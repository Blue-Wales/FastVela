#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : wechat_mp.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 微信公众号带参数二维码与安全模式回调适配。
"""

import base64
import hashlib
import secrets
import struct
import time
from urllib.parse import quote
from xml.etree import ElementTree

import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from infrastructure.core.error_handler import APIRequestError, AuthorizationError, InvalidInputError


def parse_xml(body: bytes):
    # 明确拒绝 DTD/实体及非 UTF-8 编码，限制正文大小后才进入解析器。
    if len(body) > 16384:
        raise InvalidInputError("回调内容过大", 413)
    try:
        body.decode("utf-8")
        if b"\x00" in body or b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
            raise ValueError("DTD is forbidden")
        return ElementTree.fromstring(body)
    except (ElementTree.ParseError, UnicodeError, ValueError):
        raise InvalidInputError("回调XML格式无效", 400)


class WeChatAPIError(APIRequestError):
    """仅保留供应商错误码，不暴露可能包含敏感信息的 errmsg。"""

    def __init__(self, code):
        self.code = code
        super().__init__("微信接口返回业务错误，请检查公众号配置", 502)


class WeChatMPClient:
    """使用官方 HTTPS 接口；阻塞 I/O 由同步 API/线程池调用。"""

    def __init__(self, settings, redis_client):
        self.settings = settings
        self.redis = redis_client

    def require_enabled(self):
        if not self.settings.enabled:
            raise APIRequestError("公众号登录尚未启用", 503)

    def _request(self, method: str, path: str, **kwargs):
        try:
            response = requests.request(
                method,
                "https://api.weixin.qq.com/cgi-bin/" + path,
                timeout=self.settings.http_timeout,
                **kwargs,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("unexpected response")
        except (requests.RequestException, ValueError):
            # 不将含 access_token/AppSecret 的请求URL或响应体写入异常日志。
            raise APIRequestError("微信接口暂时不可用", 502)
        if data.get("errcode"):
            raise WeChatAPIError(data["errcode"])
        return data

    def access_token(self):
        key = "fastvela:wechat:access:" + self.settings.app_id
        token = self.redis.get(key)
        if token:
            return token.decode() if isinstance(token, bytes) else token
        # 多进程共用缓存与互斥锁，避免同时刷新使旧 access_token 失效。
        with self.redis.lock(key + ":lock", timeout=15, blocking_timeout=8):
            token = self.redis.get(key)
            if token:
                return token.decode() if isinstance(token, bytes) else token
            data = self._request(
                "GET",
                "token",
                params={
                    "grant_type": "client_credential",
                    "appid": self.settings.app_id,
                    "secret": self.settings.app_secret,
                },
            )
            token = data.get("access_token")
            expires = data.get("expires_in")
            if (
                not isinstance(token, str)
                or not token
                or not isinstance(expires, int)
                or expires <= 120
            ):
                raise APIRequestError("微信令牌响应无效", 502)
            self.redis.set(key, token, ex=expires - 120)
            return token

    def create_qrcode(self, scene: str, ttl: int) -> str:
        self.require_enabled()
        token = self.access_token()
        payload = {
            "expire_seconds": ttl,
            "action_name": "QR_STR_SCENE",
            "action_info": {"scene": {"scene_str": scene}},
        }
        try:
            data = self._request(
                "POST", "qrcode/create", params={"access_token": token}, json=payload
            )
        except WeChatAPIError as exc:
            if exc.code not in (40001, 40014, 42001):
                raise
            # 只删除本次失效的缓存值，不能覆盖其他worker刚刷新的凭据。
            self.redis.eval(
                "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0",
                1,
                "fastvela:wechat:access:" + self.settings.app_id,
                token,
            )
            data = self._request(
                "POST", "qrcode/create", params={"access_token": self.access_token()}, json=payload
            )
        ticket = data.get("ticket")
        if not isinstance(ticket, str) or not ticket:
            raise APIRequestError("微信二维码响应无效", 502)
        return "https://mp.weixin.qq.com/cgi-bin/showqrcode?ticket=" + quote(ticket, safe="")

    def verify_signature(self, signature: str, timestamp: str, nonce: str, encrypted: str = ""):
        self.require_enabled()
        try:
            if abs(int(time.time()) - int(timestamp)) > self.settings.callback_tolerance:
                raise ValueError("stale callback")
        except ValueError:
            raise AuthorizationError("回调时间无效", 403)
        values = [self.settings.callback_token, timestamp, nonce]
        if encrypted:
            values.append(encrypted)
        expected = hashlib.sha1("".join(sorted(values)).encode()).hexdigest()
        if not signature or not nonce or not secrets.compare_digest(expected, signature):
            raise AuthorizationError("微信回调签名无效", 403)

    def decrypt(self, encrypted: str) -> bytes:
        try:
            key = base64.b64decode(self.settings.encoding_aes_key + "=", validate=True)
            ciphertext = base64.b64decode(encrypted, validate=True)
            decryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).decryptor()
            plain = decryptor.update(ciphertext) + decryptor.finalize()
            padding = plain[-1]
            if not 1 <= padding <= 32 or plain[-padding:] != bytes([padding]) * padding:
                raise ValueError("invalid padding")
            plain = plain[:-padding]
            size = struct.unpack("!I", plain[16:20])[0]
            if size > len(plain) - 20 or plain[20 + size :].decode() != self.settings.app_id:
                raise ValueError("wrong app id")
            return plain[20 : 20 + size]
        except (ValueError, IndexError, struct.error, UnicodeError):
            raise AuthorizationError("微信加密回调无效", 403)

    def verification_echo(self, params: dict) -> str:
        echo = params.get("echostr", "")
        if len(echo) > 4096:
            raise InvalidInputError("echostr 过长", 400)
        if params.get("msg_signature"):
            self.verify_signature(
                params.get("msg_signature", ""),
                params.get("timestamp", ""),
                params.get("nonce", ""),
                echo,
            )
            try:
                return self.decrypt(echo).decode()
            except UnicodeError:
                raise InvalidInputError("echostr 无效", 400)
        self.verify_signature(
            params.get("signature", ""), params.get("timestamp", ""), params.get("nonce", "")
        )
        return echo

    def parse_event(self, body: bytes, params: dict) -> tuple[str, str] | None:
        self.require_enabled()
        root = parse_xml(body)
        encrypted = root.findtext("Encrypt", "")
        if self.settings.callback_mode == "safe":
            if not encrypted:
                raise AuthorizationError("安全模式要求加密回调", 403)
            self.verify_signature(
                params.get("msg_signature", ""),
                params.get("timestamp", ""),
                params.get("nonce", ""),
                encrypted,
            )
            root = parse_xml(self.decrypt(encrypted))
        else:
            if encrypted:
                raise InvalidInputError("回调模式不匹配", 400)
            self.verify_signature(
                params.get("signature", ""), params.get("timestamp", ""), params.get("nonce", "")
            )
        if root.findtext("ToUserName") != self.settings.original_id:
            raise AuthorizationError("公众号接收方不匹配", 403)
        if root.findtext("MsgType") != "event":
            return None
        event = root.findtext("Event")
        scene = root.findtext("EventKey", "")
        if event == "subscribe" and scene.startswith("qrscene_"):
            scene = scene[8:]
        elif event != "SCAN":
            return None
        open_id = root.findtext("FromUserName", "")
        if not 20 <= len(scene) <= 64 or not 1 <= len(open_id) <= 128:
            return None
        return scene, open_id
