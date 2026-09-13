#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : middlewares.py
@Author  : Blue-Wales
@Date    : 2026-08-22
"""

import time
import uuid
from typing import ClassVar

from fastapi import FastAPI
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from infrastructure.utils.request_utils import get_client_ip


class RequestLogMiddleWare(BaseHTTPMiddleware):
    EXCLUDE_LOG_PREFIXES: ClassVar[set[str]] = {"/health"}

    async def dispatch(self, request, call_next):
        """
        异步处理 HTTP 请求，记录请求时间并注入请求ID到响应头。
        参数:
            request: Starlette 请求对象。
            call_next: 调用下一个中间件或路由的异步函数。
        返回:
            response: 处理后的 Starlette 响应对象。
        """
        # 记录请求开始时间
        start_time = time.time()
        # 生成唯一请求ID
        request_id = uuid.uuid4().hex
        # 获取客户端IP
        client_ip = get_client_ip(request)

        response = await call_next(request)


        process_time = f"{(time.time() - start_time):.4f}s"
        # 计算并设置请求耗时到响应头
        response.headers["X-Request-Time"] = process_time
        # 将请求ID添加到响应头
        response.headers["X-Request-Id"] = request_id
        # 添加客户端IP到响应头（可选，用于调试）
        response.headers["X-Client-IP"] = client_ip
        if not any(request.url.path.startswith(prefix) for prefix in self.EXCLUDE_LOG_PREFIXES):
            # 记录请求日志，包含客户端IP
            logger.bind(request_id=request_id).debug(
                f"{client_ip} - {request.method} {request.url.path} "
                f"{response.status_code} {process_time}"
            )

        return response


def init_middlewares(app: FastAPI) -> None:
    # 1. HTTPS重定向
    # app.add_middleware(HTTPSRedirectMiddleware)

    # 2. GZip压缩
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)

    # 客户鉴权由同步依赖在工作线程中执行。

    # 4. 请求日志
    app.add_middleware(RequestLogMiddleWare)

    # 5. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
