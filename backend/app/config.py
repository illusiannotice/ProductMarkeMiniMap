from functools import cached_property, lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "catalog"


class MigrationSettings(DatabaseSettings):
    migration_db_user: str
    migration_db_password: SecretStr
    db_user: str
    db_password: SecretStr

    @property
    def migration_database_url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.migration_db_user,
            password=self.migration_db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    @model_validator(mode="after")
    def _distinct_accounts(self) -> "MigrationSettings":
        if self.db_user == self.migration_db_user:
            raise ValueError("DB_USER must differ from MIGRATION_DB_USER")
        return self


class Settings(DatabaseSettings):
    environment: Literal["development", "production"] = "production"
    dev_auth_enabled: bool = False
    log_level: str = "INFO"

    telegram_bot_token: SecretStr
    admin_telegram_ids: str = ""
    init_data_max_age_seconds: int = Field(default=86400, ge=60)
    bot_api_token: SecretStr

    db_user: str
    db_password: SecretStr

    minio_endpoint: str
    minio_public_endpoint: str
    minio_access_key: SecretStr
    minio_secret_key: SecretStr
    minio_bucket: str = "product-images"
    minio_secure: bool = False
    minio_public_secure: bool = False
    minio_region: str = "us-east-1"
    presign_ttl_seconds: int = Field(default=900, ge=60, le=86400)

    max_image_bytes: int = Field(default=5 * 1024 * 1024, ge=1024)
    max_image_pixels: int = Field(default=40_000_000, ge=1)
    max_name_length: int = Field(default=120, ge=1, le=120)

    @field_validator("admin_telegram_ids")
    @classmethod
    def _check_admin_ids(cls, value: str) -> str:
        for item in filter(None, (part.strip() for part in value.split(","))):
            if not item.isdigit() or int(item) <= 0:
                raise ValueError("ADMIN_TELEGRAM_IDS must be a comma-separated list of Telegram user IDs")
        return value

    @field_validator("bot_api_token")
    @classmethod
    def _check_bot_api_token(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("BOT_API_TOKEN must be at least 32 characters")
        return value

    @model_validator(mode="after")
    def _forbid_dev_auth_in_production(self) -> "Settings":
        if self.dev_auth_enabled and self.environment != "development":
            raise ValueError("DEV_AUTH_ENABLED is only allowed when ENVIRONMENT=development")
        return self

    @cached_property
    def admin_ids(self) -> frozenset[int]:
        return frozenset(int(part) for part in self.admin_telegram_ids.split(",") if part.strip())

    @property
    def dev_auth_allowed(self) -> bool:
        return self.environment == "development" and self.dev_auth_enabled

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
