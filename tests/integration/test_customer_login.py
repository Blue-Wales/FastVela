#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastVela
@File    : test_customer_login.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 扫码、客户认证与Redis原子状态的离线集成验收（微信HTTP替身，真实临时Redis和SQLite）。
"""

import base64
import hashlib
import secrets
import shutil
import struct
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
import redis
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import sessionmaker

from infrastructure.core.app import create_app
from infrastructure.core.error_handler import AuthorizationError
from infrastructure.core.settings import WeChatMPSettings, app_settings
from infrastructure.models.customer import Customer, CustomerIdentity
from infrastructure.utils.customer_session_tools import CustomerSessionStore
from infrastructure.utils.database import Base, get_db
from infrastructure.utils.wechat_mp_tools import WeChatMPClient


@pytest.fixture(scope="module")
def redis_pool(tmp_path_factory):
    executable = shutil.which("redis-server")
    if not executable:
        pytest.skip("需要 redis-server 验证真实Lua原子操作")
    directory = tempfile.TemporaryDirectory(prefix="fv-redis-", dir="/tmp")
    socket = directory.name + "/redis.sock"
    process = subprocess.Popen(
        [executable, "--port", "0", "--unixsocket", socket, "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pool = redis.ConnectionPool(connection_class=redis.UnixDomainSocketConnection, path=socket)
    client = redis.Redis(connection_pool=pool)
    try:
        for _ in range(100):
            try:
                if client.ping():
                    break
            except redis.ConnectionError:
                time.sleep(0.02)
        else:
            raise RuntimeError("临时 Redis 未启动")
        yield pool
    finally:
        client.close()
        pool.disconnect()
        process.terminate()
        process.wait(timeout=5)
        directory.cleanup()


@pytest.fixture
def system(tmp_path, redis_pool, monkeypatch):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "customer.db"), connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine, tables=[Customer.__table__, CustomerIdentity.__table__])
    sessions = sessionmaker(bind=engine)
    cfg = app_settings.model_copy(deep=True)
    cfg.wechat_mp = WeChatMPSettings(
        enabled=True,
        app_id="wx-test",
        app_secret="test-secret",
        original_id="gh_test",
        callback_token="callback-secret",
        encoding_aes_key=base64.b64encode(b"k" * 32).decode().rstrip("="),
    )
    cfg.jwt.secret_key = "test-jwt-key-with-at-least-thirty-two-characters"
    monkeypatch.setattr("infrastructure.core.app.init_database", lambda _: engine)
    monkeypatch.setattr("infrastructure.core.app.init_cache", lambda _: redis_pool)
    monkeypatch.setattr("infrastructure.core.app.init_logger", lambda _: None)
    http = Mock(
        return_value=SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"ticket": "test/ticket+", "expire_seconds": 180},
        )
    )
    monkeypatch.setattr("infrastructure.utils.wechat_mp_tools.requests.request", http)
    app = create_app(cfg)

    def db_override():
        with sessions() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = db_override

    # 新增写操作和私有 GET 必须受到全局客户鉴权保护。
    @app.post("/business/write")
    def business_write():
        return {"ok": True}

    @app.get("/business/private")
    def business_private():
        return {"ok": True}

    r = redis.Redis(connection_pool=redis_pool)
    r.set("fastvela:wechat:access:wx-test", "upstream-token", ex=300)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, redis=r, settings=cfg, sessions=sessions, http=http)
    # 仅清理此测试自己启动的临时Redis，不连接用户服务。
    r.flushdb()
    r.close()


def callback_payload(system, scene, open_id="openid-one", event="SCAN"):
    event_key = "qrscene_" + scene if event == "subscribe" else scene
    message = f"<xml><ToUserName>gh_test</ToUserName><FromUserName>{open_id}</FromUserName><MsgType>event</MsgType><Event>{event}</Event><EventKey>{event_key}</EventKey></xml>".encode()
    plain = b"r" * 16 + struct.pack("!I", len(message)) + message + b"wx-test"
    padding = 32 - len(plain) % 32
    plain += bytes([padding]) * padding
    encryptor = Cipher(algorithms.AES(b"k" * 32), modes.CBC(b"k" * 16)).encryptor()
    encrypted = base64.b64encode(encryptor.update(plain) + encryptor.finalize()).decode()
    timestamp, nonce = str(int(time.time())), "test-nonce"
    signature = hashlib.sha1(
        "".join(sorted(["callback-secret", timestamp, nonce, encrypted])).encode()
    ).hexdigest()
    return {
        "timestamp": timestamp,
        "nonce": nonce,
        "msg_signature": signature,
    }, f"<xml><Encrypt>{encrypted}</Encrypt></xml>"


def begin_login(system):
    response = system.client.post("/auth/wechat/qr")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert "test%2Fticket%2B" in data["qrcode_url"]
    return {"scene": data["scene"], "poll_token": data["poll_token"]}


def complete_login(system, event="SCAN"):
    credentials = begin_login(system)
    params, body = callback_payload(system, credentials["scene"], event=event)
    response = system.client.post("/auth/wechat/callback", params=params, content=body)
    assert response.status_code == 200 and response.text == "success"
    response = system.client.post("/auth/wechat/poll", json=credentials)
    assert response.status_code == 200, response.text
    return credentials, response.json()["tokens"]


def test_guest_policy_and_removed_routes(system):
    for path in ["/health/live", "/public/site"]:
        assert system.client.get(path).status_code == 200
    for method, path in [
        ("GET", "/customers/me"),
        ("PATCH", "/customers/me"),
        ("POST", "/file/upload"),
        ("POST", "/business/write"),
        ("GET", "/business/private"),
    ]:
        assert system.client.request(method, path).json()["code"] == 401
    paths = system.client.get("/openapi.json").json()["paths"]
    assert not any(path.startswith(("/users", "/role", "/permissions", "/token")) for path in paths)
    assert system.client.get("/health/live-other").status_code == 404


@pytest.mark.parametrize("event", ["SCAN", "subscribe"])
def test_login_profile_rotation_and_logout(system, event):
    credentials, tokens = complete_login(system, event)
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    response = system.client.get("/customers/me", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data["entity_id"], str)
    assert "open_id" not in data and "mobile" not in data
    response = system.client.patch("/customers/me", headers=headers, json={"nick_name": "新的昵称"})
    assert response.json()["data"]["nick_name"] == "新的昵称"
    assert (
        system.client.patch("/customers/me", headers=headers, json={"status": 1}).status_code == 422
    )
    assert (
        system.client.patch("/customers/me", headers=headers, json={"nick_name": None}).status_code
        == 422
    )
    assert system.client.post("/auth/wechat/poll", json=credentials).json()["status"] == "consumed"
    rotated = system.client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rotated.status_code == 200
    assert (
        system.client.post(
            "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).json()["code"] == 401
    )
    refresh_headers = {"Authorization": "Bearer " + rotated.json()["refresh_token"]}
    assert system.client.get("/customers/me", headers=refresh_headers).json()["code"] == 401
    assert system.client.post("/auth/logout", headers=headers).status_code == 200
    assert system.client.get("/customers/me", headers=headers).json()["code"] == 401
    assert (
        system.client.post(
            "/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]}
        ).json()["code"] == 401
    )


def test_poll_secret_expiry_and_callback_security(system):
    credentials = begin_login(system)
    assert system.client.post("/auth/wechat/poll", json=credentials).json()["status"] == "pending"
    wrong = {**credentials, "poll_token": "x" * 43}
    assert system.client.post("/auth/wechat/poll", json=wrong).json()["code"] == 401
    params, body = callback_payload(system, credentials["scene"])
    assert (
        system.client.post(
            "/auth/wechat/callback", params={**params, "msg_signature": "bad"}, content=body
        ).status_code
        == 403
    )
    assert (
        system.client.post(
            "/auth/wechat/callback", params={**params, "timestamp": "1"}, content=body
        ).status_code
        == 403
    )
    assert (
        system.client.post(
            "/auth/wechat/callback", params=params, content=body.replace("<Encrypt>", "<Encrypt>A")
        ).status_code
        == 403
    )
    assert (
        system.client.post(
            "/auth/wechat/callback", content="<!DOCTYPE xml [<!ENTITY test 'x'>]><xml/>"
        ).status_code
        == 400
    )
    assert system.client.post("/auth/wechat/callback", content="x" * 16385).status_code == 413
    assert (
        system.client.post("/auth/wechat/callback", params=params, content="<xml/>").status_code
        == 403
    )
    system.redis.delete("fastvela:auth:qr:" + credentials["scene"])
    assert system.client.post("/auth/wechat/poll", json=credentials).json()["status"] == "expired"
    assert (
        system.client.post("/auth/wechat/callback", params=params, content=body).text == "success"
    )
    assert not system.redis.exists("fastvela:auth:qr:" + credentials["scene"])


def test_duplicate_events_and_repeat_login_reuse_customer(system):
    credentials = begin_login(system)
    for open_id in ["openid-one", "openid-two", "openid-one"]:
        params, body = callback_payload(system, credentials["scene"], open_id)
        assert (
            system.client.post("/auth/wechat/callback", params=params, content=body).status_code
            == 200
        )
    assert system.client.post("/auth/wechat/poll", json=credentials).status_code == 200
    complete_login(system)
    with system.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Customer)) == 1
        assert db.scalar(select(CustomerIdentity.subject)) == "openid-one"


def test_disabled_customer_and_redis_outage_fail_closed(system, monkeypatch):
    _, tokens = complete_login(system)
    with system.sessions() as db:
        db.execute(update(Customer).values(status=2))
        db.commit()
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    assert system.client.get("/customers/me", headers=headers).json()["code"] == 401
    assert (
        system.client.post(
            "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).json()["code"] == 401
    )
    credentials = begin_login(system)
    params, body = callback_payload(system, credentials["scene"])
    system.client.post("/auth/wechat/callback", params=params, content=body)
    assert system.client.post("/auth/wechat/poll", json=credentials).json()["code"] == 401
    monkeypatch.setattr(redis.Redis, "exists", Mock(side_effect=redis.ConnectionError("offline")))
    assert system.client.get("/customers/me", headers=headers).json()["code"] == 502
    assert system.client.get("/public/site").status_code == 200


def test_backend_and_malformed_tokens_rejected(system):
    now = int(time.time())
    payload = {"sub": "1", "exp": now + 300, "role_id": 1}
    for extra in [
        {},
        {
            "sid": "x",
            "iat": now,
            "aud": "fastvela:customer",
            "iss": "FastVela",
            "type": "access",
            "sub": "not-an-id",
        },
    ]:
        token = jwt.encode({**payload, **extra}, system.settings.jwt.secret_key, algorithm="HS256")
        assert (
            system.client.get(
                "/customers/me", headers={"Authorization": "Bearer " + token}
            ).json()["code"] == 401
        )


def test_atomic_claim_refresh_and_rate_limit(system):
    store = CustomerSessionStore(system.redis, system.settings.jwt)
    scene, secret = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
    store.create_scene(scene, secret, 60)
    assert store.confirm_scene(scene, "openid-one") == 1
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: store.consume_scene(scene, secret), range(16)))
    assert sum(results) == 1
    assert store.confirm_scene(scene, "openid-two") == 0
    tokens = store.issue(123)

    def refresh(_):
        try:
            return store.refresh(tokens["refresh_token"])
        except AuthorizationError:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(refresh, range(16)))
    assert sum(result is not None for result in results) == 1
    for _ in range(10):
        assert system.client.post("/auth/wechat/qr").status_code == 200
    assert system.client.post("/auth/wechat/qr").json()["code"] == 400


def test_wechat_failure_does_not_create_scene(system):
    system.http.return_value.json = lambda: {"errcode": 48001}
    assert system.client.post("/auth/wechat/qr").json()["code"] == 502
    assert list(system.redis.scan_iter("fastvela:auth:qr:*")) == []


def test_safe_echo_and_invalid_cipher(system):
    client = WeChatMPClient(system.settings.wechat_mp, system.redis)
    params, xml = callback_payload(system, "s" * 32)
    encrypted = xml.split("<Encrypt>")[1].split("</Encrypt>")[0]
    echo = client.verification_echo({**params, "echostr": encrypted})
    assert "<MsgType>event</MsgType>" in echo
    with pytest.raises(AuthorizationError):
        client.decrypt("invalid-base64!")


def test_plaintext_handshake_does_not_allow_plaintext_event(system):
    timestamp, nonce = str(int(time.time())), "handshake"
    signature = hashlib.sha1(
        "".join(sorted(["callback-secret", timestamp, nonce])).encode()
    ).hexdigest()
    params = {
        "signature": signature,
        "timestamp": timestamp,
        "nonce": nonce,
        "echostr": "challenge",
    }
    response = system.client.get("/auth/wechat/callback", params=params)
    assert response.status_code == 200 and response.text == "challenge"
    assert (
        system.client.post("/auth/wechat/callback", params=params, content="<xml/>").status_code
        == 403
    )


def test_wechat_expired_access_token_refreshed_once(system):
    replies = [
        {"errcode": 40001},
        {"access_token": "new-upstream-token", "expires_in": 7200},
        {"ticket": "recovered-ticket"},
    ]
    system.http.side_effect = [
        SimpleNamespace(raise_for_status=lambda: None, json=lambda data=data: data)
        for data in replies
    ]
    response = system.client.post("/auth/wechat/qr")
    assert response.status_code == 200
    assert "recovered-ticket" in response.json()["qrcode_url"]
    assert system.http.call_count == 3
    assert system.redis.get("fastvela:wechat:access:wx-test") == b"new-upstream-token"


def test_expired_customer_access_token(system):
    store = CustomerSessionStore(system.redis, system.settings.jwt)
    pair = store.issue(123)
    payload = store.decode(pair["access_token"], "access")
    payload["exp"] = int(time.time()) - 1
    token = jwt.encode(payload, system.settings.jwt.secret_key, algorithm="HS256")
    assert (
        system.client.get("/customers/me", headers={"Authorization": "Bearer " + token}).json()["code"] == 401
    )


def test_database_failure_does_not_consume_login(system, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session

    credentials = begin_login(system)
    params, body = callback_payload(system, credentials["scene"])
    system.client.post("/auth/wechat/callback", params=params, content=body)
    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", Mock(side_effect=SQLAlchemyError("commit unavailable")))
        assert system.client.post("/auth/wechat/poll", json=credentials).json()["code"] == 502
    assert system.redis.hget("fastvela:auth:qr:" + credentials["scene"], "status") == b"confirmed"
    response = system.client.post("/auth/wechat/poll", json=credentials)
    assert response.status_code == 200 and response.json()["status"] == "confirmed"

