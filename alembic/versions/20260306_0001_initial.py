"""initial schema

Revision ID: 20260306_0001
Revises:
Create Date: 2026-03-06 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260306_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "links",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("short_code", sa.String(length=32), nullable=False),
        sa.Column("long_url", sa.Text(), nullable=False),
        sa.Column("custom_alias", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("click_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("preview_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("qr_svg", sa.Text(), nullable=True),
        sa.Column("manage_token_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("short_code"),
    )
    op.create_index("ix_links_active_created_at", "links", ["is_active", "created_at"], unique=False)
    op.create_index("ix_links_expires_at", "links", ["expires_at"], unique=False)
    op.create_index("ix_links_short_code", "links", ["short_code"], unique=False)

    op.create_table(
        "click_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_id", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("referer", sa.String(length=1024), nullable=True),
        sa.Column("user_agent", sa.String(length=1024), nullable=True),
        sa.Column("client_ip_hash", sa.String(length=128), nullable=False),
        sa.Column("country_code", sa.String(length=8), nullable=True),
        sa.Column("cache_status", sa.String(length=32), nullable=False, server_default=sa.text("'db'")),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index("ix_click_events_client_ip_hash", "click_events", ["client_ip_hash"], unique=False)
    op.create_index("ix_click_events_link_id", "click_events", ["link_id"], unique=False)
    op.create_index("ix_click_events_link_occurred_at", "click_events", ["link_id", "occurred_at"], unique=False)
    op.create_index("ix_click_events_occurred_at", "click_events", ["occurred_at"], unique=False)

    op.create_table(
        "link_daily_stats",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("link_id", sa.BigInteger(), nullable=False),
        sa.Column("bucket_date", sa.Date(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("unique_visitors", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("link_id", "bucket_date", name="uq_link_daily_stats_bucket"),
    )
    op.create_index("ix_link_daily_stats_link_id", "link_daily_stats", ["link_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_link_daily_stats_link_id", table_name="link_daily_stats")
    op.drop_table("link_daily_stats")
    op.drop_index("ix_click_events_occurred_at", table_name="click_events")
    op.drop_index("ix_click_events_link_occurred_at", table_name="click_events")
    op.drop_index("ix_click_events_link_id", table_name="click_events")
    op.drop_index("ix_click_events_client_ip_hash", table_name="click_events")
    op.drop_table("click_events")
    op.drop_index("ix_links_short_code", table_name="links")
    op.drop_index("ix_links_expires_at", table_name="links")
    op.drop_index("ix_links_active_created_at", table_name="links")
    op.drop_table("links")
