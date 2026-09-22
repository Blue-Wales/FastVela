#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : session_store.py
@Author  : Blue-Wales
@Date    : 2026-09-16
@Desc    : Redis 客户登录状态与会话存储
"""

import hashlib
import secrets
import time

import jwt

from infrastructure.core.error_handler import AuthorizationError, InvalidInputError


def digest(value: str) -> str:
    """计算登录凭据摘要。"""
    return hashlib.sha256(value.encode()).hexdigest()


class CustomerSessionStore:
    """保存扫码状态、单次领取凭据和可撤销客户会话。"""

    def __init__(self, redis_client, settings):
        self.redis = redis_client
        self.settings = settings
        self.prefix = "fastvela:auth:"

    def scene_key(self, scene: str) -> str:
        """生成扫码场景缓存键。"""
        return self.prefix + "qr:" + scene

    def create_scene(self, scene: str, poll_token: str, ttl: int) -> None:
        """保存待确认扫码场景。"""
        with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(self.scene_key(scene), "poll_hash", digest(poll_token))
            pipe.hset(self.scene_key(scene), "status", "pending")
            pipe.expire(self.scene_key(scene), ttl)
            pipe.execute()

    def confirm_scene(self, scene: str, open_id: str) -> int:
        """原子确认场景，防止重复回调替换首次扫码身份。"""
        return self.redis.eval(
            """
            if redis.call('HGET', KEYS[1], 'status') ~= 'pending' then return 0 end
            redis.call('HSET', KEYS[1], 'status', 'confirmed')
            redis.call('HSET', KEYS[1], 'open_id', ARGV[1])
            return 1
            """,
            1,
            self.scene_key(scene),
            open_id,
        )

    def read_scene(self, scene: str, poll_token: str) -> dict:
        """读取扫码场景并校验浏览器领取凭据。"""
        raw = self.redis.hgetall(self.scene_key(scene))
        data = {
            (key.decode() if isinstance(key, bytes) else key): (
                value.decode() if isinstance(value, bytes) else value
            )
            for key, value in raw.items()
        }
        if not data:
            return {"status": "expired"}
        if not secrets.compare_digest(data["poll_hash"], digest(poll_token)):
            raise AuthorizationError("登录领取凭据无效", 401)
        return data

    def consume_scene(self, scene: str, poll_token: str) -> bool:
        """原子领取扫码结果，确保同一场景只签发一次令牌。"""
        return bool(
            self.redis.eval(
                """
                if redis.call('HGET', KEYS[1], 'poll_hash') ~= ARGV[1] or
                   redis.call('HGET', KEYS[1], 'status') ~= 'confirmed' then return 0 end
                redis.call('HSET', KEYS[1], 'status', 'consumed')
                redis.call('HDEL', KEYS[1], 'open_id')
                return 1
                """,
                1,
                self.scene_key(scene),
                digest(poll_token),
            )
        )

    def rate_limit(self, key: str, limit: int, seconds: int) -> None:
        """使用基础 Redis 命令限制固定时间窗内的请求次数。"""
        cache_key = self.prefix + "rate:" + digest(key)
        count = self.redis.incr(cache_key)
        if count == 1:
            self.redis.expire(cache_key, seconds)
        if count > limit:
            raise InvalidInputError("请求过于频繁，请稍后再试", 429)

    def _tokens(self, customer_id: int, session_id: str, refresh_id: str) -> dict:
        now = int(time.time())
        common = {
            "sub": str(customer_id),
            "sid": session_id,
            "iat": now,
            "iss": "FastVela",
            "aud": "fastvela:customer",
        }
        access_token = jwt.encode(
            {**common, "type": "access", "exp": now + self.settings.expire_time},
            self.settings.secret_key,
            algorithm=self.settings.algorithm,
        )
        refresh_token = jwt.encode(
            {
                **common,
                "type": "refresh",
                "jti": refresh_id,
                "exp": now + self.settings.refresh_expire_time,
            },
            self.settings.secret_key,
            algorithm=self.settings.algorithm,
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.settings.expire_time,
        }

    def issue(self, customer_id: int) -> dict:
        """创建客户会话并签发访问令牌和刷新令牌。"""
        session_id = secrets.token_urlsafe(32)
        refresh_id = secrets.token_urlsafe(32)
        tokens = self._tokens(customer_id, session_id, refresh_id)
        self.redis.set(
            self.prefix + "session:" + session_id,
            digest(refresh_id),
            ex=self.settings.refresh_expire_time,
        )
        return tokens

    def decode(self, token: str, token_type: str) -> dict:
        """解码并校验指定类型的客户令牌。"""
        try:
            payload = jwt.decode(
                token,
                self.settings.secret_key,
                algorithms=[self.settings.algorithm],
                audience="fastvela:customer",
                issuer="FastVela",
                options={"require": ["sub", "sid", "iat", "exp", "type"]},
            )
            if (
                payload["type"] != token_type
                or not isinstance(payload["sid"], str)
                or not payload["sid"]
                or not payload["sub"].isdigit()
                or int(payload["sub"]) <= 0
            ):
                raise ValueError("invalid claims")
            if token_type == "refresh" and not isinstance(payload.get("jti"), str):
                raise ValueError("missing refresh id")
            return payload
        except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
            raise AuthorizationError("客户令牌无效或已过期", 401)

    def verify_access(self, token: str) -> dict:
        """校验访问令牌对应会话仍然有效。"""
        payload = self.decode(token, "access")
        if not self.redis.exists(self.prefix + "session:" + payload["sid"]):
            raise AuthorizationError("登录已失效", 401)
        return payload

    def refresh(self, token: str) -> dict:
        """原子轮换刷新令牌。"""
        payload = self.decode(token, "refresh")
        refresh_id = secrets.token_urlsafe(32)
        tokens = self._tokens(int(payload["sub"]), payload["sid"], refresh_id)
        rotated = self.redis.eval(
            """
            if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
            redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
            return 1
            """,
            1,
            self.prefix + "session:" + payload["sid"],
            digest(payload["jti"]),
            digest(refresh_id),
            self.settings.refresh_expire_time,
        )
        if not rotated:
            raise AuthorizationError("刷新令牌已使用或会话已撤销", 401)
        return tokens

    def logout(self, session_id: str) -> None:
        """撤销客户会话。"""
        self.redis.delete(self.prefix + "session:" + session_id)
