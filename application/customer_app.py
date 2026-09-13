#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : customer_app.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 客户应用服务
"""

import secrets

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from api.request_body.auth_request import (
    PollLoginRequest,
    RefreshTokenRequest,
    WeChatCallbackRequest,
)
from api.request_body.customer_request import UpdateCustomerRequest
from api.response_model.customer_res_model import CustomerResponse
from application.base import BaseApplicationService
from domain.repo.interfaces.customer import ICustomerRepository
from infrastructure.core.container import application_factory
from infrastructure.core.enum_var import BeanScope
from infrastructure.core.error_handler import APIRequestError, AuthorizationError
from infrastructure.core.settings import app_settings
from infrastructure.utils.customer_session_tools import CustomerSessionStore
from infrastructure.utils.wechat_mp_tools import WeChatMPClient


@application_factory.autowire("customer_app_service", scope=BeanScope.PROTOTYPE.value)
class CustomerApplicationService(BaseApplicationService):
    """客户资料、扫码登录和会话应用编排。"""

    def __init__(self, db, redis_client=None, settings=None):
        super().__init__(db=db, redis_client=redis_client)
        self.settings = settings or app_settings
        self.session_tools = CustomerSessionStore(self.redis_client, self.settings.jwt)
        self.wechat_tools = WeChatMPClient(self.settings.wechat_mp, self.redis_client)


    async def _run(self, func, *args, **kwargs):
        try:
            return await run_in_threadpool(func, *args, **kwargs)
        except (RedisError, SQLAlchemyError):
            raise APIRequestError("依赖服务暂时不可用")


    async def require_active(self, customer_id: int, customer_repo: ICustomerRepository):
        customer = await customer_repo.get(customer_id)
        if customer is None or customer.status != 1 or customer.deleted_at is not None:
            raise AuthorizationError("客户不可用或已注销", 403)
        return customer


    async def check_token(self, token: str, customer_repo: ICustomerRepository):
        payload = await self._run(self.session_tools.verify_access, token)
        customer = await self.require_active(int(payload["sub"]), customer_repo)
        return customer, payload


    async def get_current_customer(self, customer_id: int, customer_repo: ICustomerRepository):
        customer = await self.require_active(customer_id, customer_repo)
        return CustomerResponse(data=customer).model_dump(mode="json")


    async def update_profile(
        self, customer_id: int, request_data: UpdateCustomerRequest, customer_repo: ICustomerRepository
    ):
        await self.require_active(customer_id, customer_repo)
        customer = await customer_repo.update_profile(
            customer_id, request_data.model_dump(exclude_unset=True)
        )
        await self._run(self.db.commit)
        return CustomerResponse(data=customer).model_dump(mode="json")


    async def create_qrcode(self, client_ip: str):
        self.wechat_tools.require_enabled()
        await self._run(self.session_tools.rate_limit, "qr-create:" + client_ip, 10, 60)
        scene = secrets.token_urlsafe(24)
        poll_token = secrets.token_urlsafe(32)
        expires_in = self.settings.wechat_mp.qr_expire_seconds
        qrcode_url = await self._run(self.wechat_tools.create_qrcode, scene, expires_in)
        await self._run(self.session_tools.create_scene, scene, poll_token, expires_in)
        return {
            "scene": scene,
            "poll_token": poll_token,
            "qrcode_url": qrcode_url,
            "expires_in": expires_in,
            "poll_interval": 2,
        }


    async def poll_login(self, request_data: PollLoginRequest, client_ip: str, customer_repo: ICustomerRepository):
        await self._run(self.session_tools.rate_limit, "qr-poll:" + client_ip, 120, 60)
        state = await self._run(
            self.session_tools.read_scene, request_data.scene, request_data.poll_token
        )
        if state["status"] != "confirmed":
            return {"status": state["status"]}
        customer = await customer_repo.get_or_create_wechat(
            self.settings.wechat_mp.app_id, state["open_id"]
        )
        await self.require_active(customer.entity_id, customer_repo)
        await customer_repo.record_login(customer.entity_id, client_ip)
        await self._run(self.db.commit)
        if not await self._run(
            self.session_tools.consume_scene, request_data.scene, request_data.poll_token
        ):
            return {"status": "consumed"}
        tokens = await self._run(self.session_tools.issue, customer.entity_id)
        return {"status": "confirmed", "tokens": tokens}


    async def verify_wechat_callback(self, request_data: WeChatCallbackRequest):
        return await self._run(self.wechat_tools.verification_echo, request_data.model_dump())


    async def handle_wechat_callback(self, request_data: WeChatCallbackRequest, content: bytes):
        event = await self._run(self.wechat_tools.parse_event, content, request_data.model_dump())
        if event:
            await self._run(self.session_tools.confirm_scene, *event)
        return "success"


    async def refresh_token(self, request_data: RefreshTokenRequest, client_ip: str, customer_repo: ICustomerRepository):
        await self._run(self.session_tools.rate_limit, "refresh:" + client_ip, 30, 60)
        payload = self.session_tools.decode(request_data.refresh_token, "refresh")
        await self.require_active(int(payload["sub"]), customer_repo)
        return await self._run(self.session_tools.refresh, request_data.refresh_token)


    async def logout(self, session_id: str):
        await self._run(self.session_tools.logout, session_id)
        return {"code": 200, "message": "退出登录成功"}


    async def get_site_info(self):
        return {
            "code": 200,
            "data": {
                "name": self.settings.service_name,
                "customer_login": self.settings.wechat_mp.enabled,
            },
        }
