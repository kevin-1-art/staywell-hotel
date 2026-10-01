def login(client, email="admin@example.com"):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Correct-Horse-42!"},
    )
    return response


def test_only_admin_can_view_role_catalog_and_staff(client):
    manager = login(client, "manager@example.com")
    headers = {"Authorization": f"Bearer {manager.json()['access_token']}"}
    assert client.get("/api/v1/admin/roles", headers=headers).status_code == 403
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 403

    admin = login(client)
    admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    roles = client.get("/api/v1/admin/roles", headers=admin_headers)
    assert roles.status_code == 200
    assert {role["key"] for role in roles.json()} == {"admin", "manager", "front_desk", "housekeeping", "accountant"}
    assert client.get("/api/v1/admin/users", headers=admin_headers).json()["total"] == 3


def test_admin_creates_role_scoped_account_then_deactivates_it(client):
    admin = login(client)
    admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    invalid = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"email": "newdesk@example.com", "full_name": "New Desk", "role": "front_desk", "password": "weak-password"},
    )
    assert invalid.status_code == 422

    created = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"email": "newdesk@example.com", "full_name": "New Desk", "role": "front_desk", "password": "FrontDesk-Secure-42!"},
    )
    assert created.status_code == 201
    assert created.json()["role"] == "front_desk"

    staff_login = client.post(
        "/api/v1/auth/login",
        json={"email": "newdesk@example.com", "password": "FrontDesk-Secure-42!"},
    )
    staff_headers = {"Authorization": f"Bearer {staff_login.json()['access_token']}"}
    assert client.get("/api/v1/reservations", headers=staff_headers).status_code == 200
    assert client.get("/api/v1/admin/users", headers=staff_headers).status_code == 403
    refresh_cookie = client.cookies.get("hotel_refresh")
    assert refresh_cookie

    deactivated = client.patch(
        f"/api/v1/admin/users/{created.json()['id']}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_admin_cannot_demote_or_deactivate_self(client):
    admin = login(client)
    response = client.patch(
        f"/api/v1/admin/users/{admin.json()['user']['id']}",
        headers={"Authorization": f"Bearer {admin.json()['access_token']}"},
        json={"role": "manager"},
    )
    assert response.status_code == 409


def test_admin_delete_archives_account_revokes_sessions_and_keeps_audit_history(client):
    admin = login(client)
    admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    created = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"email": "archive-me@example.com", "full_name": "Archive Me", "role": "housekeeping", "password": "Archive-Me-42!"},
    )
    assert created.status_code == 201

    staff_login = client.post(
        "/api/v1/auth/login",
        json={"email": "archive-me@example.com", "password": "Archive-Me-42!"},
    )
    staff_access = staff_login.json()["access_token"]
    archived = client.delete(f"/api/v1/admin/users/{created.json()['id']}", headers=admin_headers)
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False
    assert archived.json()["deleted_at"] is not None
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {staff_access}"}).status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401

    directory = client.get("/api/v1/admin/users?search=archive-me@example.com", headers=admin_headers)
    assert directory.json()["total"] == 1
    assert directory.json()["items"][0]["deleted_at"] is not None
    audit = client.get("/api/v1/audit-logs?action=user.deleted", headers=admin_headers)
    assert audit.status_code == 200
    assert audit.json()["items"][0]["actor_name"] == "Avery Admin"
    assert audit.json()["items"][0]["entity_id"] == created.json()["id"]

    self_delete = client.delete(f"/api/v1/admin/users/{admin.json()['user']['id']}", headers=admin_headers)
    assert self_delete.status_code == 409


def test_admin_edits_profile_email_and_password(client):
    admin = login(client)
    admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    created = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"email": "editable@example.com", "full_name": "Original Name", "role": "front_desk", "password": "Initial-Password-42!"},
    )
    assert created.status_code == 201
    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": "editable@example.com", "password": "Initial-Password-42!"},
    )
    assert old_login.status_code == 200

    edited = client.patch(
        f"/api/v1/admin/users/{created.json()['id']}",
        headers=admin_headers,
        json={"full_name": "Updated Name", "email": "updated@example.com", "password": "Updated-Password-42!"},
    )
    assert edited.status_code == 200
    assert edited.json()["full_name"] == "Updated Name"
    assert edited.json()["email"] == "updated@example.com"
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "editable@example.com", "password": "Initial-Password-42!"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "updated@example.com", "password": "Updated-Password-42!"},
    ).status_code == 200

    duplicate = client.patch(
        f"/api/v1/admin/users/{created.json()['id']}",
        headers=admin_headers,
        json={"email": "manager@example.com"},
    )
    assert duplicate.status_code == 409