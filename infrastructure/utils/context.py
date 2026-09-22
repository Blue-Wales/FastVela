#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : context.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 请求上下文兼容入口，客户鉴权统一在 infrastructure.auth.dependencies。
"""

from fastapi import Request


def get_current_customer(request: Request):
    return getattr(request.state, "customer", None)


def get_current_customer_id(request: Request) -> int | None:
    customer = get_current_customer(request)
    return customer.entity_id if customer else None
