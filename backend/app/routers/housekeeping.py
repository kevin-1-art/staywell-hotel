from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.models import HousekeepingTask, Role, Room, RoomStatus, User

router = APIRouter(prefix="/housekeeping", tags=["Housekeeping"])
task_roles = (Role.ADMIN, Role.MANAGER, Role.FRONT_DESK, Role.HOUSEKEEPING)


def task_view(task: HousekeepingTask, room: Room, assignee: User | None) -> dict:
    return {
        "id": task.id,
        "room_id": task.room_id,
        "room_number": room.number,
        "floor": room.floor,
        "reservation_id": task.reservation_id,
        "assigned_to_id": task.assigned_to_id,
        "assigned_to_name": assignee.full_name if assignee else None,
        "status": task.status,
        "notes": task.notes,
        "created_at": task.created_at.isoformat(),
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


@router.get("")
def list_tasks(
    task_status: str | None = Query(default=None, alias="status"),
    mine: bool = False,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_roles(*task_roles)),
    db: Session = Depends(get_db),
):
    query = select(HousekeepingTask).join(Room, Room.id == HousekeepingTask.room_id)
    if task_status:
        query = query.where(HousekeepingTask.status == task_status)
    if mine or user.role == Role.HOUSEKEEPING.value:
        query = query.where(HousekeepingTask.assigned_to_id == user.id)
    total = len(db.scalars(query).all())
    tasks = db.scalars(query.order_by(HousekeepingTask.created_at).limit(limit).offset(offset)).all()
    return {
        "items": [task_view(task, db.get(Room, task.room_id), db.get(User, task.assigned_to_id) if task.assigned_to_id else None) for task in tasks],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.patch("/{task_id}/assign")
def assign_task(
    task_id: str,
    assigned_to_id: str,
    _: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)),
    db: Session = Depends(get_db),
):
    task = db.get(HousekeepingTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Housekeeping task not found")
    assignee = db.get(User, assigned_to_id)
    if assignee is None or not assignee.is_active or assignee.role != Role.HOUSEKEEPING.value:
        raise HTTPException(status_code=422, detail="Assignment requires an active housekeeping user")
    task.assigned_to_id = assignee.id
    db.commit()
    return task_view(task, db.get(Room, task.room_id), assignee)


@router.post("/{task_id}/start")
def start_task(
    task_id: str,
    user: User = Depends(require_roles(*task_roles)),
    db: Session = Depends(get_db),
):
    task = db.get(HousekeepingTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Housekeeping task not found")
    if user.role == Role.HOUSEKEEPING.value and task.assigned_to_id != user.id:
        raise HTTPException(status_code=403, detail="This task is assigned to another staff member")
    if task.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending tasks can be started")
    task.status = "in_progress"
    room = db.get(Room, task.room_id)
    if room.status == RoomStatus.DIRTY.value:
        room.status = RoomStatus.CLEANING.value
    db.commit()
    return task_view(task, room, db.get(User, task.assigned_to_id) if task.assigned_to_id else None)


@router.post("/{task_id}/complete")
def complete_task(
    task_id: str,
    user: User = Depends(require_roles(*task_roles)),
    db: Session = Depends(get_db),
):
    task = db.get(HousekeepingTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Housekeeping task not found")
    if user.role == Role.HOUSEKEEPING.value and task.assigned_to_id != user.id:
        raise HTTPException(status_code=403, detail="This task is assigned to another staff member")
    if task.status != "in_progress":
        raise HTTPException(status_code=409, detail="Only in-progress tasks can be completed")
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    room = db.get(Room, task.room_id)
    room.status = RoomStatus.INSPECTED.value
    db.commit()
    return task_view(task, room, db.get(User, task.assigned_to_id) if task.assigned_to_id else None)


@router.post("/{task_id}/release")
def release_room(
    task_id: str,
    _: User = Depends(require_roles(Role.ADMIN, Role.MANAGER, Role.FRONT_DESK)),
    db: Session = Depends(get_db),
):
    task = db.get(HousekeepingTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Housekeeping task not found")
    if task.status != "completed":
        raise HTTPException(status_code=409, detail="Room can only be released after inspection")
    room = db.get(Room, task.room_id)
    if room.status != RoomStatus.INSPECTED.value:
        raise HTTPException(status_code=409, detail="Room must be inspected before it can be released")
    room.status = RoomStatus.AVAILABLE.value
    db.commit()
    return {"room_id": room.id, "room_number": room.number, "status": room.status}