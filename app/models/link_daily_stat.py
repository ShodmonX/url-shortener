from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import BIGINT_ID_TYPE


class LinkDailyStat(Base):
    __tablename__ = "link_daily_stats"
    __table_args__ = (UniqueConstraint("link_id", "bucket_date", name="uq_link_daily_stats_bucket"),)

    id: Mapped[int] = mapped_column(BIGINT_ID_TYPE, primary_key=True, autoincrement=True)
    link_id: Mapped[int] = mapped_column(
        BIGINT_ID_TYPE,
        ForeignKey("links.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_visitors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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

    link = relationship("Link", back_populates="daily_stats")
