import io
import json
import time
from collections.abc import AsyncIterator
from urllib.parse import urlencode

import httpx
import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Settings
from app.factory import create_app
from app.models import Base
from app.telegram_init_data import sign_init_data

BOT_TOKEN = "123456:TEST-bot-token"
SERVICE_TOKEN = "s" * 40
ADMIN_ID = 1001
USER_ID = 2002


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def ensure_bucket(self) -> None:
        pass

    def is_ready(self) -> bool:
        return True

    def put(self, key, data, length, content_type) -> None:
        payload = data.read()
        assert len(payload) == length
        self.objects[key] = (payload, content_type)

    def delete(self, key) -> None:
        self.objects.pop(key, None)

    def presign(self, key) -> str:
        return f"https://cdn.test/{key}?X-Amz-Signature=test"


def make_settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "telegram_bot_token": BOT_TOKEN,
        "admin_telegram_ids": str(ADMIN_ID),
        "bot_api_token": SERVICE_TOKEN,
        "db_user": "catalog_app",
        "db_password": "unused",
        "minio_endpoint": "minio:9000",
        "minio_public_endpoint": "localhost:8080",
        "minio_access_key": "unused",
        "minio_secret_key": "unused",
        "max_image_bytes": 200_000,
        "max_image_pixels": 4_000_000,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def tma_header(user_id: int, *, auth_date: int | None = None, bot_token: str = BOT_TOKEN) -> str:
    fields = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {"id": user_id, "first_name": "Ann", "last_name": "Lee", "username": "ann"},
            separators=(",", ":"),
        ),
    }
    fields["hash"] = sign_init_data(fields, bot_token)
    return "tma " + urlencode(fields)


def service_headers(acting_user: str | int, token: str = SERVICE_TOKEN) -> dict[str, str]:
    return {"Authorization": f"service {token}", "X-Telegram-User-Id": str(acting_user)}


def image_bytes(image_format: str = "PNG", size: tuple[int, int] = (8, 8)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, format=image_format)
    return buffer.getvalue()


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
async def engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def client(settings, engine, storage) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, engine=engine, storage=storage)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
