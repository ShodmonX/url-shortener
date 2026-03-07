import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import BIGINT_ID_TYPE


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email"),)

    id: Mapped[int] = mapped_column(BIGINT_ID_TYPE, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, nullable=False, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    links = relationship("Link", back_populates="owner")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
