#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : user_request.py
@Author  : Blue-Wales
@Date    : 2026-08-22
@Desc    : 用户相关请求体模型
"""

from pydantic import BaseModel, Field
from api.request_body.page_request import PageRequest


class GetUsersRequest(PageRequest):
    """分页获取用户列表请求体"""

    page: int = Field(default=1, description="页码", gt=0)
    page_size: int = Field(default=10, description="每页条数", gt=0, le=100)
    name: str | None = Field(default=None, description="用户名")
    mobile: str | None = Field(default=None, description="手机号")
    role_ids: list[int] | None = Field(default=None, description="角色ID列表")
    status: bool | None = Field(default=None, description="用户状态（true为激活）")


class GetUserNameListRequest(BaseModel):
    """获取用户名称列表请求体"""

    name: str | None = Field(default=None, description="用户名")


class EditUserStatusRequest(BaseModel):
    """修改用户状态请求体"""

    entity_id_list: list[int] = Field(title="用户id列表", alias="user_id_list")
    status: bool = Field(title="状态")


class RoleLoginRequest(BaseModel):
    """角色切换请求体"""

    role_id: int = Field(..., title="角色ID", description="要切换到的角色ID")


class CrmUpdateCustomerConsultantRequest(BaseModel):
    """更新客户顾问请求体"""

    mobile: str = Field(title="新顾问手机号")
    customer_id: int = Field(title="客户id")
    operation_consultant: str = Field(title="操作人名称")
    customer_mobile: str = Field(title="客户手机号")
    wechat: str = Field(title="客户微信")
    campus_id: str = Field(title="客户校区id")
    apartment_id: str = Field(title="公寓id")
    room_type_id: str = Field(title="房型id")
    name: str = Field(title="预定人名称")
    source_consultant_mobile: str = Field(title="原顾问手机号")
