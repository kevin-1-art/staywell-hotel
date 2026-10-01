import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import app


def test_production_requires_a_non_placeholder_jwt_secret_and_secure_cookies():
    with pytest.raises(ValidationError):
        Settings(app_env="production", jwt_secret="short", seed_user_password="Bootstrap-Password-42!")

    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            jwt_secret="unique-production-secret-that-is-at-least-32-characters",
            trusted_hosts=["hotel.example.com"],
        )

    settings = Settings(
        app_env="production",
        jwt_secret="unique-production-secret-that-is-at-least-32-characters",
        seed_user_password="Unique-Bootstrap-Password-42!",
        trusted_hosts=["hotel.example.com"],
        cookie_secure=False,
    )
    assert settings.cookie_secure is True


def test_production_rejects_wildcard_trusted_hosts():
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            jwt_secret="unique-production-secret-that-is-at-least-32-characters",
            trusted_hosts=["*"],
        )


def test_api_sets_security_headers_and_rejects_untrusted_host(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"

    protected = client.get("/api/v1/admin/users", headers={"Host": "attacker.invalid"})
    assert protected.status_code == 400

    private = client.get("/api/v1/admin/users")
    assert private.status_code == 401
    assert private.headers["cache-control"] == "no-store"

    preflight = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://attacker.invalid",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in preflight.headers


def test_login_is_rate_limited(client):
    responses = [
        client.post("/api/v1/auth/login", json={"email": "missing@example.com", "password": "wrong"})
        for _ in range(9)
    ]
    assert [response.status_code for response in responses[:8]] == [401] * 8
    assert responses[8].status_code == 429
