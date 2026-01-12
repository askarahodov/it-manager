import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.request_id import new_request_id, set_request_id
from app.db import engine
from app.db import async_session
from app.services.bootstrap import ensure_bootstrap_admin, ensure_default_project

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan-хук приложения.

    Используем вместо deprecated `@app.on_event("startup")`.
    """

    async with engine.begin():
        pass
    # Bootstrap admin (best-effort): создаём только если таблица users пуста
    async with async_session() as db:
        try:
            await ensure_bootstrap_admin(db, settings.bootstrap_admin_email, settings.bootstrap_admin_password)
            await ensure_default_project(db)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning("Bootstrap admin failed: %s", exc)
    yield

app = FastAPI(
    title="IT Manager API",
    version="0.1.0",
    description="API для управления хостами, секретами и автоматизацией",
    lifespan=lifespan,
)

# Логирование настраиваем как можно раньше (до обработки запросов).
setup_logging(json_logs=bool(settings.json_logs))

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

@app.middleware("http")
async def request_id_middleware(request, call_next):
    """Проставляет request-id для корреляции логов.

    - Если клиент передал `X-Request-Id`, используем его.
    - Иначе генерируем новый.
    - Возвращаем значение обратно в заголовке ответа `X-Request-Id`.
    """
    incoming = request.headers.get("x-request-id")
    rid = (incoming or "").strip() or new_request_id()
    set_request_id(rid)
    try:
        response = await call_next(request)
    finally:
        set_request_id(None)
    response.headers["X-Request-Id"] = rid
    return response

@app.get("/healthz")
async def healthz():
    """Простой healthcheck для Docker/балансировщика."""
    return {"status": "ok"}


@app.get("/api/healthz")
async def healthz_api():
    """Healthcheck через frontend proxy (`/api/*` -> backend)."""
    return {"status": "ok"}


@app.get("/api/v1/healthz")
async def healthz_api_v1():
    """Healthcheck для клиентов, которые ожидают `/api/v1/*`."""
    return {"status": "ok"}
