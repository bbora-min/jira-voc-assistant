"""AES-256-GCM helpers + SQLAlchemy TypeDecorator for transparent column encryption.

NFR-04: VOC 내 People 정보 AES-256 암호화 저장.

Wire format: nonce(12) || ciphertext || tag(16). Stored as VARBINARY/BLOB.
Empty / None plaintext is preserved (None in == None out, "" in == "" out).
"""
from __future__ import annotations

import base64
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import LargeBinary, TypeDecorator

from app.config import get_settings

NONCE_BYTES = 12


class CryptoError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _aes() -> AESGCM:
    raw = get_settings().VOC_DATA_KEY
    if not raw:
        raise CryptoError(
            "VOC_DATA_KEY 미설정. .env에 base64로 인코딩된 32바이트 키를 채우세요. "
            'ex) python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"'
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as e:  # noqa: BLE001
        raise CryptoError("VOC_DATA_KEY 가 유효한 base64 문자열이 아닙니다") from e
    if len(key) != 32:
        raise CryptoError(f"VOC_DATA_KEY 길이는 32바이트여야 합니다 (현재 {len(key)}바이트)")
    return AESGCM(key)


def encrypt_str(plaintext: str | None) -> bytes | None:
    if plaintext is None:
        return None
    nonce = os.urandom(NONCE_BYTES)
    ct = _aes().encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return nonce + ct


def decrypt_str(blob: bytes | None) -> str | None:
    if blob is None:
        return None
    if len(blob) < NONCE_BYTES + 16:
        raise CryptoError("암호문 길이 부족")
    nonce, ct = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    return _aes().decrypt(nonce, ct, associated_data=None).decode("utf-8")


class EncryptedText(TypeDecorator):
    """SQLAlchemy column type that transparently encrypts/decrypts UTF-8 text.

    Use as a column type:
        title_enc: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError(f"EncryptedText expects str, got {type(value).__name__}")
        return encrypt_str(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        return decrypt_str(bytes(value))
