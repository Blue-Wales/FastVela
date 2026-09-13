#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : app.py
@Author  : Blue-Wales
@Date    : 2026-08-22
@Desc    : Application Factory
"""

import importlib
import pkgutil
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from loguru import logger

from infrastructure.core.error_handler import init_error_handler
from infrastructure.core.log import ModulesForLogger, init_logger
from infrastructure.core.middlewares import init_middlewares
from infrastructure.core.routers import init_router
from infrastructure.core.settings import AppSettings
from infrastructure.utils.cache import init_cache
from infrastructure.utils.customer_auth_tools import require_business_customer
from infrastructure.utils.database import init_database
from infrastructure.utils.openapi_examples import install_openapi_examples

RUNTIME_MODULES = ["application.file_app", "application.customer_app", "domain.repo.file_repo", "domain.repo.customer_repo", "domain.service.email_service", "infrastructure.events"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理,确保数据库连接和redis连接池在应用关闭时被正确释放"""
    try:
        yield
    finally:
        app.state.engine.dispose()
        app.state.redis_db.disconnect()


def create_app(app_settings: AppSettings) -> FastAPI:
    """创建并配置Fastapi应用实例"""
    init_logger(ModulesForLogger.API)

    # 预加载modules
    auto_load_modules(
        base_packages=RUNTIME_MODULES
    )
    # 初始化数据库
    db_engine = init_database(app_settings.db)
    # 初始化redis
    redis_db = init_cache(app_settings.redis_db)
    # 创建服务实例
    app = FastAPI(
        title=app_settings.service_name,
        version=app_settings.service_version,
        docs_url="/docs" if app_settings.env != "prod" else None,
        redoc_url="/redoc" if app_settings.env != "prod" else None,
        openapi_url="/openapi.json" if app_settings.env != "prod" else None,
        lifespan=lifespan,
        dependencies=[Depends(require_business_customer)],
        swagger_ui_parameters={
            "defaultModelsExpandDepth": -1,
            "defaultModelExpandDepth": -1,
            "docExpansion": "none",
            "syntaxHighlight": False,
        },
    )

    app.state.settings = app_settings
    app.state.engine = db_engine
    app.state.redis_db = redis_db

    init_error_handler(app)
    init_middlewares(app)
    init_router(app, app_settings=app_settings)
    install_openapi_examples(app)

    return app


def auto_load_modules(base_packages: list[str]):
    """自动发现并加载模块"""
    for base_pkg in base_packages:
        try:
            pkg = importlib.import_module(base_pkg)
            pkg_path = getattr(pkg, "__path__", None)
            if not pkg_path:
                continue
            prefix = pkg.__name__ + "."
            for _, module_name, _ in pkgutil.walk_packages(pkg_path, prefix):
                short_name = module_name.split(".")[-1]
                if short_name != "base":
                    importlib.import_module(module_name)
                    logger.debug(f"Module loaded: {module_name}")
        except ImportError as e:
            raise ImportError(f"Failed to load required module: {base_pkg}") from e
