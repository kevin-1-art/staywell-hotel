from datetime import date, timedelta


def manager_headers(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "manager@example.com", "password": "Correct-Horse-42!"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_stay_billing_checkout_override_and_invoice(client):
    headers = manager_headers(client)
    check_in = date.today() + timedelta(days=7)
    check_out = check_in + timedelta(days=2)
    reservation_response = client.post(
        "/api/v1/reservations",
        headers=headers,
        json={
            "guest_id": "guest-test",
            "room_id": "room-test",
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "nightly_rate_ugx": 180000,
        },
    )
    assert reservation_response.status_code == 201
    reservation = reservation_response.json()

    checkin = client.post(
        f"/api/v1/reservations/{reservation['id']}/check-in",
        headers=headers,
        json={"id_document_type": "national_id", "id_document_number": "CM90000001"},
    )
    assert checkin.status_code == 200
    assert checkin.json()["total_charges_ugx"] == 360000
    assert checkin.json()["outstanding_ugx"] == 360000

    charged = client.post(
        f"/api/v1/reservations/{reservation['id']}/charges",
        headers=headers,
        json={"description": "Restaurant dinner", "category": "pos", "quantity": 1, "unit_amount_ugx": 45000},
    )
    assert charged.status_code == 201
    paid = client.post(
        f"/api/v1/reservations/{reservation['id']}/payments",
        headers=headers,
        json={"amount_ugx": 200000, "method": "mobile_money", "reference": "MM-123"},
    )
    assert paid.status_code == 201
    assert paid.json()["outstanding_ugx"] == 205000

    blocked = client.post(
        f"/api/v1/reservations/{reservation['id']}/check-out",
        headers=headers,
        json={},
    )
    assert blocked.status_code == 409

    checked_out = client.post(
        f"/api/v1/reservations/{reservation['id']}/check-out",
        headers=headers,
        json={"manager_override": True, "override_reason": "Company guarantee approved"},
    )
    assert checked_out.status_code == 200
    assert checked_out.json()["invoice_number"] == 100001
    assert checked_out.json()["outstanding_ugx"] == 205000

    rooms = client.get("/api/v1/rooms", params={"status": "dirty"}, headers=headers)
    assert rooms.status_code == 200
    assert [room["number"] for room in rooms.json()["items"]] == ["101"]

    task_list = client.get("/api/v1/housekeeping", headers=headers)
    task = task_list.json()["items"][0]
    assert task["status"] == "pending"
    started = client.post(f"/api/v1/housekeeping/{task['id']}/start", headers=headers)
    assert started.json()["status"] == "in_progress"
    cleaning = client.get("/api/v1/rooms", params={"status": "cleaning"}, headers=headers)
    assert cleaning.json()["total"] == 1
    completed = client.post(f"/api/v1/housekeeping/{task['id']}/complete", headers=headers)
    assert completed.json()["status"] == "completed"
    inspected = client.get("/api/v1/rooms", params={"status": "inspected"}, headers=headers)
    assert inspected.json()["total"] == 1
    released = client.post(f"/api/v1/housekeeping/{task['id']}/release", headers=headers)
    assert released.json()["status"] == "available"

    ticket = client.post(
        "/api/v1/maintenance",
        headers=headers,
        json={"room_id": "room-test", "title": "Repair bedside lamp", "priority": "normal"},
    )
    assert ticket.status_code == 201
    blocked_availability = client.get(
        "/api/v1/reservations/availability",
        params={"check_in": (check_out + timedelta(days=1)).isoformat(), "check_out": (check_out + timedelta(days=2)).isoformat()},
        headers=headers,
    )
    assert blocked_availability.json() == []
    closed_ticket = client.post(f"/api/v1/maintenance/{ticket.json()['id']}/close", headers=headers)
    assert closed_ticket.json()["room_status"] == "dirty"

    pdf = client.get(f"/api/v1/folios/{checked_out.json()['id']}/invoice.pdf", headers=headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")

    revenue = client.get(
        "/api/v1/reports/revenue-source",
        params={"from_date": date.today().isoformat(), "to_date": date.today().isoformat()},
        headers=headers,
    )
    assert revenue.status_code == 200
    assert revenue.json()["items"] == [{"group": "direct", "amount_ugx": 405000}]
    csv_report = client.get(
        "/api/v1/reports/revenue-room-type",
        params={"from_date": date.today().isoformat(), "to_date": date.today().isoformat(), "export": "csv"},
        headers=headers,
    )
    assert csv_report.status_code == 200
    assert "Standard,405000" in csv_report.text
    pdf_report = client.get(
        "/api/v1/reports/occupancy",
        params={"from_date": date.today().isoformat(), "to_date": date.today().isoformat(), "export": "pdf"},
        headers=headers,
    )
    assert pdf_report.status_code == 200
    assert pdf_report.content.startswith(b"%PDF")

    dashboard = client.get("/api/v1/dashboard", headers=headers)
    assert dashboard.status_code == 200
    assert "occupancy_percent" in dashboard.json()