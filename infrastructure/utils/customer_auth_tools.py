#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : customer_auth_tools.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 客户认证依赖工具
"""

from fastapi import Depends, Request
from fastapi.security import HTTPBearer
from redis import Redis
from sqlalchemy.orm import Session

from infrastructure.core.container import application_factory, repository_factory
from infrastructure.core.error_handler import AuthorizationError
from infrastructure.utils.database import get_db

bearer = HTTPBearer(auto_error=False)


def get_customer_redis(request: Request):
    redis_client = Redis(connection_pool=request.app.state.redis_db)
    try:
        yield redis_client
    finally:
        redis_client.close()


def get_customer_client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def require_customer(
    request: Request,
    db: Session = Depends(get_db),
    redis_client=Depends(get_customer_redis),
    credentials=Depends(bearer),
):
    if getattr(request.state, "customer", None) is not None:
        return request.state.customer
    if credentials is None:
        raise AuthorizationError("请先登录", 401)
    customer_app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request.app.state.settings,
    )
    customer_repo = repository_factory.get_bean("customer_repo", db=customer_app_service.db)
    customer, payload = await customer_app_service.check_token(
        token=credentials.credentials, customer_repo=customer_repo
    )
    request.state.customer = customer
    request.state.customer_session = payload
    return customer


async def require_business_customer(
    request: Request, db: Session = Depends(get_db), redis_client=Depends(get_customer_redis)
):
    public_routes = {
        ("GET", "/health"),
        ("GET", "/health/live"),
        ("GET", "/health/ready"),
        ("GET", "/public/site"),
        ("GET", "/auth/wechat/callback"),
        ("POST", "/auth/wechat/callback"),
        ("POST", "/auth/wechat/qr"),
        ("POST", "/auth/wechat/poll"),
        ("POST", "/auth/refresh"),
    }
    if (request.method, request.url.path) in public_routes:
        return
    credentials = await bearer(request)
    await require_customer(
        request=request, db=db, redis_client=redis_client, credentials=credentials
    )
