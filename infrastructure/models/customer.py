#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Project : FastBrace
@File    : customer.py
@Author  : Blue-Wales
@Date    : 2026-09-12
@Desc    : 客户与外部身份；与 FastBrace 共享数据库，不改变员工模型。
"""

from sqlalchemy import (
    BIGINT,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)

from infrastructure.utils.database import Base


class Customer(Base):
    """C 端客户主体；禁用与注销均保留外部身份，避免再次扫码重新注册。"""

    __tablename__ = "customer"
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(BIGINT, nullable=False, unique=True, comment="客户实体ID")
    nick_name = Column(String(64), nullable=False, server_default="", comment="昵称")
    mobile = Column(String(32), nullable=True, unique=True, comment="已验证手机号（含国家码）")
    email = Column(String(254), nullable=True, unique=True, comment="已验证邮箱")
    gender = Column(SmallInteger, nullable=False, server_default=text("0"), comment="0未知1男2女")
    birthday = Column(Date, nullable=True, comment="生日")
    country = Column(String(64), nullable=False, server_default="", comment="国家")
    province = Column(String(64), nullable=False, server_default="", comment="省份")
    city = Column(String(64), nullable=False, server_default="", comment="城市")
    personal_profile = Column(String(255), nullable=False, server_default="", comment="个人简介")
    status = Column(
        SmallInteger, nullable=False, server_default=text("1"), comment="1正常2禁用3注销"
    )
    register_source = Column(
        String(32), nullable=False, server_default="wechat_mp", comment="注册来源"
    )
    last_login_time = Column(DateTime, nullable=True, comment="最后登录UTC时间")
    last_login_ip = Column(String(45), nullable=True, comment="最后登录IP")
    create_time = Column(
        DateTime, nullable=False, server_default=func.current_timestamp(), comment="创建UTC时间"
    )
    update_time = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        comment="修改UTC时间",
    )
    deleted_at = Column(DateTime, nullable=True, comment="注销UTC时间")
    __table_args__ = (
        Index("ix_customer_status_created", "status", "create_time"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )


class CustomerIdentity(Base):
    """按供应商和应用隔离 OpenID；UnionID 仅作关联线索，不自动跨应用合并。"""

    __tablename__ = "customer_identity"
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(
        BIGINT, ForeignKey("customer.entity_id"), nullable=False, index=True, comment="客户实体ID"
    )
    provider = Column(String(32), nullable=False, comment="身份供应商")
    app_id = Column(String(128), nullable=False, comment="供应商应用ID")
    subject = Column(String(128), nullable=False, comment="供应商用户ID/OpenID")
    union_id = Column(String(128), nullable=True, comment="UnionID（不保证提供）")
    create_time = Column(
        DateTime, nullable=False, server_default=func.current_timestamp(), comment="绑定UTC时间"
    )
    __table_args__ = (
        UniqueConstraint("provider", "app_id", "subject", name="uq_customer_identity_subject"),
        Index("ix_customer_identity_union", "provider", "union_id"),
        {"mysql_collate": "utf8mb4_bin", "mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
