from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from app import texts


def catalog_keyboard(webapp_url: str) -> InlineKeyboardMarkup | None:
    # Telegram only accepts Mini App buttons that point to an https URL.
    if not webapp_url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.OPEN_CATALOG, web_app=WebAppInfo(url=webapp_url))]]
    )


def main_menu(is_admin: bool) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    if not is_admin:
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.CREATE_BUTTON)]],
        resize_keyboard=True,
        is_persistent=True,
    )
