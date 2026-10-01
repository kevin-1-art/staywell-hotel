from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Folio, FolioPayment, Guest, HousekeepingTask, Reservation, Room, RoomType, User
from app.seed import seed_data


def test_seed_creates_requested_demo_scale_and_is_idempotent():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False, expire_on_commit=False) as db:
        with db.begin():
            counts = seed_data(db)
        assert counts["users"] == 6
        assert counts["room_types"] == 5
        assert counts["rooms"] == 80
        assert counts["guests"] == 200
        assert counts["reservations"] == 300
        assert counts["payments"] == 300
        assert db.scalar(select(func.count()).select_from(Folio)) == 300
        assert db.scalar(select(func.count()).select_from(HousekeepingTask)) > 100
        assert db.scalar(select(func.count()).select_from(Reservation)) == 300
        assert db.scalar(select(func.count()).select_from(RoomType)) == 5
        assert db.scalar(select(func.count()).select_from(Room)) == 80
        assert db.scalar(select(func.count()).select_from(Guest)) == 200
        assert db.scalar(select(func.count()).select_from(User)) == 6
        assert seed_data(db) == {"created": 0}
        assert db.scalar(select(func.count()).select_from(FolioPayment)) == 300
    engine.dispose()