from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.links import router as links_router
from app.api.routes.redirects import router as redirects_router
from app.api.routes.urls import router as urls_router
from app.api.routes.users import router as users_router
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router, prefix=settings.api_v1_prefix)
api_router.include_router(links_router, prefix=settings.api_v1_prefix)
api_router.include_router(users_router, prefix=settings.api_v1_prefix)
api_router.include_router(urls_router, prefix=settings.api_v1_prefix)
api_router.include_router(redirects_router)
