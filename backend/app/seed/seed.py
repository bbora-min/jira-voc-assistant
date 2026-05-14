"""DB 초기화 + 기본 카테고리·운영자·샘플 데이터 시드 스크립트.

사용법:
    python -m app.seed.seed                # 기본 카테고리/유저만 생성
    python -m app.seed.seed --reset        # 모든 테이블 truncate 후 재생성
    python -m app.seed.seed --with-samples # 샘플 webhook 5건 주입
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy import delete

from app.core.logging import configure_logging
from app.db import session_scope
from app.deps import APP_ROOT
from app.models import (
    Category,
    Classification,
    Draft,
    KpiEvent,
    OperatorAction,
    PromptKind,
    PromptTemplate,
    Reference,
    Ticket,
    Upload,
    User,
    UserRole,
    WebhookInbox,
)
from app.services.classifier import DEFAULT_SYSTEM as CLASSIFY_SYSTEM
from app.services.drafter import DEFAULT_SYSTEM as DRAFT_SYSTEM
from app.services.pipeline import enqueue_webhook, process_webhook

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIES = [
    ("SYSTEM_ISSUE", "시스템 이슈", "System Issue", 1),
    ("FEATURE_INQUIRY", "기능 문의", "Feature Inquiry", 2),
    ("FEATURE_REQUEST", "기능 개발 요청", "Feature Development Request", 3),
]

DEFAULT_USERS = [
    ("admin@example.com", "운영자 (관리자)", UserRole.ADMIN),
    ("operator@example.com", "운영자 (담당자)", UserRole.OPERATOR),
]

WEBHOOKS_DIR = APP_ROOT / "seed" / "webhooks"


def _reset(s) -> None:
    for model in (
        KpiEvent, OperatorAction, Draft, Classification, Reference,
        WebhookInbox, Upload, Ticket, PromptTemplate, Category, User,
    ):
        s.execute(delete(model))


def _seed_static(s) -> None:
    if s.query(Category).count() == 0:
        for code, ko, en, order in DEFAULT_CATEGORIES:
            s.add(Category(code=code, label_ko=ko, label_en=en, sort_order=order))
        logger.info("seeded %d categories", len(DEFAULT_CATEGORIES))
    if s.query(User).count() == 0:
        for email, name, role in DEFAULT_USERS:
            s.add(User(email=email, name=name, role=role))
        logger.info("seeded %d users", len(DEFAULT_USERS))
    if s.query(PromptTemplate).count() == 0:
        s.add(PromptTemplate(
            kind=PromptKind.CLASSIFY, version=1, content=CLASSIFY_SYSTEM,
            is_active=True, note="Phase 4 default",
        ))
        s.add(PromptTemplate(
            kind=PromptKind.DRAFT, version=1, content=DRAFT_SYSTEM,
            is_active=True, note="Phase 4 default",
        ))
        logger.info("seeded 2 prompt templates (CLASSIFY, DRAFT)")


async def _seed_samples() -> int:
    files = sorted(WEBHOOKS_DIR.glob("*.json"))
    if not files:
        logger.warning("no sample webhooks found in %s", WEBHOOKS_DIR)
        return 0
    count = 0
    for p in files:
        payload = json.loads(p.read_text(encoding="utf-8"))
        meta = await enqueue_webhook(payload)
        if not meta["duplicate"]:
            await process_webhook(meta["inbox_id"])
            count += 1
    return count


async def main_async(reset: bool, with_samples: bool) -> None:
    configure_logging("INFO")
    with session_scope() as s:
        if reset:
            _reset(s)
            logger.info("reset all tables")
        _seed_static(s)
    if with_samples:
        n = await _seed_samples()
        logger.info("injected %d sample webhooks", n)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI VOC seed script")
    parser.add_argument("--reset", action="store_true", help="모든 테이블 truncate")
    parser.add_argument("--with-samples", action="store_true", help="샘플 webhook 5건 주입")
    args = parser.parse_args()
    asyncio.run(main_async(args.reset, args.with_samples))


if __name__ == "__main__":
    main()
