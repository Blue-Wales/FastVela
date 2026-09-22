#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : callback.py
@Author  : Blue-Wales
@Date    : 2026-09-16
@Desc    : 第三方平台回调接口
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse

from api.request_body.auth_request import WeChatCallbackRequest
from infrastructure.auth.dependencies import get_customer_redis
from infrastructure.core.container import application_factory
from infrastructure.utils.database import get_db

callback_router = APIRouter()


@callback_router.get(
    "/wechat/callback", summary="微信服务器接入验证", response_class=PlainTextResponse
)
async def verify_wechat_callback(
    request: Request,
    request_data: WeChatCallbackRequest = Depends(),
    db: Session = Depends(get_db),
    redis_client=Depends(get_customer_redis),
):
    """按微信协议返回验证字符串。"""
    app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request.app.state.settings,
    )
    status_code, result = await app_service.verify_wechat_callback(request_data=request_data)
    return PlainTextResponse(status_code=status_code, content=result)


@callback_router.post(
    "/wechat/callback", summary="微信扫码事件推送", response_class=PlainTextResponse
)
async def handle_wechat_callback(
    request: Request,
    request_data: WeChatCallbackRequest = Depends(),
    db: Session = Depends(get_db),
    redis_client=Depends(get_customer_redis),
):
    """将微信事件交给应用服务处理。"""
    app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request.app.state.settings,
    )
    status_code, result = await app_service.handle_wechat_callback(
        request_data=request_data, content_stream=request.stream()
    )
    return PlainTextResponse(status_code=status_code, content=result)
