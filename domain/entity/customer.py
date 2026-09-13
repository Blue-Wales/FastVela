#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : customer.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 客户实体及可公开的客户资料。
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class CustomerEntity(BaseModel):
    """客户资料快照；外部身份与会话凭据不在该对象中暴露。"""

    model_config = ConfigDict(from_attributes=True)
    entity_id: int
    nick_name: str
    gender: int
    birthday: date | None = None
    country: str
    province: str
    city: str
    personal_profile: str
    status: int
    deleted_at: datetime | None = Field(default=None, exclude=True)

    @field_serializer("entity_id")
    def serialize_id(self, value: int) -> str:
        return str(value)
