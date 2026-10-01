import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Guest, Role, Room, RoomType, User
from app.routers.auth import limiter
from app.security import hash_password


@pytest.fixture
def client():
    limiter.reset()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestSession() as db:
        db.add(
            User(
                email="admin@example.com",
                full_name="Avery Admin",
                password_hash=hash_password("Correct-Horse-42!"),
                role=Role.ADMIN.value,
                is_active=True,
            )
        )
        db.add(
            User(
                email="manager@example.com",
                full_name="Morgan Manager",
                password_hash=hash_password("Correct-Horse-42!"),
                role=Role.MANAGER.value,
                is_active=True,
            )
        )
        db.add(
            User(
                email="housekeeping@example.com",
                full_name="Harper Housekeeping",
                password_hash=hash_password("Correct-Horse-42!"),
                role=Role.HOUSEKEEPING.value,
                is_active=True,
            )
        )
        room_type = RoomType(id="type-standard", code="STD", name="Standard", capacity=2, base_rate_ugx=180000)
        guest = Guest(id="guest-test", first_name="Taylor", last_name="Guest", email="taylor@example.com")
        db.add_all([room_type, guest])
        db.flush()
        db.add(Room(id="room-test", number="101", floor=1, room_type_id=room_type.id, status="available"))
        db.commit()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()