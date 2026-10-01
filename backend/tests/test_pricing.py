from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import HotelSetting, RateRule, RoomType
from app.pricing import price_stay


def test_rate_rules_and_basis_point_charges_use_integer_ugx():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        room_type = RoomType(code="TEST", name="Test Room", capacity=2, base_rate_ugx=100_000)
        db.add(room_type)
        db.flush()
        db.add_all([
            RateRule(name="Weekend", rule_type="weekend", adjustment_type="percent", adjustment_value=1000),
            RateRule(name="Promo", rule_type="promo", adjustment_type="percent", adjustment_value=-1000, promo_code="HELLO"),
            HotelSetting(key="charges", value={"tax_basis_points": 1800, "service_basis_points": 500}),
        ])
        db.flush()
        quote = price_stay(db, room_type, date(2026, 10, 2), date(2026, 10, 4), promo_code="hello")
        assert quote["nights"] == 2
        assert quote["subtotal_ugx"] == 198_000
        assert quote["service_charge_ugx"] == 9_900
        assert quote["tax_ugx"] == 37_422
        assert quote["total_ugx"] == 245_322
        assert quote["average_nightly_rate_ugx"] == 99_000
    engine.dispose()