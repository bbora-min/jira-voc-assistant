"""Tiptap 이미지 업로드 (FR-21).

multipart 폼으로 받아 LocalStorage에 저장하고, Tiptap이 inline으로 사용할 URL을 반환.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import get_settings
from app.db import session_scope
from app.deps import get_storage
from app.models import Upload
from app.providers.storage.local import ALLOWED_MIMES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("")
async def upload(file: UploadFile = File(...)) -> dict:
    settings = get_settings()
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="empty file")
    if len(content) > settings.UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file too large (max {settings.UPLOAD_MAX_BYTES} bytes)",
        )
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MIMES:
        raise HTTPException(status_code=415, detail=f"unsupported mime: {mime}")

    storage = get_storage()
    obj = await storage.put(content=content, filename=file.filename or "upload", mime=mime)

    with session_scope() as s:
        row = Upload(
            filename=obj.filename, mime=obj.mime, size=obj.size,
            sha256=obj.sha256, path=obj.path,
        )
        s.add(row)
        s.flush()
        upload_id = row.id

    logger.info("uploaded %s (%d bytes, sha=%s)", obj.filename, obj.size, obj.sha256[:8])
    return {
        "id": upload_id,
        "url": obj.url,
        "filename": obj.filename,
        "mime": obj.mime,
        "size": obj.size,
    }


@router.get("/{name}")
async def serve(name: str) -> FileResponse:
    """sha256.ext 형태 파일명만 받아서 디스크에서 서빙. ../ 등은 거부."""
    if "/" in name or ".." in name:
        raise HTTPException(status_code=400, detail="bad name")
    settings = get_settings()
    base = Path(settings.UPLOAD_DIR).resolve()
    # 모든 yyyy/mm 하위 경로 탐색 (sha256은 충돌 거의 없음)
    for p in base.rglob(name):
        if p.is_file() and base in p.resolve().parents:
            return FileResponse(p)
    raise HTTPException(status_code=404, detail="not found")
