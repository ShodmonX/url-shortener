import json
from functools import lru_cache
from typing import Annotated
from urllib.parse import quote

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "Scalable URL Shortener"
    environment: str = "development"
    debug: bool = Field(default=False, validation_alias=AliasChoices("APP_DEBUG", "DEBUG"))
    api_v1_prefix: str = "/api/v1"
    public_base_url: str = "http://localhost:8000"
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ]
    )
    cors_allowed_methods: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    )
    cors_allowed_headers: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_minutes: int = 15
    jwt_refresh_token_ttl_days: int = 30
    auth_return_refresh_token_in_body: bool = False
    refresh_cookie_name: str = "refresh_token"
    refresh_cookie_domain: str | None = None
    refresh_cookie_path: str = "/api/v1/auth"
    refresh_cookie_secure: bool = False
    refresh_cookie_samesite: str = "lax"
    password_min_length: int = 8
    password_scrypt_n: int = 16384
    password_scrypt_r: int = 8
    password_scrypt_p: int = 1

    database_user: str = Field(
        default="url_shortener",
        validation_alias=AliasChoices("DATABASE_USER", "POSTGRES_USER"),
    )
    database_password: str = Field(
        default="url_shortener",
        validation_alias=AliasChoices("DATABASE_PASSWORD", "POSTGRES_PASSWORD"),
    )
    database_host: str = Field(default="db", validation_alias=AliasChoices("DATABASE_HOST"))
    database_port: int = Field(default=5432, validation_alias=AliasChoices("DATABASE_PORT"))
    database_db: str = Field(
        default="url_shortener",
        validation_alias=AliasChoices("DATABASE_DB", "POSTGRES_DB"),
    )
    db_pool_size: int = 20
    db_max_overflow: int = 40

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redirect_cache_ttl_seconds: int = 86400
    negative_cache_ttl_seconds: int = 60
    cache_ttl_jitter_seconds: int = 300
    local_cache_max_entries: int = 10000
    click_analytics_shards: int = 16

    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_vhost: str = "/"
    rabbitmq_prefetch_count: int = 100
    background_job_max_retries: int = 5
    fallback_queue_poll_timeout_seconds: int = 5

    short_code_length: int = 11
    short_code_max_retries: int = 8
    manage_token_length: int = 32
    forwarded_allow_ips: str = "127.0.0.1"

    rate_limit_window_seconds: int = 60
    rate_limit_create_per_window: int = 30
    rate_limit_manage_per_window: int = 120
    rate_limit_redirect_per_window: int = 6000

    metadata_fetch_timeout_seconds: float = 5.0
    metadata_max_html_bytes: int = 131072
    metadata_max_redirects: int = 5
    metadata_user_agent: str = "url-shortener-preview-bot/1.0"

    default_analytics_days: int = 30
    analytics_recent_events_limit: int = 20

    reserved_aliases: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "api",
            "docs",
            "redoc",
            "openapi.json",
            "healthz",
            "readyz",
            "favicon.ico",
        ]
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def db_async_url(self) -> str:
        return (
            f"postgresql+asyncpg://{quote(self.database_user, safe='')}:{quote(self.database_password, safe='')}"
            f"@{self.database_host}:{self.database_port}/{self.database_db}"
        )

    @property
    def db_sync_url(self) -> str:
        return (
            f"postgresql+psycopg://{quote(self.database_user, safe='')}:{quote(self.database_password, safe='')}"
            f"@{self.database_host}:{self.database_port}/{self.database_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def rabbitmq_url(self) -> str:
        encoded_vhost = quote(self.rabbitmq_vhost, safe="")
        return (
            f"amqp://{quote(self.rabbitmq_user, safe='')}:{quote(self.rabbitmq_password, safe='')}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{encoded_vhost}"
        )

    @property
    def reserved_aliases_set(self) -> set[str]:
        return {alias.lower() for alias in self.reserved_aliases}

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value: object) -> object:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"release", "prod", "production", "0", "false", "no", "off"}:
                return False
            if lowered in {"debug", "dev", "development", "1", "true", "yes", "on"}:
                return True
        return value

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("refresh_cookie_domain", mode="before")
    @classmethod
    def normalize_optional_cookie_domain(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("refresh_cookie_path", mode="before")
    @classmethod
    def normalize_cookie_path(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return "/api/v1/auth"
            if not stripped.startswith("/"):
                return f"/{stripped}"
            return stripped
        return value

    @field_validator("refresh_cookie_samesite", mode="before")
    @classmethod
    def normalize_cookie_samesite(cls, value: object) -> object:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered not in {"lax", "strict", "none"}:
                msg = "REFRESH_COOKIE_SAMESITE must be one of: lax, strict, none"
                raise ValueError(msg)
            return lowered
        return value

    @field_validator(
        "cors_allowed_origins",
        "cors_allowed_methods",
        "cors_allowed_headers",
        "reserved_aliases",
        mode="before",
    )
    @classmethod
    def normalize_csv_settings(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        stripped = value.strip()
        if not stripped:
            return []

        if stripped.startswith("[") and stripped.endswith("]"):
            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                msg = "Expected a JSON array for CORS settings"
                raise ValueError(msg)
            return parsed

        return [item.strip() for item in stripped.split(",") if item.strip()]

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.cors_allow_credentials and "*" in self.cors_allowed_origins:
            msg = "CORS_ALLOWED_ORIGINS cannot contain '*' when credentials are enabled"
            raise ValueError(msg)
        if self.refresh_cookie_samesite == "none" and not self.refresh_cookie_secure:
            msg = "REFRESH_COOKIE_SECURE must be true when REFRESH_COOKIE_SAMESITE is 'none'"
            raise ValueError(msg)

        if self.environment != "production":
            return self

        if self.debug:
            msg = "APP_DEBUG must be false in production"
            raise ValueError(msg)
        if self.secret_key == "change-me-in-production" or len(self.secret_key) < 32:
            msg = "SECRET_KEY must be set to a strong production secret"
            raise ValueError(msg)
        if not self.public_base_url.startswith("https://"):
            msg = "PUBLIC_BASE_URL must use https in production"
            raise ValueError(msg)
        if self.public_base_url.startswith(("http://localhost", "http://127.0.0.1", "https://localhost", "https://127.0.0.1")):
            msg = "PUBLIC_BASE_URL must be a public hostname in production"
            raise ValueError(msg)
        if any(
            origin.startswith(("http://localhost", "http://127.0.0.1", "https://localhost", "https://127.0.0.1"))
            for origin in self.cors_allowed_origins
        ):
            msg = "CORS_ALLOWED_ORIGINS must not include localhost origins in production"
            raise ValueError(msg)
        if self.database_password == "url_shortener":
            msg = "DATABASE_PASSWORD must be changed for production"
            raise ValueError(msg)
        if self.rabbitmq_user == "guest" or self.rabbitmq_password == "guest":
            msg = "RabbitMQ guest credentials are not allowed in production"
            raise ValueError(msg)
        if not self.refresh_cookie_secure:
            msg = "REFRESH_COOKIE_SECURE must be true in production"
            raise ValueError(msg)
        if self.auth_return_refresh_token_in_body:
            msg = "AUTH_RETURN_REFRESH_TOKEN_IN_BODY must be false in production"
            raise ValueError(msg)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]


settings = get_settings()
