import httpx
import pytest

from app.factory import create_app
from tests.conftest import ADMIN_ID, SERVICE_TOKEN, USER_ID, make_settings, service_headers, tma_header


async def test_me_requires_authentication(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "tma"


async def test_me_reports_user_role(client):
    response = await client.get("/api/v1/auth/me", headers={"Authorization": tma_header(USER_ID)})
    assert response.status_code == 200
    assert response.json() == {
        "telegram_id": USER_ID,
        "username": "ann",
        "first_name": "Ann",
        "last_name": "Lee",
        "role": "User",
    }


async def test_me_reports_admin_role(client):
    response = await client.get("/api/v1/auth/me", headers={"Authorization": tma_header(ADMIN_ID)})
    assert response.status_code == 200
    assert response.json()["role"] == "Admin"


@pytest.mark.parametrize(
    "header",
    ["Bearer abc", "tma ", "tma garbage", f"dev {USER_ID}", "basic dXNlcjpwYXNz"],
)
async def test_unsupported_or_invalid_credentials_are_rejected(client, header):
    response = await client.get("/api/v1/auth/me", headers={"Authorization": header})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing Telegram authentication"}


async def test_service_credential_acts_as_given_user(client):
    response = await client.get("/api/v1/auth/me", headers=service_headers(ADMIN_ID))
    assert response.status_code == 200
    assert response.json()["role"] == "Admin"


@pytest.mark.parametrize(
    "headers",
    [
        service_headers(ADMIN_ID, token="x" * 40),
        {"Authorization": f"service {SERVICE_TOKEN}"},
        service_headers("1 OR 1=1"),
        service_headers("1001; DROP TABLE users"),
        service_headers("0"),
        service_headers("99999999999999999999"),
    ],
)
async def test_bad_service_requests_are_rejected(client, headers):
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401


async def test_dev_auth_works_only_when_explicitly_enabled(engine, storage):
    settings = make_settings(environment="development", dev_auth_enabled=True)
    app = create_app(settings, engine=engine, storage=storage)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"dev {ADMIN_ID}"})
    assert response.status_code == 200
    assert response.json()["role"] == "Admin"


def test_dev_auth_cannot_be_enabled_in_production():
    with pytest.raises(ValueError, match="DEV_AUTH_ENABLED"):
        make_settings(environment="production", dev_auth_enabled=True)


def test_short_service_token_is_refused():
    with pytest.raises(ValueError, match="BOT_API_TOKEN"):
        make_settings(bot_api_token="short")
