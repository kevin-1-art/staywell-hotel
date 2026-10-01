from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Response, status
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.models import (
    AuditLog,
    Folio,
    FolioCharge,
    FolioPayment,
    Guest,
    HousekeepingTask,
    InvoiceCounter,
    Reservation,
    ReservationStatus,
    Role,
    Room,
    RoomStatus,
    User,
)
from app.schemas import CheckInInput, CheckOutInput, ChargeCreate, FolioEntryView, FolioView, PaymentCreate

router = APIRouter(tags=["Stays and billing"])
front_desk_roles = (Role.ADMIN, Role.MANAGER, Role.FRONT_DESK)
folio_read_roles = (*front_desk_roles, Role.ACCOUNTANT)
PAYMENT_METHODS = {"cash", "card", "bank_transfer", "mobile_money"}


def balance_for(db: Session, folio_id: str) -> tuple[int, int, int]:
    charges = db.scalar(
        select(func.coalesce(func.sum(FolioCharge.quantity * FolioCharge.unit_amount_ugx), 0)).where(
            FolioCharge.folio_id == folio_id
        )
    ) or 0
    payments = db.scalar(
        select(func.coalesce(func.sum(FolioPayment.amount_ugx), 0)).where(
            FolioPayment.folio_id == folio_id, FolioPayment.is_refund.is_(False)
        )
    ) or 0
    refunds = db.scalar(
        select(func.coalesce(func.sum(FolioPayment.amount_ugx), 0)).where(
            FolioPayment.folio_id == folio_id, FolioPayment.is_refund.is_(True)
        )
    ) or 0
    return charges, payments - refunds, charges - payments + refunds


def folio_response(db: Session, folio: Folio) -> FolioView:
    reservation = db.get(Reservation, folio.reservation_id)
    guest = db.get(Guest, reservation.guest_id)
    room = db.get(Room, reservation.room_id)
    charges, paid, outstanding = balance_for(db, folio.id)
    charge_rows = db.scalars(
        select(FolioCharge).where(FolioCharge.folio_id == folio.id).order_by(FolioCharge.created_at, FolioCharge.id)
    ).all()
    payment_rows = db.scalars(
        select(FolioPayment).where(FolioPayment.folio_id == folio.id).order_by(FolioPayment.created_at, FolioPayment.id)
    ).all()
    return FolioView(
        id=folio.id,
        reservation_id=reservation.id,
        invoice_number=folio.invoice_number,
        status=folio.status,
        guest_name=f"{guest.first_name} {guest.last_name}",
        room_number=room.number,
        charges=[
            FolioEntryView(
                id=row.id,
                description=row.description,
                category=row.category,
                quantity=row.quantity,
                unit_amount_ugx=row.unit_amount_ugx,
                amount_ugx=row.quantity * row.unit_amount_ugx,
                created_at=row.created_at.isoformat(),
            )
            for row in charge_rows
        ],
        payments=[
            FolioEntryView(
                id=row.id,
                description="Refund" if row.is_refund else "Payment",
                amount_ugx=row.amount_ugx,
                method=row.method,
                reference=row.reference,
                is_refund=row.is_refund,
                created_at=row.created_at.isoformat(),
            )
            for row in payment_rows
        ],
        total_charges_ugx=charges,
        total_payments_ugx=paid,
        outstanding_ugx=outstanding,
    )


@router.post("/api/v1/reservations/{reservation_id}/check-in", response_model=FolioView)
def check_in(
    reservation_id: str,
    payload: CheckInInput,
    user: User = Depends(require_roles(*front_desk_roles)),
    db: Session = Depends(get_db),
):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.status != ReservationStatus.CONFIRMED.value:
        raise HTTPException(status_code=409, detail="Only confirmed reservations can be checked in")
    guest = db.get(Guest, reservation.guest_id)
    if guest.is_blacklisted:
        raise HTTPException(status_code=409, detail="This guest is blocked from check-in")
    room = db.get(Room, reservation.room_id)
    if room.status not in {RoomStatus.AVAILABLE.value, RoomStatus.INSPECTED.value}:
        raise HTTPException(status_code=409, detail="Room is not ready for check-in")
    reservation.status = ReservationStatus.CHECKED_IN.value
    reservation.id_document_type = payload.id_document_type
    reservation.id_document_number = payload.id_document_number
    reservation.early_check_in_fee_ugx = payload.early_check_in_fee_ugx
    reservation.checked_in_at = datetime.now(timezone.utc)
    room.status = RoomStatus.OCCUPIED.value
    folio = db.scalar(select(Folio).where(Folio.reservation_id == reservation.id))
    if folio is None:
        folio = Folio(reservation_id=reservation.id)
        db.add(folio)
        db.flush()
    nights = (reservation.check_out - reservation.check_in).days
    existing_room_charge = db.scalar(
        select(FolioCharge.id).where(FolioCharge.folio_id == folio.id, FolioCharge.category == "room")
    )
    if existing_room_charge is None:
        db.add(
            FolioCharge(
                folio_id=folio.id,
                description=f"Room accommodation ({nights} nights)",
                category="room",
                quantity=1,
                unit_amount_ugx=int(reservation.pricing_details.get("subtotal_ugx", nights * reservation.nightly_rate_ugx)),
                created_by_id=user.id,
            )
        )
        service_charge = int(reservation.pricing_details.get("service_charge_ugx", 0))
        tax = int(reservation.pricing_details.get("tax_ugx", 0))
        if service_charge:
            db.add(FolioCharge(folio_id=folio.id, description="Service charge", category="service_charge", quantity=1, unit_amount_ugx=service_charge, created_by_id=user.id))
        if tax:
            db.add(FolioCharge(folio_id=folio.id, description="Tax", category="tax", quantity=1, unit_amount_ugx=tax, created_by_id=user.id))
    if payload.early_check_in_fee_ugx:
        db.add(
            FolioCharge(
                folio_id=folio.id,
                description="Early check-in fee",
                category="fee",
                quantity=1,
                unit_amount_ugx=payload.early_check_in_fee_ugx,
                created_by_id=user.id,
            )
        )
    existing_deposit = db.scalar(
        select(FolioPayment.id).where(
            FolioPayment.folio_id == folio.id,
            FolioPayment.reference == "Reservation deposit",
            FolioPayment.is_refund.is_(False),
        )
    )
    if reservation.deposit_ugx and existing_deposit is None:
        db.add(
            FolioPayment(
                folio_id=folio.id,
                amount_ugx=reservation.deposit_ugx,
                method="cash",
                reference="Reservation deposit",
                is_refund=False,
                created_by_id=user.id,
            )
        )
    db.add(
        AuditLog(
            actor_id=user.id,
            action="reservation.checked_in",
            entity_type="reservation",
            entity_id=reservation.id,
            details={"folio_id": folio.id, "room_id": room.id},
        )
    )
    db.commit()
    db.refresh(folio)
    return folio_response(db, folio)


@router.get("/api/v1/reservations/{reservation_id}/folio", response_model=FolioView)
def get_folio(
    reservation_id: str,
    _: User = Depends(require_roles(*folio_read_roles)),
    db: Session = Depends(get_db),
):
    folio = db.scalar(select(Folio).where(Folio.reservation_id == reservation_id))
    if folio is None:
        raise HTTPException(status_code=404, detail="Folio not found")
    return folio_response(db, folio)


@router.post("/api/v1/reservations/{reservation_id}/charges", response_model=FolioView, status_code=status.HTTP_201_CREATED)
def add_charge(
    reservation_id: str,
    payload: ChargeCreate,
    user: User = Depends(require_roles(*front_desk_roles)),
    db: Session = Depends(get_db),
):
    folio = db.scalar(select(Folio).where(Folio.reservation_id == reservation_id))
    if folio is None or folio.status != "open":
        raise HTTPException(status_code=409, detail="An open folio is required")
    db.add(
        FolioCharge(
            folio_id=folio.id,
            description=payload.description,
            category=payload.category,
            quantity=payload.quantity,
            unit_amount_ugx=payload.unit_amount_ugx,
            created_by_id=user.id,
        )
    )
    db.commit()
    return folio_response(db, folio)


@router.post("/api/v1/reservations/{reservation_id}/payments", response_model=FolioView, status_code=status.HTTP_201_CREATED)
def add_payment(
    reservation_id: str,
    payload: PaymentCreate,
    user: User = Depends(require_roles(*folio_read_roles)),
    db: Session = Depends(get_db),
):
    if payload.method not in PAYMENT_METHODS:
        raise HTTPException(status_code=422, detail="Unsupported payment method")
    folio = db.scalar(select(Folio).where(Folio.reservation_id == reservation_id))
    if folio is None or folio.status != "open":
        raise HTTPException(status_code=409, detail="An open folio is required")
    _, _, balance = balance_for(db, folio.id)
    if payload.amount_ugx > balance:
        raise HTTPException(status_code=409, detail="Payment exceeds the outstanding balance")
    db.add(
        FolioPayment(
            folio_id=folio.id,
            amount_ugx=payload.amount_ugx,
            method=payload.method,
            reference=payload.reference,
            is_refund=False,
            created_by_id=user.id,
        )
    )
    db.add(AuditLog(actor_id=user.id, action="folio.payment_received", entity_type="folio", entity_id=folio.id, details={"amount_ugx": payload.amount_ugx, "method": payload.method}))
    db.commit()
    return folio_response(db, folio)


@router.post("/api/v1/folios/{folio_id}/refunds", response_model=FolioView, status_code=status.HTTP_201_CREATED)
def refund_payment(
    folio_id: str,
    payload: PaymentCreate,
    user: User = Depends(require_roles(Role.ADMIN, Role.MANAGER, Role.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    if payload.method not in PAYMENT_METHODS:
        raise HTTPException(status_code=422, detail="Unsupported payment method")
    folio = db.get(Folio, folio_id)
    if folio is None:
        raise HTTPException(status_code=404, detail="Folio not found")
    _, paid, _ = balance_for(db, folio.id)
    if payload.amount_ugx > paid:
        raise HTTPException(status_code=409, detail="Refund exceeds collected payments")
    db.add(FolioPayment(folio_id=folio.id, amount_ugx=payload.amount_ugx, method=payload.method, reference=payload.reference, is_refund=True, created_by_id=user.id))
    db.add(AuditLog(actor_id=user.id, action="folio.refund_issued", entity_type="folio", entity_id=folio.id, details={"amount_ugx": payload.amount_ugx, "method": payload.method}))
    db.commit()
    return folio_response(db, folio)


@router.post("/api/v1/reservations/{reservation_id}/check-out", response_model=FolioView)
def check_out(
    reservation_id: str,
    payload: CheckOutInput,
    user: User = Depends(require_roles(*front_desk_roles)),
    db: Session = Depends(get_db),
):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.status != ReservationStatus.CHECKED_IN.value:
        raise HTTPException(status_code=409, detail="Only in-house reservations can be checked out")
    folio = db.scalar(select(Folio).where(Folio.reservation_id == reservation.id))
    if folio is None or folio.status != "open":
        raise HTTPException(status_code=409, detail="An open folio is required")
    if payload.manager_override and user.role not in {Role.ADMIN.value, Role.MANAGER.value}:
        raise HTTPException(status_code=403, detail="Only a manager can override an unpaid balance")
    if payload.manager_override and not payload.override_reason:
        raise HTTPException(status_code=422, detail="A reason is required for a manager override")
    if payload.late_check_out_fee_ugx:
        db.add(
            FolioCharge(
                folio_id=folio.id,
                description="Late check-out fee",
                category="fee",
                quantity=1,
                unit_amount_ugx=payload.late_check_out_fee_ugx,
                created_by_id=user.id,
            )
        )
        db.flush()
    _, _, balance = balance_for(db, folio.id)
    if balance > 0 and not payload.manager_override:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Outstanding balance of UGX {balance} must be settled before checkout")
    now = datetime.now(timezone.utc)
    if payload.manager_override:
        reservation.checkout_override_reason = payload.override_reason
        db.add(
            AuditLog(
                actor_id=user.id,
                action="checkout.balance_override",
                entity_type="reservation",
                entity_id=reservation.id,
                details={"outstanding_ugx": balance, "reason": payload.override_reason},
            )
        )
    reservation.status = ReservationStatus.CHECKED_OUT.value
    reservation.checked_out_at = now
    reservation.late_check_out_fee_ugx = payload.late_check_out_fee_ugx
    folio.status = "closed"
    folio.closed_at = now
    counter = db.scalar(select(InvoiceCounter).where(InvoiceCounter.id == 1).with_for_update())
    if counter is None:
        counter = InvoiceCounter(id=1, next_number=100001)
        db.add(counter)
        db.flush()
    folio.invoice_number = counter.next_number
    counter.next_number += 1
    room = db.get(Room, reservation.room_id)
    room.status = RoomStatus.DIRTY.value
    db.add(HousekeepingTask(room_id=room.id, reservation_id=reservation.id, status="pending", notes="Checkout clean"))
    db.add(
        AuditLog(
            actor_id=user.id,
            action="reservation.checked_out",
            entity_type="reservation",
            entity_id=reservation.id,
            details={"folio_id": folio.id, "invoice_number": folio.invoice_number},
        )
    )
    db.commit()
    return folio_response(db, folio)


@router.get("/api/v1/folios/{folio_id}/invoice.pdf")
def invoice_pdf(
    folio_id: str,
    _: User = Depends(require_roles(*folio_read_roles)),
    db: Session = Depends(get_db),
):
    folio = db.get(Folio, folio_id)
    if folio is None or folio.invoice_number is None:
        raise HTTPException(status_code=404, detail="Final invoice not found")
    data = folio_response(db, folio)
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, title=f"Staywell Invoice {folio.invoice_number}")
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("STAYWELL HOTEL", styles["Title"]),
        Paragraph(f"TAX INVOICE · SW-{folio.invoice_number:06d}", styles["Heading2"]),
        Paragraph(f"Guest: {escape(data.guest_name)} · Room: {escape(data.room_number)}", styles["Normal"]),
        Spacer(1, 16),
    ]
    rows = [["Description", "Qty", "Unit (UGX)", "Amount (UGX)"]]
    rows.extend([[escape(line.description), str(line.quantity or 1), f"{line.unit_amount_ugx or 0:,}", f"{line.amount_ugx:,}"] for line in data.charges])
    rows.append(["Total charges", "", "", f"{data.total_charges_ugx:,}"])
    rows.append(["Payments received", "", "", f"-{data.total_payments_ugx:,}"])
    rows.append(["Balance", "", "", f"{data.outstanding_ugx:,}"])
    table = Table(rows, colWidths=[245, 40, 100, 110], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#284639")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d9ded6")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f4ef")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(table)
    document.build(elements)
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=staywell-invoice-{folio.invoice_number}.pdf"},
    )