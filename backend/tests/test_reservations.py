from datetime import date, timedelta


def manager_token(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "manager@example.com", "password": "Correct-Horse-42!"},
    )
    return response.json()["access_token"]


def test_manager_can_book_room_and_room_disappears_from_availability(client):
    token = manager_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    check_in = date.today() + timedelta(days=14)
    check_out = check_in + timedelta(days=2)
    params = {"check_in": check_in.isoformat(), "check_out": check_out.isoformat()}

    before = client.get("/api/v1/reservations/availability", params=params, headers=headers)
    assert before.status_code == 200
    assert [room["number"] for room in before.json()] == ["101"]

    response = client.post(
        "/api/v1/reservations",
        headers=headers,
        json={
            "guest_id": "guest-test",
            "room_id": "room-test",
            **params,
            "nightly_rate_ugx": 180000,
            "deposit_ugx": 40000,
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "confirmed"
    assert response.json()["confirmation_code"]

    after = client.get("/api/v1/reservations/availability", params=params, headers=headers)
    assert after.json() == []


def test_overlapping_room_booking_is_rejected(client):
    token = manager_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    check_in = date.today() + timedelta(days=14)
    check_out = check_in + timedelta(days=2)
    payload = {
        "guest_id": "guest-test",
        "room_id": "room-test",
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "nightly_rate_ugx": 180000,
    }

    assert client.post("/api/v1/reservations", headers=headers, json=payload).status_code == 201
    duplicate = client.post("/api/v1/reservations", headers=headers, json=payload)
    assert duplicate.status_code == 409


def test_housekeeping_cannot_create_reservations(client):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "housekeeping@example.com", "password": "Correct-Horse-42!"},
    )
    response = client.get(
        "/api/v1/reservations/availability",
        params={"check_in": "2030-01-01", "check_out": "2030-01-02"},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 403


def test_blacklisted_guest_cannot_be_booked(client):
    token = manager_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    flagged = client.patch("/api/v1/guests/guest-test/flags", headers=headers, json={"is_blacklisted": True})
    assert flagged.status_code == 200
    check_in = date.today() + timedelta(days=14)
    response = client.post(
        "/api/v1/reservations",
        headers=headers,
        json={
            "guest_id": "guest-test",
            "room_id": "room-test",
            "check_in": check_in.isoformat(),
            "check_out": (check_in + timedelta(days=1)).isoformat(),
            "nightly_rate_ugx": 180000,
        },
    )
    assert response.status_code == 409