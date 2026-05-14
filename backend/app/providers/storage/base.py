from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class StoredObject:
    sha256: str
    path: str
    url: str
    size: int
    mime: str
    filename: str


class Storage(Protocol):
    async def put(self, *, content: bytes, filename: str, mime: str) -> StoredObject: ...
    async def open(self, path: str) -> bytes: ...
