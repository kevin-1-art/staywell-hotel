"""Store applied promotion and corporate booking context."""

from alembic import op
import sqlalchemy as sa

revision = "0005_reservation_rate_context"
down_revision = "0004_rates_inventory_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reservations", sa.Column("promo_code", sa.String(32), nullable=True))
    op.add_column("reservations", sa.Column("company_name", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("reservations", "company_name")
    op.drop_column("reservations", "promo_code")