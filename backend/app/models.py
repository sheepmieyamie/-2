from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BenchmarkAccount(Base):
    __tablename__ = "benchmark_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(128), default="")
    avatar: Mapped[str] = mapped_column(String(512), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    follower_count: Mapped[int] = mapped_column(Integer, default=0)
    note_count: Mapped[int] = mapped_column(Integer, default=0)
    share_text: Mapped[str] = mapped_column(String(512), default="")
    style_profile: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    notes: Mapped[list["BenchmarkNote"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class BenchmarkNote(Base):
    __tablename__ = "benchmark_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("benchmark_accounts.id"))
    note_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    note_type: Mapped[str] = mapped_column(String(32), default="normal")
    liked_count: Mapped[int] = mapped_column(Integer, default=0)
    collected_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    raw_data: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    account: Mapped["BenchmarkAccount"] = relationship(back_populates="notes")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    account_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatSession(Base):
    """对话会话元数据（自定义标题等）。"""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ContentPreset(Base):
    """产品 + 目标人群描述，可复用调用。"""

    __tablename__ = "content_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    product_desc: Mapped[str] = mapped_column(Text, default="")
    audience_desc: Mapped[str] = mapped_column(Text, default="")
    extra_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ReferencePost(Base):
    """单篇参考帖子，用于仿写对标。"""

    __tablename__ = "reference_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[str] = mapped_column(String(64), index=True)
    share_text: Mapped[str] = mapped_column(String(512), default="")
    title: Mapped[str] = mapped_column(String(256), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    note_type: Mapped[str] = mapped_column(String(32), default="normal")
    liked_count: Mapped[int] = mapped_column(Integer, default=0)
    collected_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    author_nickname: Mapped[str] = mapped_column(String(128), default="")
    style_analysis: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class UsageEvent(Base):
    """匿名客户使用行为（用于产品优化分析）。"""

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True, default="anonymous")
    meta: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
