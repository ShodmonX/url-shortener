from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends, Request

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthcheck(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    await request.app.state.redis.ping()
    return {"status": "ok"}
