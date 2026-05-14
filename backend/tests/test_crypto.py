"""NFR-04 — AES-256-GCM 암호화 round-trip 및 무결성 검증.

테스트 범위:
1. 평문 → 암호문 → 평문 round-trip 일관성 (단순/유니코드/긴 문자열/빈 문자열)
2. nonce 무작위성 (같은 평문이라도 매번 다른 암호문)
3. None 통과
4. 변조된 암호문 거부 (인증 태그 검증)
5. SQLAlchemy TypeDecorator process_bind_param / process_result_value
6. 실제 DB 라이프사이클 (Ticket 모델 title_enc / body_enc 컬럼 round-trip)
"""
from __future__ import annotations

import os

import pytest


def _ensure_test_key():
    """테스트는 임시 32-byte base64 키를 환경변수에 주입한 뒤 모듈을 import."""
    import base64
    os.environ.setdefault("VOC_DATA_KEY", base64.b64encode(os.urandom(32)).decode())
    # DB 도 in-memory SQLite 로 강제 (실제 voc.db 건들지 않도록)
    os.environ.setdefault("DB_URL", "sqlite:///:memory:")


_ensure_test_key()


def test_round_trip_ascii():
    from app.core.crypto import encrypt_str, decrypt_str
    pt = "hello world"
    blob = encrypt_str(pt)
    assert blob is not None
    assert blob[:1] != b"h"  # 평문 prefix 그대로 노출되면 안됨
    assert decrypt_str(blob) == pt


def test_round_trip_unicode():
    from app.core.crypto import encrypt_str, decrypt_str
    pt = "안녕하세요 — VOC 시스템 입니다 ✓"
    blob = encrypt_str(pt)
    assert decrypt_str(blob) == pt


def test_round_trip_empty_string():
    from app.core.crypto import encrypt_str, decrypt_str
    pt = ""
    blob = encrypt_str(pt)
    assert blob is not None  # nonce + tag 는 항상 있음 (최소 28바이트)
    assert len(blob) >= 12 + 16
    assert decrypt_str(blob) == ""


def test_round_trip_long_text():
    from app.core.crypto import encrypt_str, decrypt_str
    pt = "가" * 5000 + " " + "a" * 5000
    blob = encrypt_str(pt)
    assert decrypt_str(blob) == pt


def test_none_pass_through():
    from app.core.crypto import encrypt_str, decrypt_str
    assert encrypt_str(None) is None
    assert decrypt_str(None) is None


def test_nonce_randomness():
    """같은 평문이라도 매번 다른 암호문이 나와야 한다 (nonce 재사용 방지)."""
    from app.core.crypto import encrypt_str
    pt = "deterministic input"
    blob1 = encrypt_str(pt)
    blob2 = encrypt_str(pt)
    assert blob1 != blob2


def test_tampered_ciphertext_rejected():
    """암호문 1바이트만 뒤집어도 GCM 인증 태그가 실패해야 한다."""
    from cryptography.exceptions import InvalidTag

    from app.core.crypto import decrypt_str, encrypt_str
    blob = encrypt_str("sensitive data")
    assert blob is not None
    # nonce 영역은 건들지 않고 ciphertext 중간 1바이트 뒤집기
    middle = len(blob) // 2
    tampered = bytearray(blob)
    tampered[middle] ^= 0xFF
    with pytest.raises(InvalidTag):
        decrypt_str(bytes(tampered))


def test_truncated_blob_rejected():
    from app.core.crypto import CryptoError, decrypt_str
    with pytest.raises(CryptoError):
        decrypt_str(b"\x00" * 10)  # nonce(12) + tag(16) 합계 28 미만


def test_type_decorator_bind_and_result():
    from app.core.crypto import EncryptedText
    td = EncryptedText()
    blob = td.process_bind_param("payload 한글", dialect=None)
    assert isinstance(blob, bytes)
    assert td.process_result_value(blob, dialect=None) == "payload 한글"


def test_type_decorator_rejects_non_string():
    from app.core.crypto import EncryptedText
    td = EncryptedText()
    with pytest.raises(TypeError):
        td.process_bind_param(123, dialect=None)  # type: ignore[arg-type]


def test_db_lifecycle_ticket_columns():
    """실제 SQLAlchemy 세션에서 Ticket 의 title_enc/body_enc 가 BLOB 으로 저장되고
    SELECT 시 평문으로 복원되는지 확인."""
    from datetime import datetime, timezone

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models import Ticket, TicketStatus
    from app.models.base import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    title = "기밀 제목 — SBOM Export 실패"
    body = "라이선스 스캐너 v3.4 에서 오류 — Apache-2.0 OR MIT 표현식 인식 실패"

    with Session(engine) as s:
        t = Ticket(
            jira_key="TEST-1",
            title_enc=title,
            body_enc=body,
            reporter_enc=None,
            assignee=None,
            status=TicketStatus.PENDING,
            received_at=datetime.now(timezone.utc),
        )
        s.add(t)
        s.commit()
        tid = t.id

    # raw bytes 직접 조회 — BLOB 이어야 하고 평문이 노출되면 안됨
    with engine.connect() as conn:
        raw = conn.exec_driver_sql(f"SELECT title_enc FROM tickets WHERE id={tid}").scalar()
        assert isinstance(raw, (bytes, bytearray, memoryview))
        raw_bytes = bytes(raw)
        assert title.encode("utf-8") not in raw_bytes  # 평문이 BLOB 에 그대로 노출되면 안됨

    # ORM 통한 SELECT 는 평문으로 복원
    with Session(engine) as s:
        loaded = s.execute(select(Ticket).where(Ticket.id == tid)).scalar_one()
        assert loaded.title_enc == title
        assert loaded.body_enc == body
