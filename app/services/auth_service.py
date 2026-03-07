from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    TokenDecodeError,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_refresh_token_id,
    hash_password,
    verify_password,
)
from app.core.config import settings
from app.core.security import hash_client_ip
from app.models import RefreshToken, User
from app.services.exceptions import (
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    UserAlreadyExistsError,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    async def _get_user_by_email(self, email: str) -> User | None:
        statement: Select[tuple[User]] = select(User).where(User.email == self.normalize_email(email))
        return await self.db.scalar(statement)

    async def _issue_token_pair(
        self,
        user: User,
        *,
        user_agent: str | None,
        client_ip: str | None,
    ) -> TokenPair:
        refresh_jti = generate_refresh_token_id()
        access_token, access_expires_at = create_access_token(user_id=user.id, user_public_id=user.public_id)
        refresh_token, refresh_expires_at = create_refresh_token(
            user_id=user.id,
            user_public_id=user.public_id,
            jti=refresh_jti,
        )

        self.db.add(
            RefreshToken(
                jti=refresh_jti,
                user_id=user.id,
                expires_at=refresh_expires_at,
                user_agent=(user_agent or "")[:512] or None,
                issued_ip_hash=hash_client_ip(client_ip) if client_ip else None,
            )
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_expires_at=access_expires_at,
            refresh_token_expires_at=refresh_expires_at,
        )

    async def register(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None,
        client_ip: str | None,
    ) -> tuple[User, TokenPair]:
        normalized_email = self.normalize_email(email)
        if await self._get_user_by_email(normalized_email):
            raise UserAlreadyExistsError(normalized_email)

        if len(password) < settings.password_min_length:
            raise ValueError(f"password must be at least {settings.password_min_length} characters long")

        user = User(email=normalized_email, password_hash=hash_password(password))
        self.db.add(user)
        await self.db.flush()

        token_pair = await self._issue_token_pair(user, user_agent=user_agent, client_ip=client_ip)
        await self.db.commit()
        await self.db.refresh(user)
        return user, token_pair

    async def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None,
        client_ip: str | None,
    ) -> tuple[User, TokenPair]:
        user = await self._get_user_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("invalid email or password")
        if not user.is_active:
            raise InactiveUserError("user account is inactive")

        token_pair = await self._issue_token_pair(user, user_agent=user_agent, client_ip=client_ip)
        await self.db.commit()
        await self.db.refresh(user)
        return user, token_pair

    async def authenticate_access_token(self, access_token: str) -> User:
        try:
            payload = decode_token(access_token, expected_type="access")
            user_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError, TokenDecodeError, TokenExpiredError) as exc:
            raise InvalidAccessTokenError("invalid or expired access token") from exc
        user = await self.db.scalar(select(User).where(User.id == user_id))
        if user is None or not user.is_active:
            raise InvalidAccessTokenError("invalid or expired access token")
        return user

    async def refresh(
        self,
        *,
        refresh_token: str,
        user_agent: str | None,
        client_ip: str | None,
    ) -> tuple[User, TokenPair]:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
            user_id = int(payload["sub"])
            refresh_jti = UUID(payload["jti"])
        except (KeyError, TypeError, ValueError, TokenDecodeError, TokenExpiredError) as exc:
            raise InvalidRefreshTokenError("invalid or expired refresh token") from exc

        statement: Select[tuple[RefreshToken]] = select(RefreshToken).where(
            RefreshToken.jti == refresh_jti,
            RefreshToken.user_id == user_id,
        )
        token_record = await self.db.scalar(statement)
        expires_at = normalize_datetime(token_record.expires_at) if token_record is not None else None
        if token_record is None or token_record.revoked_at is not None or expires_at is None or expires_at <= utcnow():
            raise InvalidRefreshTokenError("invalid or expired refresh token")

        user = await self.db.scalar(select(User).where(User.id == user_id))
        if user is None or not user.is_active:
            raise InvalidRefreshTokenError("invalid or expired refresh token")

        new_token_pair = await self._issue_token_pair(user, user_agent=user_agent, client_ip=client_ip)
        new_payload = decode_token(new_token_pair.refresh_token, expected_type="refresh")
        token_record.revoked_at = utcnow()
        token_record.last_used_at = utcnow()
        token_record.replaced_by_jti = UUID(new_payload["jti"])

        await self.db.commit()
        await self.db.refresh(user)
        return user, new_token_pair

    async def logout(self, *, refresh_token: str) -> None:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
            user_id = int(payload["sub"])
            refresh_jti = UUID(payload["jti"])
        except (KeyError, TypeError, ValueError, TokenDecodeError, TokenExpiredError) as exc:
            raise InvalidRefreshTokenError("invalid or expired refresh token") from exc
        statement: Select[tuple[RefreshToken]] = select(RefreshToken).where(
            RefreshToken.jti == refresh_jti,
            RefreshToken.user_id == user_id,
        )
        token_record = await self.db.scalar(statement)
        if token_record is None:
            raise InvalidRefreshTokenError("invalid or expired refresh token")
        if token_record.revoked_at is None:
            token_record.revoked_at = utcnow()
            token_record.last_used_at = utcnow()
            await self.db.commit()
