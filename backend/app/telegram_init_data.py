import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

MAX_INIT_DATA_LENGTH = 4096
MAX_FUTURE_SKEW_SECONDS = 60
MAX_TELEGRAM_ID = 2**53 - 1


class InitDataError(Exception):
    pass


@dataclass(frozen=True)
class TelegramIdentity:
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Return the hash Telegram would attach to these fields."""
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    return hmac.new(_secret_key(bot_token), data_check_string.encode(), hashlib.sha256).hexdigest()


def _optional_str(value: object, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InitDataError("user field has an invalid type")
    return value[:limit] or None


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int,
    now: float | None = None,
) -> TelegramIdentity:
    if not init_data or len(init_data) > MAX_INIT_DATA_LENGTH:
        raise InitDataError("init data is missing or too long")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise InitDataError("init data is malformed") from exc

    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise InitDataError("init data contains duplicate keys")
        fields[key] = value

    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise InitDataError("init data is not signed")

    expected_hash = sign_init_data(fields, bot_token)
    if not hmac.compare_digest(expected_hash, received_hash.lower()):
        raise InitDataError("init data signature mismatch")

    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, ValueError) as exc:
        raise InitDataError("auth_date is missing or invalid") from exc

    current = time.time() if now is None else now
    if auth_date > current + MAX_FUTURE_SKEW_SECONDS:
        raise InitDataError("auth_date is in the future")
    if current - auth_date > max_age_seconds:
        raise InitDataError("init data has expired")

    try:
        user = json.loads(fields["user"])
    except (KeyError, ValueError) as exc:
        raise InitDataError("user is missing or invalid") from exc
    if not isinstance(user, dict):
        raise InitDataError("user is missing or invalid")

    telegram_id = user.get("id")
    if isinstance(telegram_id, bool) or not isinstance(telegram_id, int):
        raise InitDataError("user id is invalid")
    if not 0 < telegram_id <= MAX_TELEGRAM_ID:
        raise InitDataError("user id is out of range")

    return TelegramIdentity(
        telegram_id=telegram_id,
        username=_optional_str(user.get("username"), 64),
        first_name=_optional_str(user.get("first_name"), 128),
        last_name=_optional_str(user.get("last_name"), 128),
    )
