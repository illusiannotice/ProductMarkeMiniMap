import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth import Principal, get_principal
from app.config import Settings, get_settings
from app.db import build_engine, build_sessionmaker
from app.observability import RequestContextMiddleware, configure_logging
from app.products import router as products_router
from app.schemas import MeOut
from app.storage import ImageStorage, MinioStorage

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    engine: AsyncEngine | None = None,
    storage: ImageStorage | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = engine or build_engine(settings)
    storage = storage or MinioStorage(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            await run_in_threadpool(storage.ensure_bucket)
        except Exception:
            logger.exception("object storage bucket is not available yet")
        yield
        await engine.dispose()

    expose_docs = settings.environment == "development"
    app = FastAPI(
        title="Catalog API",
        lifespan=lifespan,
        docs_url="/api/docs" if expose_docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if expose_docs else None,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = build_sessionmaker(engine)
    app.state.storage = storage

    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(error["loc"]), "msg": error["msg"]} for error in exc.errors()]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": "Invalid request", "errors": errors},
        )

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            storage_ready = await run_in_threadpool(storage.is_ready)
        except Exception:
            logger.warning("readiness check failed", exc_info=True)
            storage_ready = False
        if not storage_ready:
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"status": "unavailable"})
        return JSONResponse(content={"status": "ready"})

    @app.get("/api/v1/auth/me", response_model=MeOut, tags=["auth"])
    async def me(principal: Principal = Depends(get_principal)) -> MeOut:
        identity = principal.identity
        return MeOut(
            telegram_id=identity.telegram_id,
            username=identity.username,
            first_name=identity.first_name,
            last_name=identity.last_name,
            role=principal.role,
        )

    app.include_router(products_router)
    return app
