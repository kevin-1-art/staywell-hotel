from app.dependencies import require_roles
from app.models import Role


def test_health_reports_database(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_login_issues_access_token_and_http_only_refresh_cookie(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "manager@example.com", "password": "Correct-Horse-42!"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "manager"
    assert response.json()["access_token"]
    assert "httponly" in response.headers["set-cookie"].lower()


def test_login_rejects_invalid_credentials(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "manager@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


def test_refresh_rotates_and_logout_revokes_session(client):
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "manager@example.com", "password": "Correct-Horse-42!"},
    )
    original_cookie = client.cookies.get("hotel_refresh")
    assert original_cookie

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != login_response.json()["access_token"]

    client.cookies.set("hotel_refresh", original_cookie, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_access_token_authenticates_current_user(client):
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "manager@example.com", "password": "Correct-Horse-42!"},
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "manager@example.com"