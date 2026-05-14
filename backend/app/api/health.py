from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.core.auth import get_current_user
from app.models import User

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    s = get_settings()
    return {
        "status": "ok",
        "integration_mode": s.INTEGRATION_MODE,
        "draft_model": s.LLM_DRAFT_MODEL,
        "classify_model": s.LLM_CLASSIFY_MODEL,
    }


@router.get("/api/me")
def me(user: Annotated[User, Depends(get_current_user)]) -> dict:
    """현재 사용자 정보. X-Forwarded-User 헤더에서 식별, dev fallback 적용 (config.DEV_DEFAULT_USER)."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
    }
