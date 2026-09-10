import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import BIGINT_ID_TYPE


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (
        UniqueConstraint("short_code"),
        Index("ix_links_short_code", "short_code"),
        Index("ix_links_expires_at", "expires_at"),
        Index("ix_links_active_created_at", "is_active", "created_at"),
        Index("ix_links_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID_TYPE, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        unique=True,
        nullable=False,
        default=uuid.uuid4,
    )
    user_id: Mapped[int | None] = mapped_column(
        BIGINT_ID_TYPE,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    short_code: Mapped[str] = mapped_column(String(32), nullable=False)
    long_url: Mapped[str] = mapped_column(Text, nullable=False)
    custom_alias: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    click_count: Mapped[int] = mapped_column(BIGINT_ID_TYPE, nullable=False, default=0)
    last_clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    preview_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    qr_svg: Mapped[str | None] = mapped_column(Text, nullable=True)
    manage_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    owner = relationship("User", back_populates="links")
    click_events = relationship("ClickEvent", back_populates="link", cascade="all, delete-orphan")
    daily_stats = relationship("LinkDailyStat", back_populates="link", cascade="all, delete-orphan")
