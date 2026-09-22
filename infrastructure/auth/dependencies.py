#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : dependencies.py
@Author  : Blue-Wales
@Date    : 2026-09-16
@Desc    : 客户认证与匿名接口依赖
"""

from fastapi import Depends, Request
from fastapi.security import HTTPBearer
from redis import Redis
from sqlalchemy.orm import Session

from infrastructure.core.container import application_factory, repository_factory
from infrastructure.core.error_handler import AuthorizationError
from infrastructure.utils.database import get_db

bearer = HTTPBearer(auto_error=False)


def get_customer_redis(request_data: Request):
    """为当前请求创建 Redis 客户端并在结束时归还连接。"""
    redis_client = Redis(connection_pool=request_data.app.state.redis_db)
    try:
        yield redis_client
    finally:
        redis_client.close()


def get_customer_client_ip(request_data: Request) -> str:
    """读取客户请求来源地址。"""
    return request_data.client.host if request_data.client else "unknown"


async def require_customer(
    request_data: Request,
    db: Session = Depends(get_db),
    redis_client=Depends(get_customer_redis),
    credentials=Depends(bearer),
):
    """校验客户登录态并向请求上下文写入客户和会话。"""
    if getattr(request_data.state, "customer", None) is not None:
        return request_data.state.customer
    if credentials is None:
        raise AuthorizationError("请先登录", 401)
    customer_app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request_data.app.state.settings,
    )
    customer_repo = repository_factory.get_bean("customer_repo", db=db)
    customer, payload = await customer_app_service.check_token(
        token=credentials.credentials, customer_repo=customer_repo
    )
    request_data.state.customer = customer
    request_data.state.customer_session = payload
    return customer


async def require_business_customer(
    request_data: Request,
    db: Session = Depends(get_db),
    redis_client=Depends(get_customer_redis),
):
    """仅允许配置中的匿名路径绕过全局客户认证。"""
    if request_data.method == "OPTIONS":
        return None
    if request_data.url.path in request_data.app.state.settings.exclude_path:
        return None
    credentials = await bearer(request_data)
    return await require_customer(
        request_data=request_data,
        db=db,
        redis_client=redis_client,
        credentials=credentials,
    )
