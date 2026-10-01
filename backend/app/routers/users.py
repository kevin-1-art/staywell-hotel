from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.models import AuditLog, RefreshSession, Role, User
from app.rbac import ROLE_DETAILS
from app.schemas import AdminUserCreate, AdminUserUpdate, AdminUserView
from app.security import hash_password

router = APIRouter(prefix="/admin", tags=["Staff administration"])
admin = require_roles(Role.ADMIN)


@router.get("/roles")
def list_roles(_: User = Depends(admin)) -> list[dict]:
    return [{"key": role.value, **ROLE_DETAILS[role.value]} for role in Role]


@router.get("/users")
def list_users(
    search: str | None = Query(default=None, max_length=100),
    role: Role | None = None,
    active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(admin),
    db: Session = Depends(get_db),
):
    query = select(User)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
    if role:
        query = query.where(User.role == role.value)
    if active is not None:
        query = query.where(User.is_active.is_(active))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    users = db.scalars(query.order_by(User.full_name, User.email).limit(limit).offset(offset)).all()
    return {"items": [AdminUserView.model_validate(user) for user in users], "total": total, "limit": limit, "offset": offset}


@router.get("/users/{user_id}", response_model=AdminUserView)
def get_user(user_id: str, _: User = Depends(admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Staff account not found")
    return user


@router.post("/users", response_model=AdminUserView, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreate,
    actor: User = Depends(admin),
    db: Session = Depends(get_db),
):
    email = str(payload.email).lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="An account already exists for this email")
    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(AuditLog(actor_id=actor.id, action="user.created", entity_type="user", entity_id=user.id, details={"email": user.email, "role": user.role}))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account already exists for this email") from exc
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=AdminUserView)
def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    actor: User = Depends(admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Staff account not found")
    if target.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Deleted accounts cannot be changed")
    changes = payload.model_dump(exclude_unset=True)
    if "email" in changes:
        email = str(changes["email"]).lower()
        duplicate = db.scalar(
            select(User.id).where(func.lower(User.email) == email, User.id != target.id)
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="An account already exists for this email")
        changes["email"] = email
    if "full_name" in changes and changes["full_name"] is not None:
        changes["full_name"] = changes["full_name"].strip()
    if target.id == actor.id and (changes.get("is_active") is False or changes.get("role", Role.ADMIN.value) != Role.ADMIN.value):
        raise HTTPException(status_code=409, detail="You cannot deactivate or demote your own administrator account")
    removing_admin = target.role == Role.ADMIN.value and target.is_active and (
        changes.get("is_active") is False or changes.get("role", Role.ADMIN.value) != Role.ADMIN.value
    )
    if removing_admin:
        other_admins = db.scalar(
            select(func.count()).select_from(User).where(
                User.role == Role.ADMIN.value,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.id != target.id,
            )
        ) or 0
        if other_admins == 0:
            raise HTTPException(status_code=409, detail="At least one active administrator must remain")
    previous = {"email": target.email, "full_name": target.full_name, "role": target.role, "is_active": target.is_active}
    password_changed = "password" in changes and changes["password"] is not None
    for field, value in changes.items():
        if field == "password":
            target.password_hash = hash_password(value)
        else:
            setattr(target, field, value)
    access_changed = target.role != previous["role"] or (target.is_active is False and previous["is_active"])
    if password_changed or access_changed or target.email != previous["email"]:
        db.execute(
            update(RefreshSession)
            .where(RefreshSession.user_id == target.id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="user.updated",
            entity_type="user",
            entity_id=target.id,
            details={
                "before": previous,
                "after": {"email": target.email, "full_name": target.full_name, "role": target.role, "is_active": target.is_active},
                "password_changed": password_changed,
            },
        )
    )
    db.commit()
    db.refresh(target)
    return target


@router.delete("/users/{user_id}", response_model=AdminUserView)
def delete_user(
    user_id: str,
    actor: User = Depends(admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Staff account not found")
    if target.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Staff account has already been deleted")
    if target.id == actor.id:
        raise HTTPException(status_code=409, detail="You cannot delete your own administrator account")
    if target.role == Role.ADMIN.value and target.is_active:
        other_admins = db.scalar(
            select(func.count()).select_from(User).where(
                User.role == Role.ADMIN.value,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.id != target.id,
            )
        ) or 0
        if other_admins == 0:
            raise HTTPException(status_code=409, detail="At least one active administrator must remain")
    previous = {"role": target.role, "is_active": target.is_active}
    now = datetime.now(timezone.utc)
    target.is_active = False
    target.deleted_at = now
    db.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == target.id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="user.deleted",
            entity_type="user",
            entity_id=target.id,
            details={"email": target.email, "before": previous, "deleted_at": now.isoformat()},
        )
    )
    db.commit()
    db.refresh(target)
    return target