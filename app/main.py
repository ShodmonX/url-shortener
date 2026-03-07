import logging
from functools import lru_cache
from html import escape
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.cache.redis import LocalTTLCache, create_redis_client
from app.core.config import settings
from app.db.session import close_db_engine
from app.messaging.rabbitmq import RabbitMQPublisher

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
DOCS_TEMPLATE_PATH = TEMPLATES_DIR / "docs.html"


@lru_cache
def load_docs_template() -> str:
    return DOCS_TEMPLATE_PATH.read_text(encoding="utf-8")


def render_docs_page() -> str:
    content = load_docs_template()
    replacements = {
        "__PROJECT_NAME__": escape(settings.project_name),
        "__PUBLIC_BASE_URL__": escape(settings.public_base_url.rstrip("/")),
        "__API_PREFIX__": escape(settings.api_v1_prefix.rstrip("/")),
    }
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    return content


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = create_redis_client()
    local_cache = LocalTTLCache(settings.local_cache_max_entries)
    app.state.redis = redis
    app.state.redirect_local_cache = local_cache

    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    app.state.publisher = publisher
    try:
        await publisher.connect()
    except Exception:
        logger.exception("RabbitMQ unavailable during startup, continuing in degraded mode")

    try:
        yield
    finally:
        await app.state.publisher.close()
        await redis.aclose()
        await close_db_engine()


openapi_url = "/openapi.json" if settings.environment != "production" else None
docs_url = "/docs" if settings.environment != "production" else None

app = FastAPI(
    title=settings.project_name,
    debug=settings.debug,
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    openapi_url=openapi_url,
    docs_url=docs_url,
    redoc_url="/redoc" if settings.debug and settings.environment != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allowed_methods,
    allow_headers=settings.cors_allowed_headers,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
async def api_documentation() -> HTMLResponse:
    return HTMLResponse(content=render_docs_page())


app.include_router(api_router)
