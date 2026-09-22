#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : wechat_access_token.py
@Author  : Blue-Wales
@Date    : 2026-09-16
@Desc    : 微信公众号稳定版接口调用凭据
"""

import requests
from redis.exceptions import LockError

from infrastructure.core.error_handler import APIRequestError, WeChatAPIError


class WeChatAccessTokenClient:
    """定时刷新微信公众号 access_token，并向业务调用提供缓存凭据。"""

    def __init__(self, settings, redis_client):
        self.settings = settings
        self.redis = redis_client

    @property
    def cache_key(self) -> str:
        """返回当前公众号的凭据缓存键。"""
        return "fastvela:wechat:access:" + self.settings.app_id

    def get(self) -> str:
        """优先读取缓存，首次缺失时主动获取并写入 Redis。"""
        token = self.redis.get(self.cache_key)
        if token:
            return token.decode() if isinstance(token, bytes) else token
        try:
            with self.redis.lock(self.cache_key + ":lock", timeout=15, blocking_timeout=5):
                token = self.redis.get(self.cache_key)
                if token:
                    return token.decode() if isinstance(token, bytes) else token
                return self.refresh()
        except LockError:
            raise APIRequestError("微信公众号调用凭据正在刷新，请稍后重试", 503)

    def refresh(self, force_refresh: bool = False) -> str:
        """调用稳定版凭据接口并按上游有效期写入 Redis。"""
        try:
            response = requests.post(
                self.settings.access_token_url,
                json={
                    "grant_type": self.settings.access_token_grant_type,
                    "appid": self.settings.app_id,
                    "secret": self.settings.app_secret,
                    "force_refresh": force_refresh,
                },
                timeout=self.settings.http_timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout:
            raise APIRequestError("获取微信公众号调用凭据超时，请检查网络连接后重试", 504)
        except requests.RequestException as exc:
            http_status = exc.response.status_code if exc.response is not None else "无响应"
            raise APIRequestError(
                f"获取微信公众号调用凭据失败，微信接口HTTP状态={http_status}，"
                "请检查接口地址、网络连接和公众号配置",
                502,
            )
        except (ValueError, TypeError):
            raise APIRequestError("微信公众号调用凭据接口返回了无法解析的数据", 502)
        if data.get("errcode"):
            raise WeChatAPIError(data["errcode"], self.settings.access_token_url)
        token = data.get("access_token")
        expires_in = data.get("expires_in")
        if not isinstance(token, str) or not token or not isinstance(expires_in, int):
            raise APIRequestError("微信公众号调用凭据响应缺少access_token或有效期", 502)
        cache_seconds = max(expires_in - self.settings.access_token_advance_seconds, 60)
        self.redis.set(self.cache_key, token, ex=cache_seconds)
        return token
