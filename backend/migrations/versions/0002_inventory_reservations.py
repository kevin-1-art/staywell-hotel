"""Create room inventory, guests, and reservations."""

from alembic import op
import sqlalchemy as sa

revision = "0002_inventory_reservations"
down_revision = "0001_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "room_types",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("base_rate_ugx", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "rooms",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("number", sa.String(12), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False),
        sa.Column("room_type_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("notes", sa.String(500), nullable=False),
        sa.ForeignKeyConstraint(["room_type_id"], ["room_types.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number"),
    )
    op.create_index("ix_rooms_floor_status", "rooms", ["floor", "status"])
    op.create_index("ix_rooms_room_type_id", "rooms", ["room_type_id"])
    op.create_index("ix_rooms_status", "rooms", ["status"])
    op.create_table(
        "guests",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("first_name", sa.String(80), nullable=False),
        sa.Column("last_name", sa.String(80), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("id_document_number", sa.String(80), nullable=True),
        sa.Column("is_vip", sa.Boolean(), nullable=False),
        sa.Column("is_blacklisted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guests_email", "guests", ["email"])
    op.create_index("ix_guests_name", "guests", ["last_name", "first_name"])
    op.create_index("ix_guests_phone", "guests", ["phone"])
    op.create_table(
        "reservations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("confirmation_code", sa.String(12), nullable=False),
        sa.Column("guest_id", sa.String(36), nullable=False),
        sa.Column("room_id", sa.String(36), nullable=False),
        sa.Column("check_in", sa.Date(), nullable=False),
        sa.Column("check_out", sa.Date(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("nightly_rate_ugx", sa.Integer(), nullable=False),
        sa.Column("deposit_ugx", sa.Integer(), nullable=False),
        sa.Column("special_requests", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("confirmation_code"),
    )
    op.create_index("ix_reservations_confirmation_code", "reservations", ["confirmation_code"])
    op.create_index("ix_reservations_guest_id", "reservations", ["guest_id"])
    op.create_index("ix_reservations_room_id", "reservations", ["room_id"])
    op.create_index("ix_reservations_stay_dates", "reservations", ["check_in", "check_out"])
    op.create_index("ix_reservations_status_check_in", "reservations", ["status", "check_in"])
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        "ALTER TABLE reservations ADD CONSTRAINT ex_reservations_room_stay_no_overlap "
        "EXCLUDE USING gist (room_id WITH =, daterange(check_in, check_out, '[)') WITH &&) "
        "WHERE (status IN ('confirmed', 'checked_in'))"
    )


def downgrade() -> None:
    op.drop_table("reservations")
    op.drop_table("guests")
    op.drop_table("rooms")
    op.drop_table("room_types")