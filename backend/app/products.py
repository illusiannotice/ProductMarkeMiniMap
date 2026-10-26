import logging
import unicodedata
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.auth import Principal, get_principal, require_admin
from app.db import get_session
from app.images import ImageTooLargeError, InvalidImageError, inspect_image
from app.models import Product
from app.schemas import ProductOut, ProductPage
from app.storage import ImageStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/products", tags=["products"])

MULTIPART_OVERHEAD_BYTES = 64 * 1024
FORBIDDEN_CATEGORIES = {"Cc", "Cs", "Co", "Cn"}


def normalize_name(raw: str, max_length: int) -> str:
    name = " ".join(unicodedata.normalize("NFC", raw).split())
    if not name:
        raise ValueError("name is required")
    if len(name) > max_length:
        raise ValueError(f"name must be at most {max_length} characters")
    if any(unicodedata.category(char) in FORBIDDEN_CATEGORIES for char in name):
        raise ValueError("name contains unsupported characters")
    return name


def get_storage(request: Request) -> ImageStorage:
    return request.app.state.storage


def to_out(product: Product, storage: ImageStorage) -> ProductOut:
    return ProductOut(
        id=product.id,
        name=product.name,
        image_url=storage.presign(product.image_key),
        created_at=product.created_at,
    )


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


@router.get("", response_model=ProductPage)
async def list_products(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    _: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
    storage: ImageStorage = Depends(get_storage),
) -> ProductPage:
    statement = (
        select(Product)
        .order_by(Product.created_at.desc(), Product.id.desc())
        .limit(limit + 1)
        .offset(offset)
    )
    products = list((await session.scalars(statement)).all())
    has_more = len(products) > limit
    return ProductPage(
        items=[to_out(product, storage) for product in products[:limit]],
        next_offset=offset + limit if has_more else None,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProductOut)
async def create_product(
    request: Request,
    principal: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    storage: ImageStorage = Depends(get_storage),
) -> ProductOut:
    settings = request.app.state.settings

    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Expected multipart/form-data",
        )
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > settings.max_image_bytes + MULTIPART_OVERHEAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Image is too large")

    async with request.form(max_files=1, max_fields=1) as form:
        if sorted(key for key, _ in form.multi_items()) != ["image", "name"]:
            raise _unprocessable("Expected exactly the fields name and image")
        raw_name = form["name"]
        image = form["image"]
        if not isinstance(raw_name, str) or not isinstance(image, UploadFile):
            raise _unprocessable("Expected a text field name and a file field image")

        try:
            name = normalize_name(raw_name, settings.max_name_length)
        except ValueError as exc:
            raise _unprocessable(str(exc)) from None

        try:
            info = await run_in_threadpool(
                inspect_image, image.file, settings.max_image_bytes, settings.max_image_pixels
            )
        except ImageTooLargeError:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Image is too large"
            ) from None
        except InvalidImageError:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Image must be a valid JPEG, PNG, or WebP file",
            ) from None

        key = f"products/{uuid.uuid4().hex}.{info.extension}"
        await run_in_threadpool(storage.put, key, image.file, info.size, info.content_type)

    product = Product(name=name, image_key=key, creator_telegram_id=principal.telegram_id)
    session.add(product)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        try:
            await run_in_threadpool(storage.delete, key)
        except Exception:
            logger.exception("failed to delete orphaned object %s", key)
        raise

    logger.info("product %s created by %s", product.id, principal.telegram_id)
    return to_out(product, storage)
