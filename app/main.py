from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(
    title="URL Shortener API",
    debug=settings.debug,
    openapi_url="/openapi.json" if settings.debug else None,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)