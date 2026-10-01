from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user, require_roles
from app.models import Reservation, ReservationStatus, Role, Room, RoomStatus, RoomType, User
from app.schemas import RoomCreate, RoomStatusUpdate, RoomTypeView, RoomView

router = APIRouter(prefix="/rooms", tags=["Rooms"])
room_roles = (Role.ADMIN, Role.MANAGER, Role.FRONT_DESK, Role.HOUSEKEEPING)


def room_view(room: Room, room_type: RoomType) -> RoomView:
    return RoomView(
        id=room.id,
        number=room.number,
        floor=room.floor,
        room_type_id=room.room_type_id,
        room_type_name=room_type.name,
        status=room.status,
        notes=room.notes,
    )


@router.get("/types", response_model=list[RoomTypeView])
def room_types(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(RoomType).order_by(RoomType.name)).all()


@router.get("")
def list_rooms(
    floor: int | None = Query(default=None, ge=0, le=99),
    room_type_id: str | None = None,
    room_status: RoomStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_roles(*room_roles, Role.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    query = select(Room, RoomType).join(RoomType, Room.room_type_id == RoomType.id)
    if floor is not None:
        query = query.where(Room.floor == floor)
    if room_type_id:
        query = query.where(Room.room_type_id == room_type_id)
    if room_status:
        query = query.where(Room.status == room_status.value)
    count_query = select(Room.id)
    if floor is not None:
        count_query = count_query.where(Room.floor == floor)
    if room_type_id:
        count_query = count_query.where(Room.room_type_id == room_type_id)
    if room_status:
        count_query = count_query.where(Room.status == room_status.value)
    total = len(db.scalars(count_query).all())
    rows = db.execute(query.order_by(Room.floor, Room.number).limit(limit).offset(offset)).all()
    return {"items": [room_view(room, room_type) for room, room_type in rows], "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=RoomView, status_code=status.HTTP_201_CREATED)
def create_room(
    payload: RoomCreate,
    _: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)),
    db: Session = Depends(get_db),
):
    if db.scalar(select(Room).where(Room.number == payload.number)):
        raise HTTPException(status_code=409, detail="Room number already exists")
    room_type = db.get(RoomType, payload.room_type_id)
    if room_type is None:
        raise HTTPException(status_code=404, detail="Room type not found")
    room = Room(**payload.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room_view(room, room_type)


@router.patch("/{room_id}/status", response_model=RoomView)
def update_room_status(
    room_id: str,
    payload: RoomStatusUpdate,
    user: User = Depends(require_roles(*room_roles)),
    db: Session = Depends(get_db),
):
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    try:
        next_status = RoomStatus(payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid room status") from exc
    if next_status == RoomStatus.OCCUPIED and user.role == Role.HOUSEKEEPING.value:
        raise HTTPException(status_code=403, detail="Housekeeping cannot occupy rooms")
    room.status = next_status.value
    if payload.notes is not None:
        room.notes = payload.notes
    db.commit()
    room_type = db.get(RoomType, room.room_type_id)
    return room_view(room, room_type)