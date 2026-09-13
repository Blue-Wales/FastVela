#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : customer_request.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 客户资料更新参数；身份、状态、手机号和邮箱不可通过此接口修改。
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UpdateCustomerRequest(BaseModel):
    """仅允许客户修改自身展示资料，生日允许清空。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nick_name: str | None = Field(default=None, min_length=1, max_length=64, examples=["小帆"])
    gender: int | None = Field(default=None, ge=0, le=2)
    birthday: date | None = None
    country: str | None = Field(default=None, max_length=64)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    personal_profile: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_profile(self):
        for name in self.model_fields_set - {"birthday"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} 不允许为空")
        if self.birthday and self.birthday > date.today():
            raise ValueError("生日不能晚于今天")
        return self
