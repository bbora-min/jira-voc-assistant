# AI 기반 Jira VOC 대응 자동화

LLM + RAG 기반 VOC 자동 응대 시스템. Jira 신규 이슈를 webhook으로 받아 RAG로 사내 가이드를 검색하고 LLM이 답변 초안을 생성, 운영자가 React 대시보드에서 검토·승인하면 Jira 코멘트로 자동 등록됩니다.

## 빠른 시작

```bash
cp .env.example .env
# .env 수정: ANTHROPIC_API_KEY, VOYAGE_API_KEY, VOC_DATA_KEY 채우기

make up                # mysql / redis / chroma 컨테이너 기동
make install           # backend + frontend 의존성 설치
make migrate           # DB 마이그레이션
make seed              # 카테고리 / 샘플 코퍼스 / 샘플 티켓 시드
make dev               # backend(:8080) + frontend(:5173) 동시 기동
```

## 구성

| 영역 | 스택 |
|---|---|
| Frontend | React 18 + TypeScript + Vite + TanStack Query + Zustand + Tiptap + Recharts |
| Backend | FastAPI + SQLAlchemy + Alembic + APScheduler |
| Realtime | WebSocket + Redis pub/sub |
| DB | MySQL 8 (PII는 AES-256-GCM) |
| LLM | Anthropic Claude (claude-opus-4-7 / claude-sonnet-4-6) |
| RAG | Chroma + Voyage 임베딩 |
| Mock | INTEGRATION_MODE=mock 시 Jira/Confluence를 인메모리로 대체 |

상세 설계는 `/home/bora/.claude/plans/ticklish-jumping-waterfall.md` 참조. 원본 요구사항은 [docs/AI_VOC_요구사항정의서.pdf](docs/AI_VOC_요구사항정의서.pdf).

## 디렉토리

```
backend/   FastAPI + 파이프라인 + Provider 추상화
frontend/  Vite + React SPA (운영자 대시보드)
docs/      원본 요구사항 PDF
```

## 환경 변수

`.env.example` 참조. 핵심:
- `ANTHROPIC_API_KEY`: Claude API 키
- `VOYAGE_API_KEY`: 임베딩용 (Voyage AI)
- `VOC_DATA_KEY`: AES-256 키 (base64, 32바이트)
- `INTEGRATION_MODE`: `mock` 또는 `real`
