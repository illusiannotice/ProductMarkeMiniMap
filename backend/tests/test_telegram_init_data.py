import json
import time
from urllib.parse import urlencode

import pytest

from app.telegram_init_data import InitDataError, sign_init_data, validate_init_data
from tests.conftest import BOT_TOKEN, tma_header

MAX_AGE = 3600


def raw(header: str) -> str:
    return header.removeprefix("tma ")


def signed(fields: dict[str, str]) -> str:
    return urlencode({**fields, "hash": sign_init_data(fields, BOT_TOKEN)})


def test_valid_init_data_returns_identity():
    identity = validate_init_data(raw(tma_header(42)), BOT_TOKEN, MAX_AGE)
    assert identity.telegram_id == 42
    assert identity.username == "ann"
    assert identity.first_name == "Ann"


def test_tampered_user_is_rejected():
    tampered = raw(tma_header(42)).replace("%22id%22%3A42", "%22id%22%3A43")
    with pytest.raises(InitDataError, match="signature"):
        validate_init_data(tampered, BOT_TOKEN, MAX_AGE)


def test_wrong_bot_token_is_rejected():
    with pytest.raises(InitDataError, match="signature"):
        validate_init_data(raw(tma_header(42, bot_token="999:other")), BOT_TOKEN, MAX_AGE)


def test_expired_init_data_is_rejected():
    old = int(time.time()) - MAX_AGE - 10
    with pytest.raises(InitDataError, match="expired"):
        validate_init_data(raw(tma_header(42, auth_date=old)), BOT_TOKEN, MAX_AGE)


def test_future_auth_date_is_rejected():
    future = int(time.time()) + 3600
    with pytest.raises(InitDataError, match="future"):
        validate_init_data(raw(tma_header(42, auth_date=future)), BOT_TOKEN, MAX_AGE)


def test_missing_hash_is_rejected():
    data = urlencode({"auth_date": str(int(time.time())), "user": json.dumps({"id": 1})})
    with pytest.raises(InitDataError, match="not signed"):
        validate_init_data(data, BOT_TOKEN, MAX_AGE)


def test_duplicate_keys_are_rejected():
    data = raw(tma_header(42)) + "&auth_date=1"
    with pytest.raises(InitDataError, match="duplicate"):
        validate_init_data(data, BOT_TOKEN, MAX_AGE)


@pytest.mark.parametrize("user", ['{"id": true}', '{"id": "42"}', '{"id": -5}', "[]", "not json"])
def test_invalid_user_payload_is_rejected(user):
    data = signed({"auth_date": str(int(time.time())), "user": user})
    with pytest.raises(InitDataError):
        validate_init_data(data, BOT_TOKEN, MAX_AGE)


def test_oversized_init_data_is_rejected():
    with pytest.raises(InitDataError, match="too long"):
        validate_init_data("a=" + "x" * 5000, BOT_TOKEN, MAX_AGE)
