#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : login.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 客户公众号扫码登录接口
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.status import HTTP_200_OK

from api.request_body.auth_request import (
    PollLoginRequest,
    RefreshTokenRequest,
    WeChatCallbackRequest,
)
from api.response_model.customer_res_model import (
    MessageResponse,
    PollLoginResponse,
    QRLoginResponse,
    TokenPair,
)
from infrastructure.core.container import application_factory, repository_factory
from infrastructure.core.error_handler import InvalidInputError, OrangeCraftException
from infrastructure.utils.customer_auth_tools import (
    get_customer_client_ip,
    get_customer_redis,
    require_customer,
)
from infrastructure.utils.database import get_db

login_router = APIRouter()


@login_router.post("/wechat/qr", summary="创建公众号登录二维码", response_model=QRLoginResponse)
async def create_qrcode(
    request: Request,
    db: Session = Depends(get_db),
    redis_client=Depends(get_customer_redis),
    client_ip: str = Depends(get_customer_client_ip),
):
    """创建公众号登录二维码"""

    customer_app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request.app.state.settings,
    )

    result = await customer_app_service.create_qrcode(client_ip=client_ip)

    return JSONResponse(
        status_code=HTTP_200_OK, content=result, headers={"Cache-Control": "no-store"}
    )


@login_router.post(
    "/wechat/poll", summary="查询并领取扫码登录结果", response_model=PollLoginResponse
)
async def poll_login(
    request_data: PollLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    redis_client=Depends(get_customer_redis),
    client_ip: str = Depends(get_customer_client_ip),
):
    """查询并领取扫码登录结果"""

    customer_app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request.app.state.settings,
    )

    customer_repo = repository_factory.get_bean("customer_repo", db=customer_app_service.db)

    result = await customer_app_service.poll_login(
        request_data=request_data, client_ip=client_ip, customer_repo=customer_repo
    )

    return JSONResponse(
        status_code=HTTP_200_OK, content=result, headers={"Cache-Control": "no-store"}
    )


@login_router.get(
    "/wechat/callback", summary="微信服务器接入验证", response_class=PlainTextResponse
)
async def verify_callback(
    request: Request,
    request_data: WeChatCallbackRequest = Depends(),
    db: Session = Depends(get_db),
    redis_client=Depends(get_customer_redis),
):
    """按微信协议原样返回验证字符串"""

    customer_app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request.app.state.settings,
    )

    try:
        result = await customer_app_service.verify_wechat_callback(request_data=request_data)
    except OrangeCraftException as exc:
        return PlainTextResponse(status_code=exc.status_code, content="invalid callback")

    return PlainTextResponse(status_code=HTTP_200_OK, content=result)


@login_router.post("/wechat/callback", summary="微信扫码事件推送", response_class=PlainTextResponse)
async def callback(
    request: Request,
    request_data: WeChatCallbackRequest = Depends(),
    db: Session = Depends(get_db),
    redis_client=Depends(get_customer_redis),
):
    """按微信协议返回success，业务处理交给应用服务"""

    customer_app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request.app.state.settings,
    )

    try:
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 16384:
                raise InvalidInputError("回调内容过大", 413)
        result = await customer_app_service.handle_wechat_callback(
            request_data=request_data, content=bytes(content)
        )
    except OrangeCraftException as exc:
        return PlainTextResponse(status_code=exc.status_code, content="invalid callback")

    return PlainTextResponse(status_code=HTTP_200_OK, content=result)


@login_router.post("/refresh", summary="刷新客户登录令牌", response_model=TokenPair)
async def refresh_token(
    request_data: RefreshTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
    redis_client=Depends(get_customer_redis),
    client_ip: str = Depends(get_customer_client_ip),
):
    """刷新客户登录令牌"""

    customer_app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request.app.state.settings,
    )

    customer_repo = repository_factory.get_bean("customer_repo", db=customer_app_service.db)

    result = await customer_app_service.refresh_token(
        request_data=request_data, client_ip=client_ip, customer_repo=customer_repo
    )

    return JSONResponse(
        status_code=HTTP_200_OK, content=result, headers={"Cache-Control": "no-store"}
    )


@login_router.post(
    "/logout",
    summary="退出客户登录",
    response_model=MessageResponse,
    dependencies=[Depends(require_customer)],
)
async def logout(
    request: Request, db: Session = Depends(get_db), redis_client=Depends(get_customer_redis)
):
    """退出客户登录"""

    customer_app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request.app.state.settings,
    )

    result = await customer_app_service.logout(session_id=request.state.customer_session["sid"])

    return JSONResponse(status_code=HTTP_200_OK, content=result)
