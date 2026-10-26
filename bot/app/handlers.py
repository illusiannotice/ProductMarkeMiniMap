import logging
import tempfile

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app import texts
from app.api_client import ApiError, CatalogApi
from app.config import BotSettings
from app.keyboards import catalog_keyboard, main_menu

logger = logging.getLogger(__name__)

router = Router(name="catalog")

MAX_NAME_LENGTH = 120
IMAGE_DOCUMENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class CaptionError(ValueError):
    pass


def parse_caption(caption: str | None) -> str:
    name = " ".join((caption or "").split())
    if not name:
        raise CaptionError(texts.MISSING_CAPTION)
    if len(name) > MAX_NAME_LENGTH:
        raise CaptionError(texts.NAME_TOO_LONG.format(limit=MAX_NAME_LENGTH))
    return name


async def send_greeting(message: Message, settings: BotSettings) -> None:
    keyboard = catalog_keyboard(settings.webapp_url)
    text = texts.GREETING if keyboard else f"{texts.GREETING}\n{texts.CATALOG_UNAVAILABLE}"
    await message.answer(text, reply_markup=keyboard)


@router.message(CommandStart())
async def on_start(message: Message, settings: BotSettings) -> None:
    await send_greeting(message, settings)
    is_admin = settings.is_admin(message.from_user and message.from_user.id)
    if is_admin:
        await message.answer(texts.ADMIN_MENU, reply_markup=main_menu(is_admin=True))


@router.message(F.text == texts.CREATE_BUTTON)
async def on_create_requested(message: Message, settings: BotSettings) -> None:
    if not settings.is_admin(message.from_user and message.from_user.id):
        await message.answer(texts.ADMIN_ONLY, reply_markup=main_menu(is_admin=False))
        return
    await message.answer(texts.CREATE_INSTRUCTIONS)


async def submit_product(
    message: Message,
    bot: Bot,
    settings: BotSettings,
    api: CatalogApi,
    *,
    file_id: str,
    file_size: int | None,
    filename: str,
) -> None:
    user = message.from_user
    if user is None or not settings.is_admin(user.id):
        await message.answer(texts.ADMIN_ONLY)
        return

    try:
        name = parse_caption(message.caption)
    except CaptionError as exc:
        await message.answer(str(exc))
        return

    if file_size is not None and file_size > settings.max_photo_bytes:
        await message.answer(texts.TOO_LARGE)
        return

    with tempfile.TemporaryFile() as image:
        await bot.download(file_id, destination=image)
        image.seek(0)
        try:
            product = await api.create_product(user.id, name, image, filename)
        except ApiError as exc:
            await message.answer(exc.user_message)
            return

    logger.info("admin %s created product %s", user.id, product.get("id"))
    await message.answer(
        texts.product_created(product.get("name", name)),
        reply_markup=catalog_keyboard(settings.webapp_url),
    )


@router.message(F.photo)
async def on_photo(message: Message, bot: Bot, settings: BotSettings, api: CatalogApi) -> None:
    photo = message.photo[-1]
    await submit_product(
        message, bot, settings, api, file_id=photo.file_id, file_size=photo.file_size, filename="photo.jpg"
    )


@router.message(F.document.mime_type.in_(IMAGE_DOCUMENT_TYPES))
async def on_image_document(message: Message, bot: Bot, settings: BotSettings, api: CatalogApi) -> None:
    document = message.document
    await submit_product(
        message,
        bot,
        settings,
        api,
        file_id=document.file_id,
        file_size=document.file_size,
        filename="image",
    )


@router.message()
async def on_any_message(message: Message, settings: BotSettings) -> None:
    await send_greeting(message, settings)
