from datetime import date, datetime
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class AppSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CreateLinkRequest(BaseModel):
    url: AnyHttpUrl
    custom_alias: str | None = Field(default=None, min_length=4, max_length=32)
    expires_at: datetime | None = None


class AliasAvailabilityResponse(AppSchema):
    alias: str
    available: bool
    reason: str | None = None


class LinkResponse(AppSchema):
    short_code: str
    short_url: str
    url: str
    custom_alias: bool
    expires_at: datetime | None
    metadata_status: str
    created_at: datetime
    manage_token: str


class LinkDetailsResponse(AppSchema):
    short_code: str
    short_url: str
    url: str
    expires_at: datetime | None
    custom_alias: bool
    click_count: int
    last_clicked_at: datetime | None
    metadata_status: str
    preview_metadata: dict[str, Any] | None
    has_qr_code: bool
    created_at: datetime
    updated_at: datetime


class PreviewResponse(AppSchema):
    short_code: str
    status: str
    metadata: dict[str, Any] | None
    updated_at: datetime


class AnalyticsPoint(AppSchema):
    date: date
    clicks: int
    unique_visitors: int


class RecentClickEvent(AppSchema):
    occurred_at: datetime
    referer: str | None
    country_code: str | None
    cache_status: str


class AnalyticsResponse(AppSchema):
    short_code: str
    total_clicks: int
    last_clicked_at: datetime | None
    daily: list[AnalyticsPoint]
    recent_events: list[RecentClickEvent]
