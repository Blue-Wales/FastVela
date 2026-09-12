#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : role.py
@Author  : Blue-Wales
@Date    : 2026-08-22
@Desc    : 角色管理接口
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from starlette.status import HTTP_200_OK

from api.request_body.role_request import (
    CreateRole,
    EditRoleUsers,
    GetRoleUsersByPage,
    UpdateRole,
)
from api.response_body.json_response import BaseResponseModel
from api.response_model.role_res_model import (
    RoleInfoModel,
    RoleTreeModel,
    RoleUsersItemModel,
)
from infrastructure.core.container import (
    application_factory,
    domain_service_factory,
    repository_factory,
)
from infrastructure.core.enum_var import PermissionLevel, Permissions
from infrastructure.utils.database import get_db
from infrastructure.utils.response_model_generator import (
    generate_paged_response_model,
    generate_response_model,
)

role_router = APIRouter()




@role_router.get(
    "/tree",
    summary="获取角色树",
    response_model=generate_response_model(RoleTreeModel, "role_tree")
)
async def get_role_tree(role_id: int, db: Session = Depends(get_db)):
    """获取角色树"""

    app_service = application_factory.get_bean("role_app_service", db=db)

    role_repo = repository_factory.get_bean("role_repo", db=app_service.db)

    result = await app_service.get_role_tree(role_id=role_id, role_repo=role_repo)

    return JSONResponse(status_code=HTTP_200_OK, content=result)



@role_router.post(
    "/user_list",
    summary="获取角色相关用户列表",
    response_model=generate_paged_response_model(RoleUsersItemModel, "role_users_list")
)
async def get_role_user_list(request_data: GetRoleUsersByPage, db: Session = Depends(get_db)):
    """获取角色相关用户列表"""

    role_app_service = application_factory.get_bean("role_app_service", db=db)

    role_domain_service = domain_service_factory.get_bean("role_domain_service")

    user_domain_service = domain_service_factory.get_bean("user_domain_service")

    role_repo = repository_factory.get_bean("role_repo", db=role_app_service.db)

    user_repo = repository_factory.get_bean("user_repo", db=role_app_service.db)

    result = await role_app_service.get_role_user_list(
        role_domain_service=role_domain_service,
        user_domain_service=user_domain_service,
        role_repo=role_repo,
        user_repo=user_repo,
        role_id=request_data.role_id,
        name=request_data.name,
        mobile=request_data.mobile,
        unregistered=request_data.unregistered,
        page=request_data.page,
        page_size=request_data.page_size,
    )

    return JSONResponse(status_code=HTTP_200_OK, content=result)


@role_router.get(
    "/info",
    summary="获取角色信息",
    response_model=generate_response_model(RoleInfoModel, name="role_info")
)
async def get_role_info(role_id: int, db: Session = Depends(get_db)):
    """获取角色信息"""

    app_service = application_factory.get_bean("role_app_service", db=db)

    role_repo = repository_factory.get_bean("role_repo", db=app_service.db)

    result = await app_service.get_role(role_id=role_id, role_repo=role_repo)

    return JSONResponse(status_code=HTTP_200_OK, content=result)

