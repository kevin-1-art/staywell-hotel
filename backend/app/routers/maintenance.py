from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.models import AuditLog, MaintenanceTicket, Role, Room, RoomStatus, User

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])
management_roles = (Role.ADMIN, Role.MANAGER, Role.FRONT_DESK)


class TicketCreate(BaseModel):
    room_id: str
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=3000)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")


@router.get("")
def list_tickets(
    ticket_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_roles(Role.ADMIN, Role.MANAGER, Role.FRONT_DESK, Role.HOUSEKEEPING)),
    db: Session = Depends(get_db),
):
    query = select(MaintenanceTicket)
    if ticket_status:
        query = query.where(MaintenanceTicket.status == ticket_status)
    rows = db.scalars(query.order_by(MaintenanceTicket.created_at.desc()).limit(limit).offset(offset)).all()
    return {
        "items": [
            {"id": ticket.id, "room_id": ticket.room_id, "room_number": db.get(Room, ticket.room_id).number,
             "title": ticket.title, "description": ticket.description, "priority": ticket.priority,
             "status": ticket.status, "created_at": ticket.created_at.isoformat(),
             "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None}
            for ticket in rows
        ],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    user: User = Depends(require_roles(*management_roles)),
    db: Session = Depends(get_db),
):
    room = db.get(Room, payload.room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.status == RoomStatus.OCCUPIED.value:
        raise HTTPException(status_code=409, detail="An occupied room cannot be blocked for maintenance")
    room.status = RoomStatus.OUT_OF_ORDER.value
    ticket = MaintenanceTicket(**payload.model_dump(), opened_by_id=user.id)
    db.add(ticket)
    db.flush()
    db.add(AuditLog(actor_id=user.id, action="maintenance.opened", entity_type="maintenance_ticket", entity_id=ticket.id, details={"room_id": room.id, "priority": ticket.priority}))
    db.commit()
    db.refresh(ticket)
    return {"id": ticket.id, "room_id": room.id, "room_number": room.number, "title": ticket.title, "priority": ticket.priority, "status": ticket.status}


@router.post("/{ticket_id}/close")
def close_ticket(
    ticket_id: str,
    user: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)),
    db: Session = Depends(get_db),
):
    ticket = db.get(MaintenanceTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Maintenance ticket not found")
    if ticket.status != "open":
        raise HTTPException(status_code=409, detail="Ticket is already closed")
    ticket.status = "closed"
    ticket.closed_at = datetime.now(timezone.utc)
    room = db.get(Room, ticket.room_id)
    if room.status == RoomStatus.OUT_OF_ORDER.value:
        room.status = RoomStatus.DIRTY.value
    db.add(AuditLog(actor_id=user.id, action="maintenance.closed", entity_type="maintenance_ticket", entity_id=ticket.id, details={"room_id": room.id}))
    db.commit()
    return {"id": ticket.id, "room_id": room.id, "room_status": room.status, "status": ticket.status}