import asyncio
import json
import logging
import sys
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app import texts
from app.api_client import CatalogApi
from app.config import BotSettings
from app.handlers import router

logger = logging.getLogger("app.bot")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)


def build_dispatcher(settings: BotSettings, api: CatalogApi) -> Dispatcher:
    dispatcher = Dispatcher(settings=settings, api=api)
    dispatcher.include_router(router)

    async def configure_bot(bot: Bot) -> None:
        await bot.set_my_commands([BotCommand(command="start", description=texts.OPEN_CATALOG)])
        if settings.webapp_is_https:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text=texts.CATALOG_MENU, web_app=WebAppInfo(url=settings.webapp_url))
            )
        else:
            logger.warning("WEBAPP_URL is not https; the Mini App button is disabled")

    async def close_api() -> None:
        await api.close()

    dispatcher.startup.register(configure_bot)
    dispatcher.shutdown.register(close_api)
    return dispatcher


def run_webhook(settings: BotSettings, bot: Bot, dispatcher: Dispatcher) -> None:
    """Stateless mode: Telegram delivers each update to one replica behind the proxy."""

    async def register_webhook(bot: Bot) -> None:
        await bot.set_webhook(
            settings.webhook_url,
            secret_token=settings.webhook_secret.get_secret_value(),
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
        logger.info("webhook registered at %s", settings.webhook_url)

    dispatcher.startup.register(register_webhook)

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app = web.Application()
    app.router.add_get("/health", health)
    SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=settings.webhook_secret.get_secret_value(),
    ).register(app, path=settings.webhook_path)
    setup_application(app, dispatcher, bot=bot)
    web.run_app(app, host="0.0.0.0", port=settings.port, print=None)


async def run_polling(bot: Bot, dispatcher: Dispatcher, api: CatalogApi) -> None:
    """Local development only: long polling must run in exactly one process."""
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await api.close()
        await bot.session.close()


def main() -> None:
    settings = BotSettings()
    configure_logging(settings.log_level)
    api = CatalogApi(settings.api_url, settings.bot_api_token.get_secret_value())
    bot = Bot(token=settings.telegram_bot_token.get_secret_value())
    dispatcher = build_dispatcher(settings, api)

    if settings.webhook_base_url:
        run_webhook(settings, bot, dispatcher)
    else:
        logger.warning("WEBHOOK_BASE_URL is empty; using long polling (run a single bot replica)")
        asyncio.run(run_polling(bot, dispatcher, api))


if __name__ == "__main__":
    main()
