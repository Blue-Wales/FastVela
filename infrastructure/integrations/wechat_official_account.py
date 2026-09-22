#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : wechat_official_account.py
@Author  : Blue-Wales
@Date    : 2026-09-16
@Desc    : 微信公众号二维码与明文回调适配
"""

import time
from urllib.parse import quote
from xml.etree import ElementTree

import requests

from infrastructure.core.error_handler import (
    APIRequestError,
    AuthorizationError,
    InvalidInputError,
    WeChatAPIError,
)
from infrastructure.integrations.wechat_access_token import WeChatAccessTokenClient


class WeChatOfficialAccountClient:
    """处理公众号带参数二维码和明文事件回调。"""

    def __init__(self, settings, redis_client):
        self.settings = settings
        self.access_tokens = WeChatAccessTokenClient(settings, redis_client)

    def create_qrcode(self, scene: str, ttl: int) -> str:
        """使用缓存 access_token 创建临时带参数二维码。"""
        token = self.access_tokens.get()
        payload = {
            "expire_seconds": ttl,
            "action_name": self.settings.qrcode_action_name,
            "action_info": {"scene": {"scene_str": scene}},
        }
        try:
            response = requests.post(
                self.settings.qrcode_create_url,
                params={self.settings.access_token_parameter: token},
                json=payload,
                timeout=self.settings.http_timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout:
            raise APIRequestError("创建微信公众号登录二维码超时，请检查网络连接后重试", 504)
        except requests.RequestException as exc:
            http_status = exc.response.status_code if exc.response is not None else "无响应"
            raise APIRequestError(
                f"创建微信公众号登录二维码失败，微信接口HTTP状态={http_status}，"
                "请检查网络连接和公众号接口权限",
                502,
            )
        except (ValueError, TypeError):
            raise APIRequestError("微信公众号二维码接口返回了无法解析的数据", 502)
        if data.get("errcode"):
            raise WeChatAPIError(data["errcode"], self.settings.qrcode_create_url)
        ticket = data.get("ticket")
        if not isinstance(ticket, str) or not ticket:
            raise APIRequestError("微信公众号二维码响应缺少ticket", 502)
        return self.settings.qrcode_show_url + quote(ticket, safe="")

    def validate_callback_time(self, timestamp: str) -> None:
        """校验微信公众号回调时间窗口。"""
        try:
            if abs(int(time.time()) - int(timestamp)) > self.settings.callback_tolerance:
                raise ValueError("stale callback")
        except ValueError:
            raise AuthorizationError("微信回调时间无效", 403)

    def verification_echo(self, params: dict) -> str:
        """验证微信服务器接入请求并返回原始挑战字符串。"""
        echo = params.get("echostr", "")
        self.validate_callback_time(params.get("timestamp", ""))
        return echo

    def parse_event(self, body: bytes, params: dict) -> tuple[str, str] | None:
        """解析已验签的关注或扫码事件。"""
        if len(body) > 16384:
            raise InvalidInputError("回调内容过大", 413)
        try:
            body.decode("utf-8")
            upper_body = body.upper()
            if b"\x00" in body or b"<!DOCTYPE" in upper_body or b"<!ENTITY" in upper_body:
                raise ValueError("unsafe xml")
            root = ElementTree.fromstring(body)
        except (ElementTree.ParseError, UnicodeError, ValueError):
            raise InvalidInputError("回调XML格式无效", 400)
        self.validate_callback_time(params.get("timestamp", ""))
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
