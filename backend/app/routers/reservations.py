import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user, require_roles
from app.models import AuditLog, Guest, HousekeepingTask, Reservation, ReservationStatus, Role, Room, RoomStatus, RoomType, User
from app.pricing import price_stay
from app.schemas import RateQuoteInput, RateQuoteView, ReservationCreate, ReservationView

router = APIRouter(prefix="/reservations", tags=["Reservations"])
booking_roles = (Role.ADMIN, Role.MANAGER, Role.FRONT_DESK)


def reservation_view(reservation: Reservation, guest: Guest, room: Room) -> ReservationView:
    return ReservationView(
        id=reservation.id,
        confirmation_code=reservation.confirmation_code,
        guest_id=guest.id,
        guest_name=f"{guest.first_name} {guest.last_name}",
        room_id=room.id,
        room_number=room.number,
        check_in=reservation.check_in,
        check_out=reservation.check_out,
        status=reservation.status,
        source=reservation.source,
        promo_code=reservation.promo_code,
        company_name=reservation.company_name,
        pricing_details=reservation.pricing_details,
        nightly_rate_ugx=reservation.nightly_rate_ugx,
        deposit_ugx=reservation.deposit_ugx,
        special_requests=reservation.special_requests,
    )


def overlaps(from_date, to_date):
    return and_(Reservation.check_in < to_date, Reservation.check_out > from_date)


@router.post("/rate-quote", response_model=RateQuoteView)
def rate_quote(payload: RateQuoteInput, _: User = Depends(require_roles(*booking_roles)), db: Session = Depends(get_db)):
    room_type = db.get(RoomType, payload.room_type_id)
    if room_type is None:
        raise HTTPException(status_code=404, detail="Room type not found")
    return {
        "room_type_id": room_type.id,
        "room_type_name": room_type.name,
        "base_rate_ugx": room_type.base_rate_ugx,
        **price_stay(db, room_type, payload.check_in, payload.check_out, payload.promo_code, payload.company_name),
    }


@router.get("/availability")
def availability(
    check_in: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
    check_out: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
    room_type_id: str | None = None,
    _: User = Depends(require_roles(*booking_roles)),
    db: Session = Depends(get_db),
):
    from datetime import date

    from_date, to_date = date.fromisoformat(check_in), date.fromisoformat(check_out)
    if to_date <= from_date:
        raise HTTPException(status_code=422, detail="Check-out must be after check-in")
    booked = select(Reservation.room_id).where(
        overlaps(from_date, to_date),
        Reservation.status.in_([ReservationStatus.CONFIRMED.value, ReservationStatus.CHECKED_IN.value]),
    )
    query = select(Room, RoomType).join(RoomType, Room.room_type_id == RoomType.id).where(
        Room.status.not_in([RoomStatus.OUT_OF_ORDER.value, RoomStatus.DIRTY.value, RoomStatus.CLEANING.value]),
        Room.id.not_in(booked),
    )
    if room_type_id:
        query = query.where(Room.room_type_id == room_type_id)
    rooms = db.execute(query.order_by(Room.floor, Room.number)).all()
    return [
        {"id": room.id, "number": room.number, "floor": room.floor, "room_type_id": room.room_type_id,
         "room_type_name": room_type.name, "capacity": room_type.capacity, "base_rate_ugx": room_type.base_rate_ugx,
         "status": room.status}
        for room, room_type in rooms
    ]


@router.get("")
def list_reservations(
    reservation_status: ReservationStatus | None = Query(default=None, alias="status"),
    from_date: str | None = None,
    to_date: str | None = None,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_roles(*booking_roles, Role.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    query = select(Reservation, Guest, Room).join(Guest, Guest.id == Reservation.guest_id).join(Room, Room.id == Reservation.room_id)
    if reservation_status:
        query = query.where(Reservation.status == reservation_status.value)
    if from_date:
        query = query.where(Reservation.check_out > from_date)
    if to_date:
        query = query.where(Reservation.check_in < to_date)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Guest.first_name.ilike(pattern), Guest.last_name.ilike(pattern), Reservation.confirmation_code.ilike(pattern), Room.number.ilike(pattern)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(Reservation.check_in.desc(), Reservation.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [reservation_view(*row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=ReservationView, status_code=status.HTTP_201_CREATED)
def create_reservation(
    payload: ReservationCreate,
    user: User = Depends(require_roles(*booking_roles)),
    db: Session = Depends(get_db),
):
    guest = db.get(Guest, payload.guest_id)
    if guest is None:
        raise HTTPException(status_code=404, detail="Guest not found")
    if guest.is_blacklisted:
        raise HTTPException(status_code=409, detail="This guest is blocked from new reservations")
    room = db.get(Room, payload.room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.status in {RoomStatus.OUT_OF_ORDER.value, RoomStatus.DIRTY.value, RoomStatus.CLEANING.value}:
        raise HTTPException(status_code=409, detail="Room is not ready for new reservations")
    conflict = db.scalar(
        select(Reservation.id).where(
            Reservation.room_id == room.id,
            overlaps(payload.check_in, payload.check_out),
            Reservation.status.in_([ReservationStatus.CONFIRMED.value, ReservationStatus.CHECKED_IN.value]),
        )
    )
    if conflict:
        raise HTTPException(status_code=409, detail="Room is already reserved for these dates")
    room_type = db.get(RoomType, room.room_type_id)
    pricing = price_stay(db, room_type, payload.check_in, payload.check_out, payload.promo_code, payload.company_name)
    if payload.nightly_rate_ugx is not None and payload.nightly_rate_ugx != pricing["average_nightly_rate_ugx"]:
        raise HTTPException(status_code=409, detail="Room rate changed; request a fresh quote")
    if payload.deposit_ugx > pricing["total_ugx"]:
        raise HTTPException(status_code=422, detail="Deposit cannot exceed the quoted total")
    reservation = Reservation(
        confirmation_code=secrets.token_hex(4).upper(),
        guest_id=guest.id,
        room_id=room.id,
        check_in=payload.check_in,
        check_out=payload.check_out,
        status=ReservationStatus.CONFIRMED.value,
        source=payload.source,
        promo_code=payload.promo_code,
        company_name=payload.company_name,
        nightly_rate_ugx=pricing["average_nightly_rate_ugx"],
        pricing_details=pricing,
        deposit_ugx=payload.deposit_ugx,
        special_requests=payload.special_requests,
        created_by_id=user.id,
    )
    db.add(reservation)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Room is already reserved for these dates") from exc
    db.refresh(reservation)
    return reservation_view(reservation, guest, room)


@router.post("/{reservation_id}/cancel", response_model=ReservationView)
def cancel_reservation(
    reservation_id: str,
    _: User = Depends(require_roles(*booking_roles)),
    db: Session = Depends(get_db),
):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.status != ReservationStatus.CONFIRMED.value:
        raise HTTPException(status_code=409, detail="Only confirmed reservations can be cancelled")
    reservation.status = ReservationStatus.CANCELLED.value
    db.commit()
    return reservation_view(reservation, db.get(Guest, reservation.guest_id), db.get(Room, reservation.room_id))


@router.post("/{reservation_id}/no-show", response_model=ReservationView)
def mark_no_show(
    reservation_id: str,
    user: User = Depends(require_roles(*booking_roles)),
    db: Session = Depends(get_db),
):
    from datetime import date

    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.status != ReservationStatus.CONFIRMED.value:
        raise HTTPException(status_code=409, detail="Only confirmed reservations can be marked no-show")
    if reservation.check_in > date.today():
        raise HTTPException(status_code=409, detail="Reservation check-in date has not arrived")
    reservation.status = ReservationStatus.NO_SHOW.value
    db.add(AuditLog(actor_id=user.id, action="reservation.no_show", entity_type="reservation", entity_id=reservation.id, details={"confirmation_code": reservation.confirmation_code}))
    db.commit()
    return reservation_view(reservation, db.get(Guest, reservation.guest_id), db.get(Room, reservation.room_id))


@router.post("/{reservation_id}/move-room", response_model=ReservationView)
def move_reservation_room(
    reservation_id: str,
    room_id: str,
    user: User = Depends(require_roles(*booking_roles)),
    db: Session = Depends(get_db),
):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.status not in {ReservationStatus.CONFIRMED.value, ReservationStatus.CHECKED_IN.value}:
        raise HTTPException(status_code=409, detail="Only active reservations can be moved")
    target = db.get(Room, room_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target room not found")
    if target.id == reservation.room_id:
        return reservation_view(reservation, db.get(Guest, reservation.guest_id), target)
    if target.status not in {RoomStatus.AVAILABLE.value, RoomStatus.INSPECTED.value}:
        raise HTTPException(status_code=409, detail="Target room is not ready for a guest")
    conflict = db.scalar(
        select(Reservation.id).where(
            Reservation.room_id == target.id,
            overlaps(reservation.check_in, reservation.check_out),
            Reservation.status.in_([ReservationStatus.CONFIRMED.value, ReservationStatus.CHECKED_IN.value]),
        )
    )
    if conflict:
        raise HTTPException(status_code=409, detail="Target room is already reserved for these dates")
    previous_room = db.get(Room, reservation.room_id)
    reservation.room_id = target.id
    if reservation.status == ReservationStatus.CHECKED_IN.value:
        previous_room.status = RoomStatus.DIRTY.value
        target.status = RoomStatus.OCCUPIED.value
        db.add(HousekeepingTask(room_id=previous_room.id, reservation_id=reservation.id, status="pending", notes="Room move clean"))
    db.add(AuditLog(actor_id=user.id, action="reservation.room_moved", entity_type="reservation", entity_id=reservation.id, details={"from_room_id": previous_room.id, "to_room_id": target.id}))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Target room is already reserved for these dates") from exc
    return reservation_view(reservation, db.get(Guest, reservation.guest_id), target)