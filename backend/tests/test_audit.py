def bearer(client, email):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Correct-Horse-42!"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_can_search_audit_by_actor_and_action_with_real_pagination(client):
    admin_headers = bearer(client, "admin@example.com")
    created = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"email": "audited@example.com", "full_name": "Audited Staff", "role": "accountant", "password": "Audited-Staff-42!"},
    )
    assert created.status_code == 201

    response = client.get("/api/v1/audit-logs?action=user.created", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    event = response.json()["items"][0]
    assert event["actor_name"] == "Avery Admin"
    assert event["actor_email"] == "admin@example.com"
    assert event["action"] == "user.created"
    assert event["entity_id"] == created.json()["id"]

    page = client.get("/api/v1/audit-logs?limit=1&offset=1", headers=admin_headers)
    assert page.status_code == 200
    assert page.json()["limit"] == 1
    assert page.json()["offset"] == 1
    assert page.json()["total"] >= 1


def test_audit_history_is_not_visible_to_front_desk(client):
    headers = bearer(client, "housekeeping@example.com")
    assert client.get("/api/v1/audit-logs", headers=headers).status_code == 403