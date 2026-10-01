"""Persist the accepted per-night reservation price snapshot."""

from alembic import op
import sqlalchemy as sa

revision = "0006_reservation_price_snapshot"
down_revision = "0005_reservation_rate_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reservations", sa.Column("pricing_details", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("reservations", "pricing_details")