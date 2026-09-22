#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : wechat.py
@Author  : Blue-Wales
@Date    : 2026-09-16
@Desc    : 微信公众号调用凭据定时刷新任务
"""

from celery import shared_task
from redis import Redis

from infrastructure.core.settings import app_settings
from infrastructure.cron.task_loader import TaskManager
from infrastructure.integrations.wechat_access_token import WeChatAccessTokenClient
from infrastructure.utils.cache import init_cache


@shared_task(name="application.tasks.wechat.refresh_wechat_access_token")
@TaskManager.scheduled(minute="0")
def refresh_wechat_access_token() -> str:
    """每小时刷新微信公众号稳定版接口调用凭据。"""
    redis_pool = init_cache(app_settings.redis_db)
    redis_client = Redis(connection_pool=redis_pool)
    try:
        client = WeChatAccessTokenClient(app_settings.wechat_mp, redis_client)
        client.refresh(force_refresh=False)
        return "success"
    finally:
        redis_client.close()
        redis_pool.disconnect()
