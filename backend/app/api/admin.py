"""관리 API.

Phase 3: RAG 재색인 추가.
Phase 6: 카테고리 CRUD + 프롬프트 템플릿 버전 관리 + LLM 피드백 export 추가.
"""
from __future__ import annotations

import logging
from typing import Annotated, Generator

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.db import get_db
from app.deps import get_rag
from app.models import (
    ActionType,
    Category,
    Draft,
    KpiEvent,
    KpiEventType,
    OperatorAction,
    PromptKind,
    PromptTemplate,
    Ticket,
)
from app.services.reindex import reindex_all
from sqlalchemy import desc as sa_desc, func as sa_func, update as sa_update
from fastapi.responses import StreamingResponse
import json

logger = logging.getLogger(__name__)
# 모든 admin 라우트는 ADMIN 역할 필요 (Phase 7.1)
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ─────────────────────────── RAG ────────────────────────────


@router.get("/rag-status")
def rag_status() -> dict:
    rag = get_rag()
    if hasattr(rag, "collection_meta"):
        return rag.collection_meta()  # type: ignore[attr-defined]
    return {"count": 0}


@router.post("/reindex")
async def trigger_reindex() -> dict:
    logger.info("manual reindex requested")
    result = await reindex_all()
    return {"ok": True, **result}


# ─────────────────────────── 카테고리 CRUD (NFR-07) ────────────────────────────


class CategoryCreate(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[A-Z][A-Z0-9_]+$")
    label_ko: str = Field(min_length=1, max_length=120)
    label_en: str | None = Field(default=None, max_length=120)
    sort_order: int = Field(default=0, ge=0, le=10_000)


class CategoryUpdate(BaseModel):
    label_ko: str | None = Field(default=None, max_length=120)
    label_en: str | None = Field(default=None, max_length=120)
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    is_active: bool | None = None


class CategoryOut(BaseModel):
    id: int
    code: str
    label_ko: str
    label_en: str | None
    sort_order: int
    is_active: bool


def _to_out(c: Category) -> CategoryOut:
    return CategoryOut(id=c.id, code=c.code, label_ko=c.label_ko, label_en=c.label_en,
                       sort_order=c.sort_order, is_active=c.is_active)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Annotated[Session, Depends(get_db)]) -> list[CategoryOut]:
    """Admin 화면용 — is_active 와 무관하게 전체 목록."""
    rows = db.execute(select(Category).order_by(Category.sort_order, Category.id)).scalars().all()
    return [_to_out(c) for c in rows]


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryCreate, db: Annotated[Session, Depends(get_db)]) -> CategoryOut:
    existing = db.execute(select(Category).where(Category.code == body.code)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"category code '{body.code}' already exists")
    c = Category(code=body.code, label_ko=body.label_ko, label_en=body.label_en,
                 sort_order=body.sort_order, is_active=True)
    db.add(c)
    db.commit()
    db.refresh(c)
    logger.info("category created: id=%s code=%s", c.id, c.code)
    return _to_out(c)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryUpdate,
                    db: Annotated[Session, Depends(get_db)]) -> CategoryOut:
    c = db.get(Category, category_id)
    if not c:
        raise HTTPException(status_code=404, detail="category not found")
    if body.label_ko is not None: c.label_ko = body.label_ko
    if body.label_en is not None: c.label_en = body.label_en
    if body.sort_order is not None: c.sort_order = body.sort_order
    if body.is_active is not None: c.is_active = body.is_active
    db.commit()
    db.refresh(c)
    logger.info("category updated: id=%s code=%s active=%s", c.id, c.code, c.is_active)
    return _to_out(c)


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, db: Annotated[Session, Depends(get_db)]) -> None:
    """Soft delete — is_active=False 로 비활성. 참조 무결성 보호."""
    c = db.get(Category, category_id)
    if not c:
        raise HTTPException(status_code=404, detail="category not found")
    c.is_active = False
    db.commit()
    logger.info("category deactivated: id=%s code=%s", c.id, c.code)


# ─── 프롬프트 템플릿 버전 관리 (CLASSIFY / DRAFT 시스템 프롬프트) ───


class PromptOut(BaseModel):
    id: int
    kind: PromptKind
    version: int
    content: str
    is_active: bool
    note: str | None
    created_at: str | None


class PromptCreate(BaseModel):
    kind: PromptKind
    content: str = Field(min_length=10, max_length=20_000)
    note: str | None = Field(default=None, max_length=500)
    activate: bool = Field(default=False, description="True면 생성 즉시 활성화")


class PromptPreviewReq(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    kind: PromptKind


def _to_prompt_out(p: PromptTemplate) -> PromptOut:
    return PromptOut(
        id=p.id, kind=p.kind, version=p.version, content=p.content,
        is_active=p.is_active, note=p.note,
        created_at=p.created_at.isoformat() if p.created_at else None,
    )


@router.get("/prompts", response_model=list[PromptOut])
def list_prompts(
    db: Annotated[Session, Depends(get_db)],
    kind: PromptKind | None = None,
) -> list[PromptOut]:
    stmt = select(PromptTemplate).order_by(PromptTemplate.kind, PromptTemplate.version.desc())
    if kind:
        stmt = stmt.where(PromptTemplate.kind == kind)
    rows = db.execute(stmt).scalars().all()
    return [_to_prompt_out(p) for p in rows]


@router.post("/prompts", response_model=PromptOut, status_code=201)
def create_prompt(body: PromptCreate, db: Annotated[Session, Depends(get_db)]) -> PromptOut:
    # 같은 kind 최대 버전 + 1
    max_v = db.execute(
        select(sa_func.coalesce(sa_func.max(PromptTemplate.version), 0))
        .where(PromptTemplate.kind == body.kind)
    ).scalar() or 0
    new = PromptTemplate(
        kind=body.kind, version=int(max_v) + 1,
        content=body.content, note=body.note,
        is_active=False,
    )
    db.add(new)
    db.flush()
    if body.activate:
        # 같은 kind 의 다른 버전 모두 비활성화 후 이 버전만 활성화
        db.execute(
            sa_update(PromptTemplate)
            .where(PromptTemplate.kind == body.kind, PromptTemplate.id != new.id)
            .values(is_active=False)
        )
        new.is_active = True
    db.commit()
    db.refresh(new)
    logger.info("prompt created: kind=%s version=%s activated=%s", new.kind, new.version, body.activate)
    return _to_prompt_out(new)


@router.post("/prompts/{prompt_id}/activate", response_model=PromptOut)
def activate_prompt(prompt_id: int, db: Annotated[Session, Depends(get_db)]) -> PromptOut:
    p = db.get(PromptTemplate, prompt_id)
    if not p:
        raise HTTPException(status_code=404, detail="prompt not found")
    db.execute(
        sa_update(PromptTemplate)
        .where(PromptTemplate.kind == p.kind, PromptTemplate.id != p.id)
        .values(is_active=False)
    )
    p.is_active = True
    db.commit()
    db.refresh(p)
    logger.info("prompt activated: id=%s kind=%s version=%s", p.id, p.kind, p.version)
    return _to_prompt_out(p)


@router.post("/prompts/preview")
def preview_prompt(body: PromptPreviewReq) -> dict:
    """Jinja2 렌더 미리보기. 샘플 컨텍스트(고정)로 렌더링하여 system 텍스트 결과를 반환.

    실제 호출에서 system 은 거의 정적 텍스트이지만, 만약 Jinja 변수가 포함되면
    실제 추론 시 어떻게 보일지 확인할 수 있다.
    """
    from jinja2 import Template, TemplateError
    sample_ctx: dict = {
        "ticket": {
            "title": "[샘플] SBOM Export가 실패합니다",
            "body": "프로젝트 X에서 SBOM 추출 시 'license expression invalid' 에러가 발생합니다.",
        },
        "chunks": [
            {"source_title": "SBOM Export 실패 시 점검 가이드",
             "text": "1) scanner.yaml 의 spdx_mode 확인. 2) 라이선스 표현식 검증..."},
            {"source_title": "라이선스 표현식 형식",
             "text": "Apache-2.0 OR MIT 처럼 SPDX 식별자를 OR/AND/WITH 로 조합한 표현..."},
        ],
        "kind": body.kind.value,
    }
    try:
        rendered = Template(body.content).render(**sample_ctx)
        return {"ok": True, "rendered": rendered, "context_used": sample_ctx}
    except TemplateError as e:
        return {"ok": False, "error": str(e), "context_used": sample_ctx}


# ─── LLM 피드백 JSONL export (SFT / DPO 학습용) ───


@router.get("/llm-feedback-export")
def llm_feedback_export(
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    """미채택 케이스(REJECT 액션이 있고 마지막이 REJECT인 DONE 티켓)를 JSONL 로 export.

    각 행 = 한 학습 샘플:
      {
        "jira_key": str,
        "ticket_title": str,
        "ticket_body": str,
        "ai_draft_html": str,     # AI 가 처음 만든 본문
        "operator_html": str,     # 운영자가 최종 등록한 본문 (=Jira 코멘트)
        "reject_reason": str,     # 운영자가 적은 미채택 사유 (LLM negative feedback)
        "edit_distance": int,
        "created_at": ISO8601 str,
      }

    SFT: operator_html 을 정답으로 학습. DPO: (ai_draft, operator_html, reason) 으로 선호도 학습.
    """
    # REJECT 액션이 있는 ticket 들 (가장 최근 REJECT가 마지막인 케이스만)
    reject_action_subq = (
        select(
            OperatorAction.ticket_id,
            OperatorAction.payload_json,
            OperatorAction.created_at,
            sa_func.row_number().over(
                partition_by=OperatorAction.ticket_id,
                order_by=sa_desc(OperatorAction.id),
            ).label("rn"),
            OperatorAction.action,
        )
        .where(OperatorAction.action.in_([ActionType.REJECT, ActionType.APPROVE]))
        .subquery()
    )

    rows = db.execute(
        select(
            Ticket.jira_key, Ticket.title_enc, Ticket.body_enc,
            Draft.body_html, Draft.body_html_edited, Draft.edit_distance,
            reject_action_subq.c.payload_json, reject_action_subq.c.created_at,
        )
        .join(reject_action_subq, reject_action_subq.c.ticket_id == Ticket.id)
        .join(Draft, Draft.ticket_id == Ticket.id)
        .where(reject_action_subq.c.rn == 1, reject_action_subq.c.action == ActionType.REJECT)
        .order_by(Ticket.id.desc())
    ).all()

    def _generate() -> Generator[bytes, None, None]:
        n = 0
        for r in rows:
            payload = r[6] or {}
            sample = {
                "jira_key": r[0],
                "ticket_title": r[1] or "",
                "ticket_body": r[2] or "",
                "ai_draft_html": r[3] or "",
                "operator_html": r[4] or r[3] or "",
                "reject_reason": payload.get("reason", ""),
                "edit_distance": int(r[5] or 0),
                "created_at": r[7].isoformat() if r[7] else None,
            }
            yield (json.dumps(sample, ensure_ascii=False) + "\n").encode("utf-8")
            n += 1
        logger.info("llm-feedback-export streamed %d samples", n)

    return StreamingResponse(
        _generate(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="llm_negative_feedback.jsonl"'},
    )
