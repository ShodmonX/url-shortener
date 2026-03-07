from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.link import AnalyticsPoint


class AppSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    has_next: bool


class OwnedLinkSummary(AppSchema):
    id: UUID
    original_url: str
    short_code: str
    created_at: datetime
    expires_at: datetime | None
    total_clicks: int


class MyUrlsResponse(BaseModel):
    items: list[OwnedLinkSummary]
    pagination: PaginationMeta


class DimensionCount(BaseModel):
    value: str
    count: int


class UrlStatsResponse(BaseModel):
    id: UUID
    short_code: str
    original_url: str
    total_clicks: int
    created_at: datetime
    expires_at: datetime | None
    last_clicked_at: datetime | None
    daily_clicks: list[AnalyticsPoint]
    top_referrers: list[DimensionCount] = Field(default_factory=list)
    top_countries: list[DimensionCount] = Field(default_factory=list)
    top_devices: list[DimensionCount] = Field(default_factory=list)
