"""로컬 디스크 저장소. ./var/uploads/{yyyy}/{mm}/{sha256}.{ext} 구조."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
from datetime import datetime
from pathlib import Path

from app.providers.storage.base import Storage, StoredObject

logger = logging.getLogger(__name__)

ALLOWED_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


class LocalStorage(Storage):
    def __init__(self, base_dir: Path, public_url_prefix: str = "/api/uploads/"):
        self.base_dir = base_dir
        self.url_prefix = public_url_prefix
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def put(self, *, content: bytes, filename: str, mime: str) -> StoredObject:
        if mime not in ALLOWED_MIMES:
            raise ValueError(f"허용되지 않은 mime: {mime}")
        sha = hashlib.sha256(content).hexdigest()
        ext = mimetypes.guess_extension(mime) or ""
        now = datetime.utcnow()
        rel = Path(f"{now:%Y}/{now:%m}") / f"{sha}{ext}"
        target = self.base_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, content)
        return StoredObject(
            sha256=sha,
            path=str(target),
            url=f"{self.url_prefix}{sha}{ext}",
            size=len(content),
            mime=mime,
            filename=filename,
        )

    async def open(self, path: str) -> bytes:
        return await asyncio.to_thread(Path(path).read_bytes)
