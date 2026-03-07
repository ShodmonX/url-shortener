"""add auth and ownership

Revision ID: 20260306_0002
Revises: 20260306_0001
Create Date: 2026-03-06 00:30:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260306_0002"
down_revision = "20260306_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("jti", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("replaced_by_jti", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("issued_ip_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti"),
    )
    op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"], unique=False)
    op.create_index("ix_refresh_tokens_user_expires_at", "refresh_tokens", ["user_id", "expires_at"], unique=False)

    op.add_column("links", sa.Column("user_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_links_user_id_users", "links", "users", ["user_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_links_user_created_at", "links", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_links_user_created_at", table_name="links")
    op.drop_constraint("fk_links_user_id_users", "links", type_="foreignkey")
    op.drop_column("links", "user_id")
    op.drop_index("ix_refresh_tokens_user_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_jti", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
