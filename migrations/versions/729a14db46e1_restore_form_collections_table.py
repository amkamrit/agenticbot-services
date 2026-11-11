"""restore form_collections table"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "729a14db46e1"
down_revision: str | Sequence[str] | None = "d081e87b0203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    inspector = sa.inspect(conn)

    if not inspector.has_table("form_collections"):
        op.create_table(
            "form_collections",
            sa.Column("id", sa.Integer(), primary_key=True),
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
            "ix_form_collections_tenant_id",
            "form_collections",
            ["tenant_id"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("form_collections"):
        op.drop_index(
            "ix_form_collections_tenant_id",
            table_name="form_collections",
        )
        op.drop_table("form_collections")
