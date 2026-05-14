"""인증/인가 dependency.

PoC: `X-Forwarded-User` 헤더(reverse proxy 가 OIDC 인증 후 세팅)를 신뢰하여 사용자 식별.
헤더가 없으면 dev fallback (settings.DEV_DEFAULT_USER) 으로 자동 로그인. Production 에서는
reverse proxy 가 항상 헤더를 세팅하도록 보장하면 fallback 은 발동되지 않는다.

향후 OIDC 토큰 검증으로 교체할 때 이 모듈의 `get_current_user` 만 바꾸면 다른 모든 라우트는
영향 없음 — Provider seam.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User, UserRole

logger = logging.getLogger(__name__)


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    x_forwarded_user: Annotated[str | None, Header(alias="X-Forwarded-User")] = None,
) -> User:
    """현재 요청의 사용자를 반환. X-Forwarded-User 헤더 우선, 없으면 dev fallback."""
    settings = get_settings()
    email = (x_forwarded_user or "").strip().lower() or settings.DEV_DEFAULT_USER
    if not email:
        raise HTTPException(status_code=401, detail="missing X-Forwarded-User header")
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        logger.warning("unknown user header=%r", email)
        raise HTTPException(status_code=401, detail=f"unknown user: {email}")
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    """ADMIN 역할 가드. OPERATOR 가 호출하면 403."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="admin role required")
    return user
