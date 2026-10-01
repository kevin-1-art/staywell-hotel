from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user, require_roles
from app.models import Folio, FolioCharge, FolioPayment, Guest, Reservation, Role, Room, User
from app.schemas import GuestCreate, GuestFlagsUpdate, GuestView

router = APIRouter(prefix="/guests", tags=["Guests"])
write_roles = (Role.ADMIN, Role.MANAGER, Role.FRONT_DESK)


@router.get("")
def list_guests(
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_roles(*write_roles, Role.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    query = select(Guest)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(Guest.first_name.ilike(pattern), Guest.last_name.ilike(pattern), Guest.email.ilike(pattern), Guest.phone.ilike(pattern))
        )
    count_statement = select(func.count()).select_from(query.subquery())
    total = db.scalar(count_statement) or 0
    guests = db.scalars(query.order_by(Guest.last_name, Guest.first_name).limit(limit).offset(offset)).all()
    return {"items": guests, "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=GuestView, status_code=status.HTTP_201_CREATED)
def create_guest(
    payload: GuestCreate,
    _: User = Depends(require_roles(*write_roles)),
    db: Session = Depends(get_db),
):
    conditions = []
    if payload.email:
        conditions.append(func.lower(Guest.email) == str(payload.email).lower())
    if payload.phone:
        conditions.append(Guest.phone == payload.phone)
    if conditions and db.scalar(select(Guest).where(or_(*conditions))):
        raise HTTPException(status_code=409, detail="A guest with this email or phone already exists")
    guest = Guest(
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        email=str(payload.email).lower() if payload.email else None,
        phone=payload.phone,
        id_document_number=payload.id_document_number,
    )
    db.add(guest)
    db.commit()
    db.refresh(guest)
    return guest


@router.get("/{guest_id}", response_model=GuestView)
def get_guest(guest_id: str, _: User = Depends(require_roles(*write_roles, Role.ACCOUNTANT)), db: Session = Depends(get_db)):
    guest = db.get(Guest, guest_id)
    if guest is None:
        raise HTTPException(status_code=404, detail="Guest not found")
    return guest


@router.patch("/{guest_id}/flags", response_model=GuestView)
def update_guest_flags(
    guest_id: str,
    payload: GuestFlagsUpdate,
    _: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)),
    db: Session = Depends(get_db),
):
    guest = db.get(Guest, guest_id)
    if guest is None:
        raise HTTPException(status_code=404, detail="Guest not found")
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(guest, name, value)
    db.commit()
    return guest


@router.get("/{guest_id}/history")
def guest_history(
    guest_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_roles(*write_roles, Role.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    guest = db.get(Guest, guest_id)
    if guest is None:
        raise HTTPException(status_code=404, detail="Guest not found")
    query = select(Reservation).where(Reservation.guest_id == guest_id)
    total = len(db.scalars(query).all())
    stays = db.scalars(query.order_by(Reservation.check_in.desc()).limit(limit).offset(offset)).all()
    history = []
    for stay in stays:
        room = db.get(Room, stay.room_id)
        folio = db.scalar(select(Folio).where(Folio.reservation_id == stay.id))
        charge_total = 0
        payment_total = 0
        if folio:
            charge_total = db.scalar(select(func.coalesce(func.sum(FolioCharge.quantity * FolioCharge.unit_amount_ugx), 0)).where(FolioCharge.folio_id == folio.id)) or 0
            payment_total = db.scalar(select(func.coalesce(func.sum(FolioPayment.amount_ugx), 0)).where(FolioPayment.folio_id == folio.id, FolioPayment.is_refund.is_(False))) or 0
        history.append({"reservation_id": stay.id, "confirmation_code": stay.confirmation_code,
                        "room_number": room.number, "check_in": stay.check_in, "check_out": stay.check_out,
                        "status": stay.status, "source": stay.source, "charges_ugx": charge_total,
                        "payments_ugx": payment_total})
    return {"guest": guest, "items": history, "total": total, "limit": limit, "offset": offset}