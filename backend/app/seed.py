from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.config import settings
from app.models import (
    AuditLog,
    Folio,
    FolioCharge,
    FolioPayment,
    Guest,
    HotelSetting,
    HousekeepingTask,
    InventoryItem,
    InvoiceCounter,
    MaintenanceTicket,
    Notification,
    RateRule,
    Reservation,
    ReservationStatus,
    Role,
    Room,
    RoomStatus,
    RoomType,
    User,
)
from app.security import hash_password

ROOM_TYPE_DATA = [
    ("STD", "Standard", 2, 180_000, "Queen bed, work desk and courtyard view"),
    ("DLX", "Deluxe", 2, 260_000, "King bed and private balcony"),
    ("TWN", "Twin", 2, 220_000, "Two single beds and quiet garden outlook"),
    ("FAM", "Family Suite", 4, 390_000, "Two rooms with a shared sitting area"),
    ("STE", "Executive Suite", 2, 520_000, "Separate lounge and executive amenities"),
]

USER_DATA = [
    ("admin@staywell.demo", "Amina Admin", Role.ADMIN.value),
    ("manager@staywell.demo", "Moses Manager", Role.MANAGER.value),
    ("frontdesk@staywell.demo", "Ruth Front Desk", Role.FRONT_DESK.value),
    ("housekeeping@staywell.demo", "Grace Housekeeping", Role.HOUSEKEEPING.value),
    ("accountant@staywell.demo", "Peter Accountant", Role.ACCOUNTANT.value),
    ("housekeeping2@staywell.demo", "Daniel Housekeeping", Role.HOUSEKEEPING.value),
]


def seed_data(db: Session, today: date | None = None) -> dict[str, int]:
    if db.scalar(select(func.count()).select_from(User)):
        return {"created": 0}
    today = today or date.today()
    now = datetime.now(timezone.utc)
    initial_password = settings.seed_user_password if settings.app_env.lower() == "production" else "Staywell-Demo-2026!"
    if not initial_password:
        raise RuntimeError("Production seed requires SEED_USER_PASSWORD")
    users = [
        User(email=email, full_name=name, password_hash=hash_password(initial_password), role=role, is_active=True)
        for email, name, role in USER_DATA
    ]
    db.add_all(users)
    db.flush()
    users_by_role = {user.role: user for user in users}
    room_types = [
        RoomType(code=code, name=name, capacity=capacity, base_rate_ugx=rate, description=description)
        for code, name, capacity, rate, description in ROOM_TYPE_DATA
    ]
    db.add_all(room_types)
    db.flush()
    rooms: list[Room] = []
    for floor in range(1, 5):
        for room_index in range(1, 21):
            global_index = (floor - 1) * 20 + room_index - 1
            room_type = room_types[global_index % len(room_types)]
            room_status = RoomStatus.OCCUPIED.value if global_index < 20 else RoomStatus.AVAILABLE.value
            if global_index in {20, 21}:
                room_status = RoomStatus.DIRTY.value
            if global_index == 22:
                room_status = RoomStatus.CLEANING.value
            if global_index == 23:
                room_status = RoomStatus.INSPECTED.value
            room = Room(number=f"{floor}{room_index:02}", floor=floor, room_type_id=room_type.id, status=room_status)
            rooms.append(room)
    db.add_all(rooms)
    db.flush()
    guests = [
        Guest(
            first_name=("Ayo", "Nadia", "Sam", "Leah", "Owen", "Mariam", "Noah", "Irene")[index % 8],
            last_name=f"Guest{index + 1:03}",
            email=f"guest{index + 1:03}@example.com",
            phone=f"+256700{index + 1:06}",
            is_vip=index % 29 == 0,
            is_blacklisted=False,
        )
        for index in range(200)
    ]
    db.add_all(guests)
    db.flush()
    source_values = ("direct", "corporate", "ota", "walk_in")
    payment_methods = ("cash", "card", "bank_transfer", "mobile_money")
    reservations: list[Reservation] = []
    folios: list[Folio] = []
    charges: list[FolioCharge] = []
    payments: list[FolioPayment] = []
    tasks: list[HousekeepingTask] = []
    audit: list[AuditLog] = []
    next_invoice = 100001
    for room_index, room in enumerate(rooms):
        room_type = room_types[room_index % len(room_types)]
        guest = guests[room_index % len(guests)]
        stays = []
        if room_index < 20:
            stays.append((today - timedelta(days=1), today + timedelta(days=2), ReservationStatus.CHECKED_IN.value))
        else:
            end = today - timedelta(days=8 + room_index % 19)
            stays.append((end - timedelta(days=2), end, ReservationStatus.CHECKED_OUT.value))
        stays.append((today + timedelta(days=10 + room_index % 6), today + timedelta(days=12 + room_index % 6), ReservationStatus.CONFIRMED.value))
        stays.append((today + timedelta(days=38 + room_index % 8), today + timedelta(days=41 + room_index % 8), ReservationStatus.CONFIRMED.value))
        if room_index < 60:
            end = today - timedelta(days=46 + room_index % 17)
            stays.append((end - timedelta(days=3), end, ReservationStatus.CHECKED_OUT.value))
        for stay_index, (arrive, depart, stay_status) in enumerate(stays):
            reservation = Reservation(
                confirmation_code=f"SW{room_index + 1:03}{stay_index + 1:02}",
                guest_id=guests[(room_index * 3 + stay_index) % len(guests)].id,
                room_id=room.id,
                check_in=arrive,
                check_out=depart,
                status=stay_status,
                source=source_values[(room_index + stay_index) % len(source_values)],
                nightly_rate_ugx=room_type.base_rate_ugx,
                deposit_ugx=20_000 if stay_status != ReservationStatus.CHECKED_OUT.value else 0,
                special_requests="Quiet room" if room_index % 11 == 0 else "",
                checked_in_at=datetime.combine(arrive, datetime.min.time(), tzinfo=timezone.utc) if stay_status in {ReservationStatus.CHECKED_IN.value, ReservationStatus.CHECKED_OUT.value} else None,
                checked_out_at=datetime.combine(depart, datetime.min.time(), tzinfo=timezone.utc) if stay_status == ReservationStatus.CHECKED_OUT.value else None,
                id_document_type="national_id" if stay_status in {ReservationStatus.CHECKED_IN.value, ReservationStatus.CHECKED_OUT.value} else None,
                id_document_number=f"CM{room_index + 1:08}" if stay_status in {ReservationStatus.CHECKED_IN.value, ReservationStatus.CHECKED_OUT.value} else None,
                created_by_id=users_by_role[Role.FRONT_DESK.value].id,
            )
            if stay_status == ReservationStatus.CHECKED_OUT.value:
                reservation.checkout_override_reason = None
            reservations.append(reservation)
            db.add(reservation)
            db.flush()
            folio = Folio(reservation_id=reservation.id, status="closed" if stay_status == ReservationStatus.CHECKED_OUT.value else "open")
            if stay_status == ReservationStatus.CHECKED_OUT.value:
                folio.invoice_number = next_invoice
                next_invoice += 1
                folio.closed_at = reservation.checked_out_at
            folios.append(folio)
            db.add(folio)
            db.flush()
            nights = (depart - arrive).days
            if stay_status != ReservationStatus.CONFIRMED.value:
                charges.append(FolioCharge(folio_id=folio.id, description=f"Room accommodation ({nights} nights)", category="room", quantity=nights, unit_amount_ugx=room_type.base_rate_ugx, created_by_id=users_by_role[Role.FRONT_DESK.value].id))
            payment_amount = max(20_000, nights * room_type.base_rate_ugx) if stay_status == ReservationStatus.CHECKED_OUT.value else 20_000
            payment_reference = "Reservation deposit" if stay_status == ReservationStatus.CONFIRMED.value else f"SEED-{room_index + 1:03}-{stay_index + 1}"
            payments.append(FolioPayment(folio_id=folio.id, amount_ugx=payment_amount, method="cash" if stay_status == ReservationStatus.CONFIRMED.value else payment_methods[(room_index + stay_index) % len(payment_methods)], reference=payment_reference, is_refund=False, created_by_id=users_by_role[Role.ACCOUNTANT.value].id))
            if stay_status == ReservationStatus.CHECKED_OUT.value:
                tasks.append(HousekeepingTask(room_id=room.id, reservation_id=reservation.id, status="completed", notes="Seeded completed checkout clean", created_at=reservation.checked_out_at, completed_at=reservation.checked_out_at))
            audit.append(AuditLog(actor_id=users_by_role[Role.FRONT_DESK.value].id, action="reservation.created", entity_type="reservation", entity_id=reservation.id, details={"source": reservation.source}))
    db.add_all(charges + payments + tasks + audit)
    for room_index in (20, 21):
        latest_checkout = next(reservation for reservation in reservations if reservation.room_id == rooms[room_index].id and reservation.status == ReservationStatus.CHECKED_OUT.value)
        tasks.append(HousekeepingTask(room_id=rooms[room_index].id, reservation_id=latest_checkout.id, assigned_to_id=users_by_role[Role.HOUSEKEEPING.value].id, status="pending", notes="Turnover clean"))
    db.add_all(tasks[-2:])
    db.add(InvoiceCounter(id=1, next_number=next_invoice))
    db.add_all([
        RateRule(name="Weekend Saver", rule_type="weekend", adjustment_type="percent", adjustment_value=1000),
        RateRule(name="Peak Season", rule_type="seasonal", starts_on=today + timedelta(days=60), ends_on=today + timedelta(days=90), adjustment_type="percent", adjustment_value=1500),
        RateRule(name="WELCOME10", rule_type="promo", adjustment_type="percent", adjustment_value=-1000, promo_code="WELCOME10"),
        RateRule(name="Kampala Corporate", rule_type="corporate", adjustment_type="percent", adjustment_value=-1200, company_name="Kampala Business Group"),
    ])
    db.add_all([
        InventoryItem(sku="LINEN-SHEET", name="Queen bed sheet", unit="piece", quantity_on_hand=24, reorder_level=30, unit_cost_ugx=35_000),
        InventoryItem(sku="AMENITY-SOAP", name="Guest soap", unit="bar", quantity_on_hand=180, reorder_level=100, unit_cost_ugx=1_500),
        InventoryItem(sku="WATER-500", name="Still water 500ml", unit="bottle", quantity_on_hand=48, reorder_level=60, unit_cost_ugx=1_200),
        InventoryItem(sku="COFFEE-UG", name="Ugandan coffee sachet", unit="sachet", quantity_on_hand=310, reorder_level=120, unit_cost_ugx=800),
    ])
    db.add_all([
        HotelSetting(key="property", value={"name": "Staywell Kampala", "currency": "UGX", "usd_rate_ugx": 3700}, updated_by_id=users_by_role[Role.ADMIN.value].id),
        HotelSetting(key="charges", value={"tax_basis_points": 1800, "service_basis_points": 500}, updated_by_id=users_by_role[Role.ADMIN.value].id),
        HotelSetting(key="notifications", value={"email_provider": "console", "sms_provider": "console"}, updated_by_id=users_by_role[Role.ADMIN.value].id),
    ])
    db.add_all([
        Notification(user_id=user.id, category="system", title="Welcome to Staywell", body="Your staff workspace is ready.")
        for user in users
    ])
    db.flush()
    return {"users": len(users), "room_types": len(room_types), "rooms": len(rooms), "guests": len(guests), "reservations": len(reservations), "folios": len(folios), "payments": len(payments), "tasks": len(tasks)}


def main() -> None:
    with SessionLocal() as db, db.begin():
        counts = seed_data(db)
    print(f"Seed complete: {counts}")


if __name__ == "__main__":
    main()