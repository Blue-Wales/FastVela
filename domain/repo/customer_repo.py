#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : customer_repo.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 客户仓储，唯一索引加保存点处理并发首次登录。
"""

import secrets
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from domain.entity.customer import CustomerEntity
from domain.repo.base import BaseRepository
from infrastructure.core.container import repository_factory
from infrastructure.core.enum_var import BeanScope
from infrastructure.models.customer import Customer, CustomerIdentity


@repository_factory.autowire("customer_repo", scope=BeanScope.PROTOTYPE.value)
class CustomerRepository(BaseRepository):
    """客户仓储"""

    def _get(self, customer_id: int) -> CustomerEntity | None:
        row = self.db.scalar(select(Customer).where(Customer.entity_id == customer_id))
        return CustomerEntity.model_validate(row) if row else None

    def _identity_customer(self, app_id: str, open_id: str, lock: bool = False):
        # 锁定读取使用最新已提交记录，兼容 MySQL REPEATABLE READ 下的冲突重读。
        statement = (
            select(Customer)
            .join(CustomerIdentity, Customer.entity_id == CustomerIdentity.customer_id)
            .where(
                CustomerIdentity.provider == "wechat_mp",
                CustomerIdentity.app_id == app_id,
                CustomerIdentity.subject == open_id,
            )
        )
        return self.db.scalar(statement.with_for_update() if lock else statement)

    def _get_or_create_wechat(self, app_id: str, open_id: str) -> CustomerEntity:
        row = self._identity_customer(app_id, open_id)
        if row is None:
            try:
                with self.db.begin_nested():
                    row = Customer(entity_id=secrets.randbits(63) or 1, nick_name="微信客户")
                    self.db.add(row)
                    self.db.flush()
                    self.db.add(
                        CustomerIdentity(
                            customer_id=row.entity_id,
                            provider="wechat_mp",
                            app_id=app_id,
                            subject=open_id,
                        )
                    )
                    self.db.flush()
            except IntegrityError:
                row = self._identity_customer(app_id, open_id, lock=True)
                if row is None:
                    raise
        return CustomerEntity.model_validate(row)

    def _update_profile(self, customer_id: int, fields: dict) -> CustomerEntity:
        if fields:
            self.db.execute(
                update(Customer).where(Customer.entity_id == customer_id).values(**fields)
            )
        return self._get(customer_id)

    def _record_login(self, customer_id: int, ip: str) -> None:
        self.db.execute(
            update(Customer)
            .where(Customer.entity_id == customer_id)
            .values(
                last_login_time=datetime.now(timezone.utc).replace(tzinfo=None),
                last_login_ip=ip,
            )
        )

    async def get(self, customer_id: int) -> CustomerEntity | None:
        return await run_in_threadpool(self._get, customer_id)

    async def get_or_create_wechat(self, app_id: str, open_id: str) -> CustomerEntity:
        return await run_in_threadpool(self._get_or_create_wechat, app_id, open_id)

    async def update_profile(self, customer_id: int, fields: dict) -> CustomerEntity:
        return await run_in_threadpool(self._update_profile, customer_id, fields)

    async def record_login(self, customer_id: int, ip: str) -> None:
        await run_in_threadpool(self._record_login, customer_id, ip)
