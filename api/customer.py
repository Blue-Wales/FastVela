#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : customer.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 客户资料接口
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from starlette.status import HTTP_200_OK

from api.request_body.customer_request import UpdateCustomerRequest
from api.response_model.customer_res_model import CustomerResponse
from infrastructure.core.container import application_factory, repository_factory
from infrastructure.utils.customer_auth_tools import get_customer_redis, require_customer
from infrastructure.utils.database import get_db

customer_router = APIRouter(dependencies=[Depends(require_customer)])


@customer_router.get("/me", summary="获取当前客户资料", response_model=CustomerResponse)
async def get_current_customer(
    request: Request, db: Session = Depends(get_db), redis_client=Depends(get_customer_redis)
):
    """获取当前客户资料"""

    customer_app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request.app.state.settings,
    )

    customer_repo = repository_factory.get_bean("customer_repo", db=customer_app_service.db)

    result = await customer_app_service.get_current_customer(
        customer_id=request.state.customer.entity_id, customer_repo=customer_repo
    )

    return JSONResponse(status_code=HTTP_200_OK, content=result)


@customer_router.post("/me", summary="修改当前客户资料", response_model=CustomerResponse)
async def update_customer(
    request_data: UpdateCustomerRequest,
    request: Request,
    db: Session = Depends(get_db),
    redis_client=Depends(get_customer_redis),
):
    """修改当前客户资料"""

    customer_app_service = application_factory.get_bean(
        "customer_app_service",
        db=db,
        redis_client=redis_client,
        settings=request.app.state.settings,
    )

    customer_repo = repository_factory.get_bean("customer_repo", db=customer_app_service.db)

    result = await customer_app_service.update_profile(
        customer_id=request.state.customer.entity_id,
        request_data=request_data,
        customer_repo=customer_repo,
    )

    return JSONResponse(status_code=HTTP_200_OK, content=result)
