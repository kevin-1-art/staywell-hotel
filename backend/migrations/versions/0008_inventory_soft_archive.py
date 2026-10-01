"""Add soft archival for inventory items."""

from alembic import op
import sqlalchemy as sa

revision = "0008_inventory_soft_archive"
down_revision = "0007_user_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_items", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("inventory_items", sa.Column("archived_by_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_inventory_items_archived_by_id_users", "inventory_items", "users", ["archived_by_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_inventory_items_archived_at", "inventory_items", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_inventory_items_archived_at", table_name="inventory_items")
    op.drop_constraint("fk_inventory_items_archived_by_id_users", "inventory_items", type_="foreignkey")
    op.drop_column("inventory_items", "archived_by_id")
    op.drop_column("inventory_items", "archived_at")