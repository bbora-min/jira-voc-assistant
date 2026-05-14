from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import actions as actions_router
from app.api import admin as admin_router
from app.api import categories as categories_router
from app.api import dev as dev_router
from app.api import health as health_router
from app.api import kpi as kpi_router
from app.api import retrieval as retrieval_router
from app.api import tickets as tickets_router
from app.api import uploads as uploads_router
from app.api import webhook as webhook_router
from app.api import ws as ws_router
from app.config import get_settings
from app.core.logging import configure_logging
from app.core.ws_manager import init_ws_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    manager = init_ws_manager(settings.REDIS_URL)
    await manager.start()

    # NFR-06: APScheduler 시간당 Confluence 재색인 잡
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.services.reindex import reindex_all
    from app.services.webhook_retry import retry_failed_inboxes

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        reindex_all,
        "interval",
        minutes=settings.REINDEX_INTERVAL_MINUTES,
        id="reindex_all",
        coalesce=True,
        max_instances=1,
    )
    # Phase 7.4: 실패한 webhook 행을 1분마다 재시도 (FR-04 안정성)
    scheduler.add_job(
        retry_failed_inboxes,
        "interval",
        minutes=1,
        id="webhook_retry",
        coalesce=True,
        max_instances=1,
    )
    # Phase 7.7: KPI 응답 prewarm — 사용자 페이지 진입 시 cold start 방지
    from app.services.kpi_cache import prewarm_kpi_cache
    scheduler.add_job(
        prewarm_kpi_cache,
        "interval",
        minutes=5,
        id="kpi_prewarm",
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    app.state.scheduler = scheduler

    logger.info(
        "AI VOC backend started — mode=%s, reindex_every=%dm, webhook_retry_every=1m",
        settings.INTEGRATION_MODE, settings.REINDEX_INTERVAL_MINUTES,
    )
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await manager.stop()
        logger.info("AI VOC backend stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AI VOC Auto-Response Backend",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router.router)
    app.include_router(ws_router.router)
    app.include_router(webhook_router.router)
    app.include_router(tickets_router.router)
    app.include_router(actions_router.router)
    app.include_router(categories_router.router)
    app.include_router(uploads_router.router)
    app.include_router(admin_router.router)
    app.include_router(retrieval_router.router)
    app.include_router(kpi_router.router)
    if settings.INTEGRATION_MODE == "mock":
        app.include_router(dev_router.router)
    return app


app = create_app()
