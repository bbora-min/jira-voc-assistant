"""Dependency injection seam.

INTEGRATION_MODE 환경변수에 따라 mock/real provider를 선택한다.
LLM/RAG는 Phase 3-4에서 실 구현이 들어오기 전까지 None을 반환할 수 있다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config import Settings, get_settings
from app.providers.embed.base import Embedder
from app.providers.kb.base import KnowledgeBase
from app.providers.kb.mock import MockKnowledgeBase
from app.providers.rag.base import RAGProvider
from app.providers.storage.base import Storage
from app.providers.storage.local import LocalStorage
from app.providers.tracker.base import IssueTracker
from app.providers.tracker.mock import MockJira

PROJECT_ROOT = Path(__file__).resolve().parents[1]   # backend/
APP_ROOT = Path(__file__).resolve().parent           # backend/app/
CORPUS_DIR = APP_ROOT / "seed" / "corpus"


def get_app_settings() -> Settings:
    return get_settings()


@lru_cache(maxsize=1)
def get_tracker() -> IssueTracker:
    s = get_settings()
    if s.INTEGRATION_MODE == "mock":
        return MockJira()
    if not (s.JIRA_BASE_URL and s.JIRA_API_USER and s.JIRA_API_TOKEN):
        raise RuntimeError(
            "INTEGRATION_MODE=real 인데 JIRA_BASE_URL / JIRA_API_USER / JIRA_API_TOKEN 미설정"
        )
    from app.providers.tracker.jira import JiraClient
    return JiraClient(
        base_url=s.JIRA_BASE_URL,
        user=s.JIRA_API_USER,
        token=s.JIRA_API_TOKEN,
    )


@lru_cache(maxsize=1)
def get_kb() -> KnowledgeBase:
    s = get_settings()
    if s.INTEGRATION_MODE == "mock":
        return MockKnowledgeBase(corpus_dir=CORPUS_DIR)
    if not (s.CONFLUENCE_BASE_URL and s.CONFLUENCE_API_USER and s.CONFLUENCE_API_TOKEN):
        raise RuntimeError(
            "INTEGRATION_MODE=real 인데 CONFLUENCE_BASE_URL / CONFLUENCE_API_USER / CONFLUENCE_API_TOKEN 미설정"
        )
    from app.providers.kb.confluence import ConfluenceClient
    return ConfluenceClient(
        base_url=s.CONFLUENCE_BASE_URL,
        user=s.CONFLUENCE_API_USER,
        token=s.CONFLUENCE_API_TOKEN,
        space_keys=s.confluence_space_keys_list,
    )


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    s = get_settings()
    base = Path(s.UPLOAD_DIR).resolve()
    return LocalStorage(base_dir=base)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """VOYAGE_API_KEY가 있으면 Voyage, 없으면 ChromaDB 기본(ONNX MiniLM)."""
    s = get_settings()
    if s.VOYAGE_API_KEY:
        from app.providers.embed.voyage import VoyageEmbedder
        return VoyageEmbedder(api_key=s.VOYAGE_API_KEY)
    from app.providers.embed.local import LocalEmbedder
    return LocalEmbedder()


@lru_cache(maxsize=1)
def get_rag() -> RAGProvider:
    from app.providers.rag.chroma import ChromaRAGProvider

    s = get_settings()
    return ChromaRAGProvider(
        persist_dir=Path(s.RAG_PERSIST_DIR).resolve(),
        collection_name=s.RAG_COLLECTION,
        embedder=get_embedder(),
    )


@lru_cache(maxsize=1)
def get_llm():
    """ANTHROPIC_API_KEY 존재 시 실제 Claude API, 없으면 결정적 MockLLM."""
    s = get_settings()
    if s.ANTHROPIC_API_KEY:
        from app.providers.llm.anthropic import AnthropicLLMProvider
        return AnthropicLLMProvider(api_key=s.ANTHROPIC_API_KEY)
    from app.providers.llm.mock import MockLLMProvider
    return MockLLMProvider()


def reset_provider_cache() -> None:
    """테스트 / 시드 스크립트에서 INTEGRATION_MODE 변경 시 호출."""
    get_tracker.cache_clear()
    get_kb.cache_clear()
    get_storage.cache_clear()
    get_embedder.cache_clear()
    get_rag.cache_clear()
    get_llm.cache_clear()
