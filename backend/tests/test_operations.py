def login_token(client, email):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Correct-Horse-42!"},
    )
    return response.json()["access_token"]


def test_manager_can_manage_stock_rates_and_view_configuration(client):
    headers = {"Authorization": f"Bearer {login_token(client, 'manager@example.com')}"}
    created = client.post(
        "/api/v1/inventory",
        headers=headers,
        json={"sku": "LINEN-01", "name": "Bath towel", "unit": "piece", "quantity_on_hand": 2, "reorder_level": 5, "unit_cost_ugx": 12000},
    )
    assert created.status_code == 201
    item_id = created.json()["id"]
    low_stock = client.get("/api/v1/inventory?low_stock=true", headers=headers)
    assert low_stock.json()["items"][0]["low_stock"] is True

    adjusted = client.post(
        f"/api/v1/inventory/{item_id}/adjust",
        headers=headers,
        json={"quantity_delta": 8, "reason": "Supplier delivery"},
    )
    assert adjusted.json()["quantity_on_hand"] == 10
    negative = client.post(
        f"/api/v1/inventory/{item_id}/adjust",
        headers=headers,
        json={"quantity_delta": -11, "reason": "Bad stock count"},
    )
    assert negative.status_code == 409

    rate = client.post(
        "/api/v1/rates",
        headers=headers,
        json={"name": "Corporate 5", "rule_type": "corporate", "adjustment_type": "percent", "adjustment_value": -500, "company_name": "Example Ltd"},
    )
    assert rate.status_code == 201
    assert client.get("/api/v1/settings", headers=headers).status_code == 200


def test_notification_lists_are_private_and_settings_are_admin_only(client):
    manager_headers = {"Authorization": f"Bearer {login_token(client, 'manager@example.com')}"}
    frontdesk_headers = {"Authorization": f"Bearer {login_token(client, 'housekeeping@example.com')}"}

    manager_notice = client.get("/api/v1/notifications", headers=manager_headers)
    staff_notice = client.get("/api/v1/notifications", headers=frontdesk_headers)
    assert manager_notice.status_code == 200
    assert staff_notice.status_code == 200
    assert manager_notice.json()["items"] == []
    assert staff_notice.json()["items"] == []
    assert client.put("/api/v1/settings/charges", headers=manager_headers, json={"tax_basis_points": 1800, "service_basis_points": 500}).status_code == 403


def test_inventory_remove_archives_only_zero_stock_and_preserves_admin_history(client):
    manager_headers = {"Authorization": f"Bearer {login_token(client, 'manager@example.com')}"}
    created = client.post(
        "/api/v1/inventory",
        headers=manager_headers,
        json={"sku": "ARCHIVE-01", "name": "Retired linen", "unit": "piece", "quantity_on_hand": 2, "reorder_level": 1, "unit_cost_ugx": 7000},
    )
    item_id = created.json()["id"]
    assert client.delete(f"/api/v1/inventory/{item_id}", headers=manager_headers).status_code == 409
    adjusted = client.post(
        f"/api/v1/inventory/{item_id}/adjust",
        headers=manager_headers,
        json={"quantity_delta": -2, "reason": "Disposed damaged stock"},
    )
    assert adjusted.json()["quantity_on_hand"] == 0

    housekeeping = login_token(client, "housekeeping@example.com")
    housekeeping_headers = {"Authorization": f"Bearer {housekeeping}"}
    assert client.delete(f"/api/v1/inventory/{item_id}", headers=housekeeping_headers).status_code == 403

    archived = client.delete(f"/api/v1/inventory/{item_id}", headers=manager_headers)
    assert archived.status_code == 200
    assert archived.json()["archived_at"]
    assert all(item["id"] != item_id for item in client.get("/api/v1/inventory", headers=manager_headers).json()["items"])
    archived_items = client.get("/api/v1/inventory?include_archived=true", headers=manager_headers)
    assert archived_items.status_code == 200
    assert any(item["id"] == item_id and item["archived_at"] for item in archived_items.json()["items"])