"""Add stays, folios, payments, housekeeping, maintenance, and audit."""

from alembic import op
import sqlalchemy as sa

revision = "0003_stays_billing_housekeeping"
down_revision = "0002_inventory_reservations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reservations", sa.Column("id_document_type", sa.String(32), nullable=True))
    op.add_column("reservations", sa.Column("id_document_number", sa.String(80), nullable=True))
    op.add_column("reservations", sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reservations", sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reservations", sa.Column("early_check_in_fee_ugx", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("reservations", sa.Column("late_check_out_fee_ugx", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("reservations", sa.Column("checkout_override_reason", sa.Text(), nullable=True))
    op.create_table(
        "folios",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("reservation_id", sa.String(36), nullable=False),
        sa.Column("invoice_number", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reservation_id"),
        sa.UniqueConstraint("invoice_number"),
    )
    op.create_table(
        "folio_charges",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("folio_id", sa.String(36), nullable=False),
        sa.Column("description", sa.String(160), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_amount_ugx", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["folio_id"], ["folios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_folio_charges_folio_id", "folio_charges", ["folio_id"])
    op.create_index("ix_folio_charges_folio_created", "folio_charges", ["folio_id", "created_at"])
    op.create_table(
        "folio_payments",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("folio_id", sa.String(36), nullable=False),
        sa.Column("amount_ugx", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(24), nullable=False),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column("is_refund", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["folio_id"], ["folios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_folio_payments_folio_id", "folio_payments", ["folio_id"])
    op.create_index("ix_folio_payments_folio_created", "folio_payments", ["folio_id", "created_at"])
    op.create_table(
        "invoice_counter",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO invoice_counter (id, next_number) VALUES (1, 100001)")
    op.create_table(
        "housekeeping_tasks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("room_id", sa.String(36), nullable=False),
        sa.Column("reservation_id", sa.String(36), nullable=True),
        sa.Column("assigned_to_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_housekeeping_tasks_room_id", "housekeeping_tasks", ["room_id"])
    op.create_index("ix_housekeeping_tasks_assigned_to_id", "housekeeping_tasks", ["assigned_to_id"])
    op.create_index("ix_housekeeping_tasks_status_created", "housekeeping_tasks", ["status", "created_at"])
    op.create_table(
        "maintenance_tickets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("room_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("opened_by_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["opened_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_tickets_room_id", "maintenance_tickets", ["room_id"])
    op.create_index("ix_maintenance_tickets_status", "maintenance_tickets", ["status"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(48), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id", "created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("maintenance_tickets")
    op.drop_table("housekeeping_tasks")
    op.drop_table("invoice_counter")
    op.drop_table("folio_payments")
    op.drop_table("folio_charges")
    op.drop_table("folios")
    for column in (
        "checkout_override_reason", "late_check_out_fee_ugx", "early_check_in_fee_ugx",
        "checked_out_at", "checked_in_at", "id_document_number", "id_document_type",
    ):
        op.drop_column("reservations", column)