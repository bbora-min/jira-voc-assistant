from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    ANTHROPIC_API_KEY: str = ""
    VOYAGE_API_KEY: str = ""

    DB_URL: str = "mysql+pymysql://voc:voc@localhost:3306/voc"
    REDIS_URL: str = "redis://localhost:6379/0"
    CHROMA_URL: str = "http://localhost:8001"

    INTEGRATION_MODE: Literal["mock", "real"] = "mock"
    LOG_LEVEL: str = "INFO"

    VOC_DATA_KEY: str = ""

    CORS_ALLOW_ORIGINS: str = "http://localhost:5173"

    UPLOAD_DIR: str = "./var/uploads"
    UPLOAD_MAX_BYTES: int = 10 * 1024 * 1024

    LLM_DRAFT_MODEL: str = "claude-opus-4-7"
    LLM_CLASSIFY_MODEL: str = "claude-sonnet-4-6"
    LLM_TIMEOUT_SECONDS: float = 8.0

    RAG_COLLECTION: str = "voc_corpus"
    RAG_TOP_K: int = 5
    RAG_PERSIST_DIR: str = "./var/chroma"
    REINDEX_INTERVAL_MINUTES: int = 60   # NFR-06: Confluence 변경 후 1시간 이내 반영

    # 인증 (Phase 7) — X-Forwarded-User 헤더가 없을 때 사용할 기본 사용자 email.
    # Production 에서는 reverse proxy 가 항상 헤더를 세팅하도록 하고, 비워두는 것을 권장.
    DEV_DEFAULT_USER: str = "admin@example.com"

    # 실제 외부 시스템 통합 (Phase 7.3) — INTEGRATION_MODE=real 일 때만 사용
    JIRA_BASE_URL: str = ""
    JIRA_API_USER: str = ""
    JIRA_API_TOKEN: str = ""

    CONFLUENCE_BASE_URL: str = ""
    CONFLUENCE_API_USER: str = ""
    CONFLUENCE_API_TOKEN: str = ""
    CONFLUENCE_SPACE_KEYS: str = "SPIM,SBOM"   # 콤마 구분, list 변환은 property 로

    @property
    def confluence_space_keys_list(self) -> list[str]:
        return [k.strip() for k in self.CONFLUENCE_SPACE_KEYS.split(",") if k.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
