import csv
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO, StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user, require_roles
from app.models import (
    AuditLog,
    Folio,
    FolioCharge,
    FolioPayment,
    Guest,
    HousekeepingTask,
    Reservation,
    ReservationStatus,
    Role,
    Room,
    RoomStatus,
    RoomType,
    User,
)

router = APIRouter(tags=["Dashboard, reports, and audit"])
financial_roles = (Role.ADMIN, Role.MANAGER, Role.FRONT_DESK, Role.ACCOUNTANT)


@router.get("/api/v1/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    rooms_total = db.scalar(select(func.count()).select_from(Room)) or 0
    rooms_blocked = db.scalar(select(func.count()).select_from(Room).where(Room.status == RoomStatus.OUT_OF_ORDER.value)) or 0
    sellable_rooms = max(rooms_total - rooms_blocked, 0)
    arrivals = db.scalar(
        select(func.count()).select_from(Reservation).where(
            Reservation.check_in == today, Reservation.status == ReservationStatus.CONFIRMED.value
        )
    ) or 0
    departures = db.scalar(
        select(func.count()).select_from(Reservation).where(
            Reservation.check_out == today, Reservation.status == ReservationStatus.CHECKED_IN.value
        )
    ) or 0
    occupied = db.scalar(
        select(func.count()).select_from(Reservation).where(Reservation.status == ReservationStatus.CHECKED_IN.value)
    ) or 0
    dirty_rooms = db.scalar(select(func.count()).select_from(Room).where(Room.status == RoomStatus.DIRTY.value)) or 0
    open_tasks = db.scalar(select(func.count()).select_from(HousekeepingTask).where(HousekeepingTask.status != "completed")) or 0
    result = {
        "date": today.isoformat(),
        "arrivals": arrivals,
        "departures": departures,
        "in_house": occupied,
        "sellable_rooms": sellable_rooms,
        "occupancy_percent": round(occupied * 100 / sellable_rooms, 1) if sellable_rooms else 0,
        "dirty_rooms": dirty_rooms,
        "open_housekeeping_tasks": open_tasks,
    }
    if user.role == Role.HOUSEKEEPING.value:
        return result
    revenue_today = db.scalar(
        select(func.coalesce(func.sum(FolioPayment.amount_ugx), 0)).where(
            FolioPayment.is_refund.is_(False), func.date(FolioPayment.created_at) == today
        )
    ) or 0
    refund_today = db.scalar(
        select(func.coalesce(func.sum(FolioPayment.amount_ugx), 0)).where(
            FolioPayment.is_refund.is_(True), func.date(FolioPayment.created_at) == today
        )
    ) or 0
    expected_room_revenue = db.scalar(
        select(func.coalesce(func.sum(Reservation.nightly_rate_ugx), 0)).where(
            Reservation.status == ReservationStatus.CHECKED_IN.value,
            Reservation.check_in <= today,
            Reservation.check_out > today,
        )
    ) or 0
    return {
        **result,
        "revenue_ugx": revenue_today - refund_today,
        "adr_ugx": round(expected_room_revenue / occupied) if occupied else 0,
        "revpar_ugx": round(expected_room_revenue / sellable_rooms) if sellable_rooms else 0,
    }


def report_rows(db: Session, report_type: str, from_date: date, to_date: date) -> list[dict]:
    start_at = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    if report_type == "occupancy":
        days = (to_date - from_date).days + 1
        rooms = db.scalar(select(func.count()).select_from(Room).where(Room.status != RoomStatus.OUT_OF_ORDER.value)) or 0
        rows = []
        for offset in range(days):
            day = from_date + timedelta(days=offset)
            occupied = db.scalar(
                select(func.count()).select_from(Reservation).where(
                    Reservation.check_in <= day,
                    Reservation.check_out > day,
                    Reservation.status.in_([ReservationStatus.CONFIRMED.value, ReservationStatus.CHECKED_IN.value]),
                )
            ) or 0
            rows.append({"date": day.isoformat(), "occupied_rooms": occupied, "sellable_rooms": rooms,
                         "occupancy_percent": round(occupied * 100 / rooms, 1) if rooms else 0})
        return rows
    if report_type in {"revenue-source", "revenue-room-type"}:
        if report_type == "revenue-source":
            dimension = Reservation.source.label("group")
            query = select(dimension, func.sum(FolioCharge.quantity * FolioCharge.unit_amount_ugx).label("amount_ugx"))
        else:
            dimension = RoomType.name.label("group")
            query = select(dimension, func.sum(FolioCharge.quantity * FolioCharge.unit_amount_ugx).label("amount_ugx"))
        query = query.join(Folio, Folio.id == FolioCharge.folio_id).join(Reservation, Reservation.id == Folio.reservation_id)
        if report_type == "revenue-room-type":
            query = query.join(Room, Room.id == Reservation.room_id).join(RoomType, RoomType.id == Room.room_type_id)
        rows = db.execute(
            query.where(FolioCharge.created_at >= start_at, FolioCharge.created_at < end_at)
            .group_by(dimension).order_by(dimension)
        ).all()
        return [{"group": row.group or "other", "amount_ugx": int(row.amount_ugx or 0)} for row in rows]
    if report_type == "payment-method":
        rows = db.execute(
            select(
                FolioPayment.method.label("group"),
                func.sum(case((FolioPayment.is_refund.is_(True), -FolioPayment.amount_ugx), else_=FolioPayment.amount_ugx)).label("amount_ugx"),
            )
            .where(FolioPayment.created_at >= start_at, FolioPayment.created_at < end_at)
            .group_by(FolioPayment.method)
            .order_by(FolioPayment.method)
        ).all()
        return [{"group": row.group, "amount_ugx": int(row.amount_ugx or 0)} for row in rows]
    if report_type == "cancellations":
        rows = db.execute(
            select(Reservation.source, func.count().label("count"))
            .where(Reservation.status == ReservationStatus.CANCELLED.value, Reservation.created_at >= start_at, Reservation.created_at < end_at)
            .group_by(Reservation.source)
            .order_by(Reservation.source)
        ).all()
        return [{"source": source or "other", "count": count} for source, count in rows]
    if report_type == "staff-performance":
        rows = db.execute(
            select(User.full_name, AuditLog.action, func.count().label("count"))
            .join(User, User.id == AuditLog.actor_id)
            .where(AuditLog.created_at >= start_at, AuditLog.created_at < end_at)
            .group_by(User.full_name, AuditLog.action)
            .order_by(User.full_name, AuditLog.action)
        ).all()
        return [{"staff": name, "action": action, "count": count} for name, action, count in rows]
    raise HTTPException(status_code=404, detail="Unknown report type")


@router.get("/api/v1/reports/{report_type}")
def report(
    report_type: str,
    from_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    to_date: date = Query(default_factory=date.today),
    export: str | None = Query(default=None, pattern="^(csv|pdf)$"),
    _: User = Depends(require_roles(*financial_roles)),
    db: Session = Depends(get_db),
):
    if to_date < from_date:
        raise HTTPException(status_code=422, detail="End date must be on or after start date")
    rows = report_rows(db, report_type, from_date, to_date)
    if not export:
        return {"report": report_type, "from_date": from_date, "to_date": to_date, "items": rows}
    columns = list(rows[0].keys()) if rows else ["message"]
    if export == "csv":
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        if rows:
            writer.writerows(rows)
        else:
            writer.writerow({"message": "No data for selected period"})
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={report_type}-{from_date}-{to_date}.csv"},
        )
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, title=f"Staywell {report_type} report")
    table_rows = [[column.replace("_", " ").title() for column in columns]]
    table_rows.extend([[str(row.get(column, "")) for column in columns] for row in rows] or [["No data for selected period"]])
    table = Table(table_rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#284639")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d9ded6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f4ef")]),
    ]))
    from reportlab.lib.styles import getSampleStyleSheet

    document.build([Paragraph(f"Staywell · {report_type.replace('-', ' ').title()}", getSampleStyleSheet()["Title"]), Spacer(1, 12), table])
    return Response(buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={report_type}-{from_date}-{to_date}.pdf"})


@router.get("/api/v1/audit-logs")
def audit_logs(
    search: str | None = Query(default=None, max_length=100),
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_roles(Role.ADMIN, Role.MANAGER, Role.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    query = select(AuditLog, User.full_name, User.email).outerjoin(User, User.id == AuditLog.actor_id)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            User.full_name.ilike(pattern)
            | User.email.ilike(pattern)
            | AuditLog.action.ilike(pattern)
            | AuditLog.entity_type.ilike(pattern)
            | AuditLog.entity_id.ilike(pattern)
        )
    if from_date:
        query = query.where(func.date(AuditLog.created_at) >= from_date)
    if to_date:
        query = query.where(func.date(AuditLog.created_at) <= to_date)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)).all()
    items = [
        {
            "id": audit.id,
            "actor_id": audit.actor_id,
            "actor_name": actor_name or "System",
            "actor_email": actor_email,
            "action": audit.action,
            "entity_type": audit.entity_type,
            "entity_id": audit.entity_id,
            "details": audit.details,
            "created_at": audit.created_at.isoformat(),
        }
        for audit, actor_name, actor_email in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}