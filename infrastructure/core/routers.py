#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : routers.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : C 端路由注册；仅显式公开的接口允许游客访问。
"""

from fastapi import Depends, FastAPI

from api.customer import customer_router
from api.file import file_router
from api.health import health_router
from api.login import login_router
from api.public import public_router
from infrastructure.core.settings import AppSettings
from infrastructure.utils.customer_auth_tools import require_customer


def init_router(app: FastAPI, app_settings: AppSettings):
    app.include_router(health_router, tags=["健康检查"])
    app.include_router(public_router, prefix="/public", tags=["公开站点"])
    app.include_router(login_router, prefix="/auth", tags=["客户认证"])
    app.include_router(customer_router, prefix="/customers", tags=["客户资料"])
    app.include_router(file_router, prefix="/file", tags=["文件"], dependencies=[Depends(require_customer)])
