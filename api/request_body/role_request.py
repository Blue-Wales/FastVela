#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : role_request.py
@Author  : Blue-Wales
@Date    : 2026-08-22
@Desc    : 角色相关请求体模型
"""

from pydantic import BaseModel, Field

from api.request_body.page_request import PageRequest


class GetRoleUsersByPage(PageRequest):
    """分页获取角色用户请求体"""

    role_id: int = Field(description="角色id")
    name: str | None = Field(description="用户名", default=None)
    mobile: str | None = Field(description="手机号", default=None)
    unregistered: bool = Field(default=False, description="是否为未注册用户")


class EditRoleUsers(BaseModel):
    """编辑角色用户关系请求体"""

    role_id: int = Field(description="角色id")
    user_ids: list[int] = Field(description="用户id列表")
