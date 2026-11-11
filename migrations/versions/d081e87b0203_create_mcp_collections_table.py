"""create mcp_collections table

Revision ID: d081e87b0203
Revises: b55caf8981e1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d081e87b0203"
down_revision: Union[str, Sequence[str], None] = "b55caf8981e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_collections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_mcp_collections_tenant_id",
        "mcp_collections",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mcp_collections_tenant_id",
        table_name="mcp_collections",
    )
    op.drop_table("mcp_collections")
