#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : user.py
@Author  : Blue-Wales
@Date    : 2026-08-22
@Desc    : 用户管理接口
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from starlette.status import HTTP_200_OK

from api.request_body.user_request import (
    GetUserNameListRequest,
    GetUsersRequest,
)
from api.response_body.json_response import BaseResponseModel
from api.response_model.user_res_model import (
    CurrentUserModel,
    UserInfoModel,
    UserItemModel,
    UserResModel,
)
from infrastructure.core.container import (
    application_factory,
    domain_service_factory,
    repository_factory,
)
from infrastructure.utils.database import get_db
from infrastructure.utils.response_model_generator import (
    generate_list_response_model,
    generate_paged_response_model,
    generate_response_model,
)

user_router = APIRouter()


@user_router.get(
    "",
    summary="获取用户列表",
    response_model=generate_paged_response_model(UserItemModel, "user_list")
)
async def users_list(request_data: GetUsersRequest, db: Session = Depends(get_db)):
    """获取用户列表"""

    user_app_service = application_factory.get_bean("user_app_service", db=db)

    user_domain_service = domain_service_factory.get_bean("user_domain_service")

    role_domain_service = domain_service_factory.get_bean("role_domain_service")

    user_repo = repository_factory.get_bean("user_repo", db=user_app_service.db)

    role_repo = repository_factory.get_bean("role_repo", db=user_app_service.db)

    result = await user_app_service.get_users(
        user_repo=user_repo,
        role_repo=role_repo,
        user_domain_service=user_domain_service,
        role_domain_service=role_domain_service,
        name=request_data.name,
        mobile=request_data.mobile,
        role_ids=request_data.role_ids,
        status=request_data.status,
        page=request_data.page,
        page_size=request_data.page_size,
    )

    return JSONResponse(status_code=HTTP_200_OK, content=result)


@user_router.get(
    "/me",
    summary="获取当前用户信息",
    response_model=generate_response_model(CurrentUserModel, "current_user"),
)
async def get_current_user(db: Session = Depends(get_db)):
    """获取当前用户信息"""

    user_app_service = application_factory.get_bean("user_app_service", db=db)

    role_domain_service = domain_service_factory.get_bean("role_domain_service")

    user_repo = repository_factory.get_bean("user_repo", db=user_app_service.db)

    role_repo = repository_factory.get_bean("role_repo", db=user_app_service.db)

    file_repo = repository_factory.get_bean("file_repo", db=user_app_service.db)

    result = await user_app_service.get_current_user(
        role_domain_service=role_domain_service,
        user_repo=user_repo,
        role_repo=role_repo,
        file_repo=file_repo,
    )

    return JSONResponse(status_code=HTTP_200_OK, content=result)


@user_router.get(
    "/choices",
    summary="获取用户名称列表",
    response_model=generate_list_response_model(UserResModel, "user_name_list")
)
async def user_name_list(
    request_data: GetUserNameListRequest, db: Session = Depends(get_db)
):
    """获取用户名称列表"""

    user_app_service = application_factory.get_bean("user_app_service", db=db)

    user_repo = repository_factory.get_bean("user_repo", db=user_app_service.db)

    result = await user_app_service.get_user_name_list(
        user_repo=user_repo, name=request_data.name
    )

    return JSONResponse(status_code=HTTP_200_OK, content=result)


@user_router.get(
    "/{user_id}",
    summary="用户详细信息",
    response_model=generate_response_model(UserInfoModel, "user_info")
)
async def users_info(user_id: int, db: Session = Depends(get_db)):
    """获取用户详细信息"""

    user_app_service = application_factory.get_bean("user_app_service", db=db)

    role_domain_service = domain_service_factory.get_bean("role_domain_service")

    user_repo = repository_factory.get_bean("user_repo", db=user_app_service.db)

    role_repo = repository_factory.get_bean("role_repo", db=user_app_service.db)

    file_repo = repository_factory.get_bean("file_repo", db=user_app_service.db)

    result = await user_app_service.get_user_info(
        role_domain_service=role_domain_service,
        user_repo=user_repo,
        role_repo=role_repo,
        file_repo=file_repo,
        user_id=user_id,
    )

    return JSONResponse(status_code=HTTP_200_OK, content=result)


