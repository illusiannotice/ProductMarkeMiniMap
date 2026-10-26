import hmac
import logging
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import get_session
from app.telegram_init_data import (
    MAX_TELEGRAM_ID,
    InitDataError,
    TelegramIdentity,
    validate_init_data,
)
from app.users import upsert_user

logger = logging.getLogger(__name__)

ACTING_USER_HEADER = "x-telegram-user-id"


class Role(StrEnum):
    USER = "User"
    ADMIN = "Admin"


@dataclass(frozen=True)
class Principal:
    identity: TelegramIdentity
    role: Role

    @property
    def telegram_id(self) -> int:
        return self.identity.telegram_id


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing Telegram authentication",
        headers={"WWW-Authenticate": "tma"},
    )


def _parse_telegram_id(raw: str | None) -> int:
    if not raw or not raw.isascii() or not raw.isdigit() or len(raw) > 16:
        raise _unauthorized()

    value = int(raw)
    if not 0 < value <= MAX_TELEGRAM_ID:
        raise _unauthorized()
    return value


def _identity_from_header(request: Request, settings: Settings) -> TelegramIdentity:
    header = request.headers.get("authorization", "")
    scheme, _, credentials = header.partition(" ")
    scheme = scheme.lower()
    credentials = credentials.strip()
    if not credentials:
        raise _unauthorized()

    if scheme == "tma":
        try:
            return validate_init_data(
                credentials,
                settings.telegram_bot_token.get_secret_value(),
                settings.init_data_max_age_seconds,
            )
        except InitDataError as exc:
            logger.info("rejected Telegram init data: %s", exc)
            raise _unauthorized() from None

    if scheme == "service":
        expected = settings.bot_api_token.get_secret_value().encode()
        if not hmac.compare_digest(credentials.encode(), expected):
            logger.warning("rejected service credential")
            raise _unauthorized()
        return TelegramIdentity(telegram_id=_parse_telegram_id(request.headers.get(ACTING_USER_HEADER)))

    if scheme == "dev" and settings.dev_auth_allowed:
        return TelegramIdentity(telegram_id=_parse_telegram_id(credentials), first_name="Developer")

    raise _unauthorized()


async def get_principal(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Principal:
    settings = get_settings(request)
    identity = _identity_from_header(request, settings)
    await upsert_user(session, identity)
    await session.commit()
    role = Role.ADMIN if identity.telegram_id in settings.admin_ids else Role.USER
    return Principal(identity=identity, role=role)


async def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.role is not Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
    return principal
