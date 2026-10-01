"""Add configurable rates, hotel settings, inventory, and notifications."""

from alembic import op
import sqlalchemy as sa

revision = "0004_rates_inventory_notifications"
down_revision = "0003_stays_billing_housekeeping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hotel_settings",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_by_id", sa.String(36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "rate_rules",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("rule_type", sa.String(24), nullable=False),
        sa.Column("room_type_id", sa.String(36), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("adjustment_type", sa.String(16), nullable=False),
        sa.Column("adjustment_value", sa.Integer(), nullable=False),
        sa.Column("promo_code", sa.String(32), nullable=True),
        sa.Column("company_name", sa.String(120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["room_type_id"], ["room_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_rules_dates_active", "rate_rules", ["starts_on", "ends_on", "is_active"])
    op.create_index("ix_rate_rules_promo_code", "rate_rules", ["promo_code"])
    op.create_index("ix_rate_rules_room_type_id", "rate_rules", ["room_type_id"])
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("sku", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("quantity_on_hand", sa.Integer(), nullable=False),
        sa.Column("reorder_level", sa.Integer(), nullable=False),
        sa.Column("unit_cost_ugx", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku"),
    )
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["item_id"], ["inventory_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_movements_item_id", "stock_movements", ["item_id"])
    op.create_index("ix_stock_movements_item_created", "stock_movements", ["item_id", "created_at"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_user_read_created", "notifications", ["user_id", "read_at", "created_at"])
    op.execute(
        "INSERT INTO hotel_settings (key, value, updated_at) VALUES "
        "('property', '{\"name\": \"Staywell Kampala\", \"currency\": \"UGX\", \"usd_rate_ugx\": 3700}', now()), "
        "('charges', '{\"tax_basis_points\": 1800, \"service_basis_points\": 500}', now())"
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("stock_movements")
    op.drop_table("inventory_items")
    op.drop_table("rate_rules")
    op.drop_table("hotel_settings")