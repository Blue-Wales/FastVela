#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : public.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 公开站点接口
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from starlette.status import HTTP_200_OK

from infrastructure.core.container import application_factory
from infrastructure.utils.customer_auth_tools import get_customer_redis
from infrastructure.utils.database import get_db

public_router = APIRouter()


@public_router.get("/site", summary="公开站点信息")
async def get_site_info(
    request: Request, db: Session = Depends(get_db), redis_client=Depends(get_customer_redis)
):
    """获取游客可查看的站点信息"""

    customer_app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request.app.state.settings,
    )

    result = await customer_app_service.get_site_info()

    return JSONResponse(status_code=HTTP_200_OK, content=result)
