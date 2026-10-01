from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user, require_roles
from app.models import AuditLog, HotelSetting, InventoryItem, Notification, RateRule, Role, StockMovement, User

router = APIRouter(tags=["Rates, inventory, settings, and notifications"])
management_roles = (Role.ADMIN, Role.MANAGER)


class RateRuleInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    rule_type: str = Field(pattern="^(seasonal|weekend|promo|corporate)$")
    room_type_id: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    adjustment_type: str = Field(default="percent", pattern="^(percent|fixed)$")
    adjustment_value: int = Field(ge=-10000, le=100_000_000)
    promo_code: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=120)


class InventoryItemInput(BaseModel):
    sku: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    unit: str = Field(default="unit", max_length=24)
    quantity_on_hand: int = Field(default=0, ge=0)
    reorder_level: int = Field(default=0, ge=0)
    unit_cost_ugx: int = Field(default=0, ge=0, le=100_000_000)


class StockAdjustment(BaseModel):
    quantity_delta: int = Field(ge=-100_000, le=100_000)
    reason: str = Field(min_length=3, max_length=200)

    @field_validator("quantity_delta")
    @classmethod
    def validate_nonzero_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Stock adjustment must change the quantity")
        return value


@router.get("/api/v1/rates")
def list_rates(_: User = Depends(require_roles(*management_roles, Role.FRONT_DESK)), db: Session = Depends(get_db)):
    rules = db.scalars(select(RateRule).order_by(RateRule.rule_type, RateRule.name)).all()
    return rules


@router.post("/api/v1/rates", status_code=status.HTTP_201_CREATED)
def create_rate_rule(
    payload: RateRuleInput,
    _: User = Depends(require_roles(*management_roles)),
    db: Session = Depends(get_db),
):
    if payload.starts_on and payload.ends_on and payload.ends_on <= payload.starts_on:
        raise HTTPException(status_code=422, detail="Rate end date must be after its start date")
    rule = RateRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/api/v1/settings")
def get_settings(_: User = Depends(require_roles(*management_roles, Role.ACCOUNTANT)), db: Session = Depends(get_db)):
    return {setting.key: setting.value for setting in db.scalars(select(HotelSetting).order_by(HotelSetting.key)).all()}


@router.put("/api/v1/settings/{key}")
def update_setting(
    key: str,
    value: dict,
    user: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    if key not in {"property", "charges", "notifications"}:
        raise HTTPException(status_code=404, detail="Setting group not found")
    if key == "property" and value.get("usd_rate_ugx", 0) <= 0:
        raise HTTPException(status_code=422, detail="USD exchange rate must be a positive UGX integer")
    if key == "charges" and any(not isinstance(value.get(field), int) or value[field] < 0 for field in ("tax_basis_points", "service_basis_points")):
        raise HTTPException(status_code=422, detail="Taxes and service charge must be non-negative integer basis points")
    setting = db.get(HotelSetting, key)
    if setting is None:
        setting = HotelSetting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
        setting.updated_at = datetime.now(timezone.utc)
    setting.updated_by_id = user.id
    db.commit()
    return {"key": key, "value": setting.value}


@router.get("/api/v1/inventory")
def list_inventory(
    low_stock: bool = False,
    include_archived: bool = False,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_roles(Role.ADMIN, Role.MANAGER, Role.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    if include_archived and user.role not in {Role.ADMIN.value, Role.MANAGER.value}:
        raise HTTPException(status_code=403, detail="Only Admin or Manager can view archived inventory")
    query = select(InventoryItem)
    if include_archived:
        query = query.where(InventoryItem.archived_at.is_not(None))
    else:
        query = query.where(InventoryItem.archived_at.is_(None))
    if low_stock:
        query = query.where(InventoryItem.quantity_on_hand <= InventoryItem.reorder_level)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(InventoryItem.name).limit(limit).offset(offset)).all()
    return {
        "items": [
            {"id": item.id, "sku": item.sku, "name": item.name, "unit": item.unit,
             "quantity_on_hand": item.quantity_on_hand, "reorder_level": item.reorder_level,
             "unit_cost_ugx": item.unit_cost_ugx,
               "low_stock": item.quantity_on_hand <= item.reorder_level,
               "archived_at": item.archived_at.isoformat() if item.archived_at else None}
            for item in items
        ],
           "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/api/v1/inventory", status_code=status.HTTP_201_CREATED)
def create_inventory_item(
    payload: InventoryItemInput,
    _: User = Depends(require_roles(*management_roles)),
    db: Session = Depends(get_db),
):
    if db.scalar(select(InventoryItem.id).where(InventoryItem.sku == payload.sku)):
        raise HTTPException(status_code=409, detail="Inventory SKU already exists")
    item = InventoryItem(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "sku": item.sku, "name": item.name, "quantity_on_hand": item.quantity_on_hand, "low_stock": item.quantity_on_hand <= item.reorder_level}


@router.post("/api/v1/inventory/{item_id}/adjust")
def adjust_stock(
    item_id: str,
    payload: StockAdjustment,
    user: User = Depends(require_roles(*management_roles)),
    db: Session = Depends(get_db),
):
    item = db.scalar(select(InventoryItem).where(InventoryItem.id == item_id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    if item.archived_at is not None:
        raise HTTPException(status_code=409, detail="Archived inventory cannot be adjusted")
    if item.quantity_on_hand + payload.quantity_delta < 0:
        raise HTTPException(status_code=409, detail="Stock cannot fall below zero")
    item.quantity_on_hand += payload.quantity_delta
    item.updated_at = datetime.now(timezone.utc)
    db.add(StockMovement(item_id=item.id, quantity_delta=payload.quantity_delta, reason=payload.reason, actor_id=user.id))
    db.commit()
    return {"id": item.id, "sku": item.sku, "quantity_on_hand": item.quantity_on_hand, "low_stock": item.quantity_on_hand <= item.reorder_level}


@router.delete("/api/v1/inventory/{item_id}")
def archive_inventory_item(
    item_id: str,
    user: User = Depends(require_roles(*management_roles)),
    db: Session = Depends(get_db),
):
    item = db.scalar(select(InventoryItem).where(InventoryItem.id == item_id).with_for_update())
    if item is None or item.archived_at is not None:
        raise HTTPException(status_code=404, detail="Active inventory item not found")
    if item.quantity_on_hand != 0:
        raise HTTPException(status_code=409, detail="Reduce stock to zero before removing this item")
    item.archived_at = datetime.now(timezone.utc)
    item.archived_by_id = user.id
    db.add(
        AuditLog(
            actor_id=user.id,
            action="inventory.archived",
            entity_type="inventory_item",
            entity_id=item.id,
            details={"sku": item.sku, "name": item.name},
        )
    )
    db.commit()
    return {"id": item.id, "sku": item.sku, "archived_at": item.archived_at.isoformat()}


@router.get("/api/v1/notifications")
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    items = db.scalars(query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.post("/api/v1/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": notification.id, "read_at": notification.read_at.isoformat()}