from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HotelSetting, RateRule, RoomType


def price_stay(
    db: Session,
    room_type: RoomType,
    check_in: date,
    check_out: date,
    promo_code: str | None = None,
    company_name: str | None = None,
) -> dict[str, int | list[dict[str, int | str]]]:
    rules = db.scalars(select(RateRule).where(RateRule.is_active.is_(True))).all()
    settings = db.get(HotelSetting, "charges")
    charges = settings.value if settings else {"tax_basis_points": 0, "service_basis_points": 0}
    tax_bps = max(int(charges.get("tax_basis_points", 0)), 0)
    service_bps = max(int(charges.get("service_basis_points", 0)), 0)
    nightly: list[dict[str, int | str]] = []
    cursor = check_in
    while cursor < check_out:
        rate = room_type.base_rate_ugx
        for rule in rules:
            if rule.room_type_id and rule.room_type_id != room_type.id:
                continue
            if rule.rule_type == "seasonal" and not (rule.starts_on and rule.ends_on and rule.starts_on <= cursor <= rule.ends_on):
                continue
            if rule.rule_type == "weekend" and cursor.weekday() not in {4, 5}:
                continue
            if rule.rule_type == "promo" and (not promo_code or not rule.promo_code or rule.promo_code.casefold() != promo_code.casefold()):
                continue
            if rule.rule_type == "corporate" and (not company_name or not rule.company_name or rule.company_name.casefold() != company_name.casefold()):
                continue
            if rule.adjustment_type == "percent":
                rate += rate * rule.adjustment_value // 10_000
            else:
                rate += rule.adjustment_value
        rate = max(rate, 0)
        nightly.append({"date": cursor.isoformat(), "room_rate_ugx": rate})
        cursor += timedelta(days=1)
    subtotal = sum(int(line["room_rate_ugx"]) for line in nightly)
    service = subtotal * service_bps // 10_000
    tax = (subtotal + service) * tax_bps // 10_000
    return {
        "nights": len(nightly),
        "average_nightly_rate_ugx": subtotal // len(nightly),
        "subtotal_ugx": subtotal,
        "service_charge_ugx": service,
        "tax_ugx": tax,
        "total_ugx": subtotal + service + tax,
        "nightly_rates": nightly,
    }