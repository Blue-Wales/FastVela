#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : customer_res_model.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 客户与认证接口响应模型。
"""

from typing import Literal

from pydantic import BaseModel, Field

from domain.entity.customer import CustomerEntity


class CustomerResponse(BaseModel):
    """当前登录客户资料。"""

    code: int = 200
    data: CustomerEntity


class TokenPair(BaseModel):
    """客户令牌对，禁止向日志输出。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class QRLoginResponse(BaseModel):
    """短期二维码及浏览器专属领取凭据。"""

    scene: str
    poll_token: str
    qrcode_url: str
    expires_in: int
    poll_interval: int = 2


class PollLoginResponse(BaseModel):
    """领取成功后同一场景无法再次签发令牌。"""

    status: Literal["pending", "expired", "consumed", "confirmed"]
    tokens: TokenPair | None = None


class MessageResponse(BaseModel):
    """操作成功响应。"""

    code: int = 200
    message: str = Field(examples=["退出登录成功"])
