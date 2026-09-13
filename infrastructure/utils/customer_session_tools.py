#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : session_store.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : Redis 登录状态与客户会话；Lua 保证多 worker 下的状态变更原子性。
"""

import hashlib
import secrets
import time

import jwt

from infrastructure.core.error_handler import AuthorizationError, InvalidInputError


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class CustomerSessionStore:
    """短期扫码状态、单次领取、轮换刷新令牌和可撤销会话。"""

    def __init__(self, redis_client, settings):
        self.redis = redis_client
        self.settings = settings
        self.prefix = "fastvela:auth:"

    def scene_key(self, scene: str) -> str:
        return self.prefix + "qr:" + scene

    def create_scene(self, scene: str, poll_token: str, ttl: int):
        with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(
                self.scene_key(scene),
                mapping={"poll_hash": digest(poll_token), "status": "pending"},
            )
            pipe.expire(self.scene_key(scene), ttl)
            pipe.execute()

    def confirm_scene(self, scene: str, open_id: str):
        # 重复推送或另一个人扫码，均不能替换第一次已确认的身份。
        return self.redis.eval(
            """
            if redis.call('HGET', KEYS[1], 'status') ~= 'pending' then return 0 end
            redis.call('HSET', KEYS[1], 'status', 'confirmed', 'open_id', ARGV[1])
            return 1
        """,
            1,
            self.scene_key(scene),
            open_id,
        )

    def read_scene(self, scene: str, poll_token: str) -> dict:
        raw = self.redis.hgetall(self.scene_key(scene))
        data = {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }
        if not data:
            return {"status": "expired"}
        if not secrets.compare_digest(data["poll_hash"], digest(poll_token)):
            raise AuthorizationError("登录领取凭据无效", 401)
        return data

    def consume_scene(self, scene: str, poll_token: str) -> bool:
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

    def rate_limit(self, key: str, limit: int, seconds: int):
        count = self.redis.eval(
            """
            local count = redis.call('INCR', KEYS[1])
            if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
            return count
        """,
            1,
            self.prefix + "rate:" + digest(key),
            seconds,
        )
        if count > limit:
            raise InvalidInputError("请求过于频繁，请稍后再试", 429)

    def _tokens(self, customer_id: int, sid: str, refresh_id: str) -> dict:
        now = int(time.time())
        cfg = self.settings
        common = {
            "sub": str(customer_id),
            "sid": sid,
            "iat": now,
            "iss": "FastVela",
            "aud": "fastvela:customer",
        }
        access = jwt.encode(
            {**common, "type": "access", "exp": now + cfg.expire_time},
            cfg.secret_key,
            algorithm=cfg.algorithm,
        )
        refresh = jwt.encode(
            {**common, "type": "refresh", "jti": refresh_id, "exp": now + cfg.refresh_expire_time},
            cfg.secret_key,
            algorithm=cfg.algorithm,
        )
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": cfg.expire_time,
        }

    def issue(self, customer_id: int) -> dict:
        sid, refresh_id = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        tokens = self._tokens(customer_id, sid, refresh_id)
        self.redis.set(
            self.prefix + "session:" + sid, digest(refresh_id), ex=self.settings.refresh_expire_time
        )
        return tokens

    def decode(self, token: str, token_type: str) -> dict:
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
        payload = self.decode(token, "access")
        if not self.redis.exists(self.prefix + "session:" + payload["sid"]):
            raise AuthorizationError("登录已失效", 401)
        return payload

    def refresh(self, token: str) -> dict:
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

    def logout(self, sid: str):
        self.redis.delete(self.prefix + "session:" + sid)
