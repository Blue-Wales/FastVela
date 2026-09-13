#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : auth_request.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 扫码登录和会话请求参数。
"""

from pydantic import BaseModel, ConfigDict, Field


class PollLoginRequest(BaseModel):
    """poll_token 仅保存在创建二维码的浏览器，不得放入二维码或URL。"""

    model_config = ConfigDict(extra="forbid")
    scene: str = Field(min_length=20, max_length=64)
    poll_token: str = Field(min_length=32, max_length=128)


class RefreshTokenRequest(BaseModel):
    """刷新令牌在成功刷新后立即作废。"""

    model_config = ConfigDict(extra="forbid")
    refresh_token: str = Field(min_length=32, max_length=4096)


class WeChatCallbackRequest(BaseModel):
    """微信服务器推送签名参数；GET接入验证时包含echostr。"""

    signature: str = Field(default="", max_length=128)
    timestamp: str = Field(default="", max_length=32)
    nonce: str = Field(default="", max_length=128)
    msg_signature: str = Field(default="", max_length=128)
    echostr: str = Field(default="", max_length=4096)
    encrypt_type: str = Field(default="", max_length=16)
