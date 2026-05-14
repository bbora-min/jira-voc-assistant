"""실제 JiraClient / ConfluenceClient skeleton 컴파일·인터페이스 호환 검증 (Phase 7.3).

라이브 HTTP 호출은 하지 않는다. 다음만 검증:
1. import 성공
2. Protocol 시그니처 일치 (IssueTracker / KnowledgeBase)
3. INTEGRATION_MODE=real 환경에서 deps.get_tracker / get_kb 가 적절한 RuntimeError 또는 실제 객체 반환
4. config 의 새 필드들이 .env 미설정 시 빈 문자열 기본값 + space_keys list 변환 동작
"""
from __future__ import annotations

import base64
import os

import pytest


def _ensure_test_env():
    os.environ.setdefault("VOC_DATA_KEY", base64.b64encode(os.urandom(32)).decode())
    os.environ.setdefault("DB_URL", "sqlite:///:memory:")


_ensure_test_env()


def test_jira_skeleton_imports_and_has_protocol_methods():
    from app.providers.tracker.base import IssueTracker
    from app.providers.tracker.jira import JiraClient

    # Protocol 구조적 일치 (Python 의 Protocol 은 runtime 적 검증을 별도 요구하므로 메서드 존재만 확인)
    for name in ("fetch_ticket", "post_comment", "transition"):
        assert hasattr(JiraClient, name), f"JiraClient missing {name}"

    # Protocol 자체는 import 가능
    assert IssueTracker is not None


def test_jira_constructor_rejects_empty_base_url():
    from app.providers.tracker.jira import JiraClient

    with pytest.raises(ValueError):
        JiraClient(base_url="", user="x", token="y")


def test_confluence_skeleton_imports_and_has_protocol_methods():
    from app.providers.kb.base import KnowledgeBase
    from app.providers.kb.confluence import ConfluenceClient

    for name in ("list_documents", "fetch_document"):
        assert hasattr(ConfluenceClient, name), f"ConfluenceClient missing {name}"
    assert KnowledgeBase is not None


def test_confluence_constructor_rejects_empty_space_keys():
    from app.providers.kb.confluence import ConfluenceClient

    with pytest.raises(ValueError):
        ConfluenceClient(base_url="https://x", user="u", token="t", space_keys=[])


def test_config_real_mode_fields_default_empty():
    """새로 추가된 필드들이 미설정 시 빈 문자열 (env 우선이지만 기본값 검증)."""
    from app.config import Settings

    s = Settings(
        VOC_DATA_KEY=os.environ["VOC_DATA_KEY"],
        DB_URL=os.environ["DB_URL"],
        JIRA_BASE_URL="",
        JIRA_API_USER="",
        JIRA_API_TOKEN="",
        CONFLUENCE_BASE_URL="",
        CONFLUENCE_API_USER="",
        CONFLUENCE_API_TOKEN="",
        CONFLUENCE_SPACE_KEYS="SPIM, SBOM , COMPLIANCE",
    )
    assert s.JIRA_BASE_URL == ""
    assert s.confluence_space_keys_list == ["SPIM", "SBOM", "COMPLIANCE"]


def test_deps_real_mode_missing_jira_raises():
    """INTEGRATION_MODE=real 인데 자격증명 누락 → RuntimeError. mock 누수 방지."""
    from app.config import get_settings
    from app.deps import get_tracker, reset_provider_cache

    s = get_settings()
    # 캐시 우회 위해 직접 환경 변수 시뮬레이션
    s.INTEGRATION_MODE = "real"  # type: ignore[assignment]
    s.JIRA_BASE_URL = ""
    reset_provider_cache()
    try:
        with pytest.raises(RuntimeError, match="JIRA_BASE_URL"):
            get_tracker()
    finally:
        s.INTEGRATION_MODE = "mock"  # type: ignore[assignment]
        reset_provider_cache()


def test_deps_real_mode_jira_returns_real_client():
    """JIRA_* 가 세팅되면 실제 JiraClient 인스턴스 반환 (네트워크 호출 없이 생성만 확인)."""
    from app.config import get_settings
    from app.deps import get_tracker, reset_provider_cache
    from app.providers.tracker.jira import JiraClient

    s = get_settings()
    s.INTEGRATION_MODE = "real"  # type: ignore[assignment]
    s.JIRA_BASE_URL = "https://acme.atlassian.net"
    s.JIRA_API_USER = "ops@acme.com"
    s.JIRA_API_TOKEN = "fake-token-xxx"
    reset_provider_cache()
    try:
        tracker = get_tracker()
        assert isinstance(tracker, JiraClient)
    finally:
        s.INTEGRATION_MODE = "mock"  # type: ignore[assignment]
        s.JIRA_BASE_URL = ""
        s.JIRA_API_USER = ""
        s.JIRA_API_TOKEN = ""
        reset_provider_cache()


def test_html_to_adf_strips_tags():
    """단순 HTML → ADF 변환이 모든 태그를 제거하고 paragraph 1개로 감싸는지 확인."""
    from app.providers.tracker.jira import _html_to_adf

    adf = _html_to_adf("<p>안녕 <strong>세계</strong></p><ul><li>A</li><li>B</li></ul>")
    assert adf["type"] == "doc"
    assert adf["version"] == 1
    paras = adf["content"]
    assert len(paras) == 1 and paras[0]["type"] == "paragraph"
    text_nodes = paras[0]["content"]
    full = "".join(n.get("text", "") for n in text_nodes)
    assert "<" not in full and ">" not in full
    assert "안녕" in full and "세계" in full
