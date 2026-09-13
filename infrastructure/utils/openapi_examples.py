#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : openapi_examples.py
@Author  : Blue-Wales
@Date    : 2026-08-22
@Desc    : OpenAPI 文档示例增强
"""

from copy import deepcopy
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

TAGS_METADATA = [
    {"name": "健康检查", "description": "服务存活、就绪和依赖组件健康状态检查。"},
    {"name": "文件", "description": "文件上传与文件资源返回。"},
    {"name": "客户认证", "description": "客户公众号扫码登录、刷新令牌和退出登录。"},
    {"name": "客户资料", "description": "当前客户资料查询与修改。"},
    {"name": "公开站点", "description": "游客可查看的公开信息。"},
]


OPENAPI_EXAMPLES = {
    "/health": {
        "get": {
            "response": {
                "status": "healthy",
                "version": "2.0.0",
                "environment": "dev",
                "timestamp": "2026-05-26T10:30:00Z",
                "components": {
                    "database": {"status": "healthy", "message": ""},
                    "redis": {"status": "healthy", "message": ""},
                },
            }
        }
    },
    "/health/live": {"get": {"response": {"status": "alive"}}},
    "/health/ready": {"get": {"response": {"status": "ready"}}},
    "/file/upload": {
        "post": {
            "request": {"file_type": "avatar", "file": "avatar.png"},
            "response": {
                "code": 200,
                "message": "success",
                "data": {
                    "file_name": "avatar.png",
                    "file_path": "https://oss.example.com/avatar.png",
                },
            },
        }
    },
}


def install_openapi_examples(app: FastAPI) -> None:
    """Install a custom OpenAPI builder with module examples."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=TAGS_METADATA,
        )
        _merge_examples(openapi_schema, OPENAPI_EXAMPLES)
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi


def _merge_examples(
    openapi_schema: dict[str, Any], examples: dict[str, dict[str, dict[str, Any]]]
) -> None:
    paths = openapi_schema.get("paths", {})
    for path, method_examples in examples.items():
        if path not in paths:
            continue

        for method, example in method_examples.items():
            operation = paths[path].get(method)
            if not operation:
                continue

            request_example = example.get("request")
            response_example = example.get("response")
            if request_example is not None:
                _set_request_example(operation, request_example)
            if response_example is not None:
                _set_response_example(operation, response_example)


def _set_request_example(operation: dict[str, Any], example: dict[str, Any]) -> None:
    request_body = operation.get("requestBody")
    if not request_body:
        return

    for content in request_body.get("content", {}).values():
        content.setdefault("examples", {})
        content["examples"]["frontend_debug"] = {
            "summary": "前端调试示例",
            "value": deepcopy(example),
        }


def _set_response_example(operation: dict[str, Any], example: dict[str, Any]) -> None:
    response = operation.setdefault("responses", {}).setdefault(
        "200", {"description": "Successful Response"}
    )
    content = response.setdefault("content", {}).setdefault("application/json", {})
    content.setdefault("examples", {})
    content["examples"]["success"] = {
        "summary": "成功响应示例",
        "value": deepcopy(example),
    }
