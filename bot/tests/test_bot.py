import io
from dataclasses import dataclass, field
from types import SimpleNamespace

import httpx
import pytest
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from app import texts
from app.api_client import ApiError, CatalogApi
from app.config import BotSettings
from app.handlers import CaptionError, on_create_requested, on_start, parse_caption, submit_product
from app.keyboards import catalog_keyboard, main_menu

ADMIN_ID = 1001
USER_ID = 2002
SERVICE_TOKEN = "s" * 40


def make_settings(**overrides) -> BotSettings:
    values = {
        "telegram_bot_token": "123:abc",
        "admin_telegram_ids": str(ADMIN_ID),
        "bot_api_token": SERVICE_TOKEN,
        "webapp_url": "https://catalog.example.com",
    }
    values.update(overrides)
    return BotSettings(_env_file=None, **values)


@dataclass
class FakeMessage:
    user_id: int | None
    caption: str | None = None
    answers: list[tuple[str, object]] = field(default_factory=list)

    @property
    def from_user(self):
        return None if self.user_id is None else SimpleNamespace(id=self.user_id)

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))


class FakeBot:
    def __init__(self) -> None:
        self.downloads: list[str] = []

    async def download(self, file_id, destination):
        self.downloads.append(file_id)
        destination.write(b"image-bytes")


class FakeApi:
    def __init__(self, error: ApiError | None = None) -> None:
        self.error = error
        self.calls: list[tuple[int, str, bytes, str]] = []

    async def create_product(self, acting_user_id, name, image, filename):
        self.calls.append((acting_user_id, name, image.read(), filename))
        if self.error:
            raise self.error
        return {"id": "p1", "name": name}


async def submit(message, api=None, bot=None, file_size=100):
    api = api or FakeApi()
    bot = bot or FakeBot()
    await submit_product(
        message, bot, make_settings(), api, file_id="file-1", file_size=file_size, filename="photo.jpg"
    )
    return api, bot


def test_parse_caption_normalizes_whitespace():
    assert parse_caption("  Desk \n lamp  ") == "Desk lamp"


@pytest.mark.parametrize("caption", [None, "", "   \n"])
def test_parse_caption_requires_a_name(caption):
    with pytest.raises(CaptionError, match="названия"):
        parse_caption(caption)


def test_parse_caption_limits_length():
    with pytest.raises(CaptionError, match="120"):
        parse_caption("x" * 121)


def test_catalog_keyboard_requires_https():
    assert catalog_keyboard("http://localhost:3000") is None
    keyboard = catalog_keyboard("https://catalog.example.com")
    assert isinstance(keyboard, InlineKeyboardMarkup)
    assert keyboard.inline_keyboard[0][0].web_app.url == "https://catalog.example.com"


def test_create_button_is_visible_only_to_admins():
    admin_menu = main_menu(is_admin=True)
    assert isinstance(admin_menu, ReplyKeyboardMarkup)
    assert admin_menu.keyboard[0][0].text == texts.CREATE_BUTTON
    assert isinstance(main_menu(is_admin=False), ReplyKeyboardRemove)


async def test_start_greets_users_without_admin_menu():
    message = FakeMessage(USER_ID)
    await on_start(message, make_settings())
    [(text, keyboard)] = message.answers
    assert text == texts.GREETING
    assert isinstance(keyboard, InlineKeyboardMarkup)


async def test_start_shows_admin_menu_to_admins():
    message = FakeMessage(ADMIN_ID)
    await on_start(message, make_settings())
    assert [text for text, _ in message.answers] == [texts.GREETING, texts.ADMIN_MENU]
    assert isinstance(message.answers[1][1], ReplyKeyboardMarkup)


async def test_start_explains_missing_https_webapp():
    message = FakeMessage(USER_ID)
    await on_start(message, make_settings(webapp_url="http://localhost:3000"))
    [(text, keyboard)] = message.answers
    assert texts.CATALOG_UNAVAILABLE in text
    assert keyboard is None


async def test_create_command_is_refused_for_users():
    message = FakeMessage(USER_ID)
    await on_create_requested(message, make_settings())
    assert message.answers[0][0] == texts.ADMIN_ONLY


async def test_admin_photo_with_caption_is_submitted():
    message = FakeMessage(ADMIN_ID, caption=" New  lamp ")
    api, bot = await submit(message)
    assert api.calls == [(ADMIN_ID, "New lamp", b"image-bytes", "photo.jpg")]
    assert bot.downloads == ["file-1"]
    assert message.answers[0][0] == texts.product_created("New lamp")


async def test_user_photo_is_refused_without_download():
    message = FakeMessage(USER_ID, caption="Lamp")
    api, bot = await submit(message)
    assert api.calls == [] and bot.downloads == []
    assert message.answers[0][0] == texts.ADMIN_ONLY


async def test_admin_photo_without_caption_is_refused():
    message = FakeMessage(ADMIN_ID, caption=None)
    api, _ = await submit(message)
    assert api.calls == []
    assert message.answers[0][0] == texts.MISSING_CAPTION


async def test_oversized_photo_is_refused_before_download():
    message = FakeMessage(ADMIN_ID, caption="Lamp")
    api, bot = await submit(message, file_size=10 * 1024 * 1024)
    assert api.calls == [] and bot.downloads == []
    assert message.answers[0][0] == texts.TOO_LARGE


async def test_api_errors_are_relayed_to_admin():
    message = FakeMessage(ADMIN_ID, caption="Lamp")
    await submit(message, api=FakeApi(error=ApiError(texts.UNSUPPORTED_IMAGE, 415)))
    assert message.answers[0][0] == texts.UNSUPPORTED_IMAGE


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, texts.SERVICE_AUTH_FAILED),
        (403, texts.ADMIN_ONLY),
        (413, texts.TOO_LARGE),
        (415, texts.UNSUPPORTED_IMAGE),
        (422, texts.INVALID_PRODUCT),
        (500, texts.TEMPORARY_FAILURE),
        (502, texts.TEMPORARY_FAILURE),
    ],
)
async def test_api_client_maps_error_statuses(status, expected):
    api = CatalogApi("http://api", SERVICE_TOKEN, transport=httpx.MockTransport(lambda _: httpx.Response(status)))
    with pytest.raises(ApiError) as caught:
        await api.create_product(ADMIN_ID, "Lamp", _bytes(), "photo.jpg")
    assert caught.value.user_message == expected
    await api.close()


async def test_api_client_sends_service_credentials_and_multipart():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["user"] = request.headers["x-telegram-user-id"]
        seen["body"] = request.read()
        return httpx.Response(201, json={"id": "p1", "name": "Lamp"})

    api = CatalogApi("http://api", SERVICE_TOKEN, transport=httpx.MockTransport(handler))
    assert (await api.create_product(ADMIN_ID, "Lamp", _bytes(), "photo.jpg"))["name"] == "Lamp"
    assert seen["auth"] == f"service {SERVICE_TOKEN}"
    assert seen["user"] == str(ADMIN_ID)
    assert b'name="name"' in seen["body"] and b'name="image"' in seen["body"]
    await api.close()


async def test_api_client_maps_network_failures():
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    api = CatalogApi("http://api", SERVICE_TOKEN, transport=httpx.MockTransport(handler))
    with pytest.raises(ApiError) as caught:
        await api.create_product(ADMIN_ID, "Lamp", _bytes(), "photo.jpg")
    assert caught.value.user_message == texts.TEMPORARY_FAILURE
    await api.close()


def test_webhook_mode_requires_https_and_secret():
    with pytest.raises(ValueError, match="https"):
        make_settings(webhook_base_url="http://example.com", webhook_secret="a" * 40)
    with pytest.raises(ValueError, match="WEBHOOK_SECRET"):
        make_settings(webhook_base_url="https://example.com", webhook_secret="short")
    settings = make_settings(webhook_base_url="https://example.com/", webhook_secret="a" * 40)
    assert settings.webhook_url == "https://example.com/telegram/webhook"


def _bytes():
    return io.BytesIO(b"image")
