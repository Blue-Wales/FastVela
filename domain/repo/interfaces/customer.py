#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : customer.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 客户持久化契约。
"""

from typing import Protocol

from domain.entity.customer import CustomerEntity


class ICustomerRepository(Protocol):
    """以客户实体ID为标识；调用方控制提交，注册需保证外部身份唯一。"""

    async def get(self, customer_id: int) -> CustomerEntity | None:
        """返回客户（包含禁用状态），不存在时返回 None。"""
        ...

    async def get_or_create_wechat(self, app_id: str, open_id: str) -> CustomerEntity:
        """查找或创建公众号客户；并发冲突复用已存在身份，不提交事务。"""
        ...

    async def update_profile(self, customer_id: int, fields: dict) -> CustomerEntity:
        """更新调用方已校验的资料字段，返回新快照，不提交事务。"""
        ...

    async def record_login(self, customer_id: int, ip: str) -> None:
        """记录UTC登录时间与IP，不提交事务。"""
        ...
