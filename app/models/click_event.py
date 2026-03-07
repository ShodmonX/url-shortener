import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import BIGINT_ID_TYPE


class ClickEvent(Base):
    __tablename__ = "click_events"
    __table_args__ = (
        Index("ix_click_events_link_occurred_at", "link_id", "occurred_at"),
        Index("ix_click_events_occurred_at", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID_TYPE, primary_key=True, autoincrement=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        unique=True,
        nullable=False,
        default=uuid.uuid4,
    )
    link_id: Mapped[int] = mapped_column(
        BIGINT_ID_TYPE,
        ForeignKey("links.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    referer: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    client_ip_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cache_status: Mapped[str] = mapped_column(String(32), nullable=False, default="db")

    link = relationship("Link", back_populates="click_events")
