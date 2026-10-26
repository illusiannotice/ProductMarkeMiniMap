import re
from functools import cached_property

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WEBHOOK_SECRET_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,256}")


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    telegram_bot_token: SecretStr
    admin_telegram_ids: str = ""
    api_url: str = "http://api:8000"
    bot_api_token: SecretStr
    webapp_url: str = ""

    webhook_base_url: str = ""
    webhook_path: str = "/telegram/webhook"
    webhook_secret: SecretStr = SecretStr("")
    port: int = 8081

    max_photo_bytes: int = Field(default=5 * 1024 * 1024, ge=1024)
    log_level: str = "INFO"

    @field_validator("admin_telegram_ids")
    @classmethod
    def _check_admin_ids(cls, value: str) -> str:
        for item in filter(None, (part.strip() for part in value.split(","))):
            if not item.isdigit() or int(item) <= 0:
                raise ValueError("ADMIN_TELEGRAM_IDS must be a comma-separated list of Telegram user IDs")
        return value

    @field_validator("webhook_path")
    @classmethod
    def _check_webhook_path(cls, value: str) -> str:
        if not re.fullmatch(r"/[A-Za-z0-9/_-]*", value):
            raise ValueError("WEBHOOK_PATH must be an absolute URL path")
        return value

    @model_validator(mode="after")
    def _check_webhook(self) -> "BotSettings":
        if self.webhook_base_url:
            if not self.webhook_base_url.startswith("https://"):
                raise ValueError("WEBHOOK_BASE_URL must use https")
            if not WEBHOOK_SECRET_PATTERN.fullmatch(self.webhook_secret.get_secret_value()):
                raise ValueError("WEBHOOK_SECRET must be 32-256 characters of A-Z, a-z, 0-9, _ or -")
        return self

    @cached_property
    def admin_ids(self) -> frozenset[int]:
        return frozenset(int(part) for part in self.admin_telegram_ids.split(",") if part.strip())

    @property
    def webhook_url(self) -> str:
        return self.webhook_base_url.rstrip("/") + self.webhook_path

    @property
    def webapp_is_https(self) -> bool:
        return self.webapp_url.startswith("https://")

    def is_admin(self, telegram_id: int | None) -> bool:
        return telegram_id is not None and telegram_id in self.admin_ids
