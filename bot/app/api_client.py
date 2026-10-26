import logging
from typing import Any, BinaryIO

import httpx

from app import texts

logger = logging.getLogger(__name__)

STATUS_MESSAGES = {
    401: texts.SERVICE_AUTH_FAILED,
    403: texts.ADMIN_ONLY,
    413: texts.TOO_LARGE,
    415: texts.UNSUPPORTED_IMAGE,
    422: texts.INVALID_PRODUCT,
}


class ApiError(Exception):
    def __init__(self, user_message: str, status: int | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.status = status


def error_for_status(status: int) -> ApiError:
    return ApiError(STATUS_MESSAGES.get(status, texts.TEMPORARY_FAILURE), status)


class CatalogApi:
    """Thin client for the catalog API. All validation and authorization happen server-side."""

    def __init__(self, base_url: str, service_token: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._service_token = service_token
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30.0, connect=5.0),
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def create_product(
        self, acting_user_id: int, name: str, image: BinaryIO, filename: str
    ) -> dict[str, Any]:
        try:
            response = await self._client.post(
                "/api/v1/products",
                headers={
                    "Authorization": f"service {self._service_token}",
                    "X-Telegram-User-Id": str(acting_user_id),
                },
                data={"name": name},
                files={"image": (filename, image, "application/octet-stream")},
            )
        except httpx.HTTPError as exc:
            logger.warning("catalog API request failed: %s", type(exc).__name__)
            raise ApiError(texts.TEMPORARY_FAILURE) from exc

        if response.status_code != 201:
            logger.warning(
                "catalog API rejected product: status=%s request_id=%s",
                response.status_code,
                response.headers.get("x-request-id"),
            )
            raise error_for_status(response.status_code)
        return response.json()
