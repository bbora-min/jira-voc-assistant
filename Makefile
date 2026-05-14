.PHONY: help up down logs install backend-install frontend-install dev backend-dev frontend-dev migrate seed demo clean

help:
	@echo "AI VOC - Make targets"
	@echo "  make up                인프라 컨테이너 (mysql/redis/chroma) 기동"
	@echo "  make down              인프라 종료"
	@echo "  make logs              인프라 로그 follow"
	@echo "  make install           backend + frontend 의존성 설치"
	@echo "  make dev               backend + frontend 개발 서버 동시 기동"
	@echo "  make backend-dev       FastAPI uvicorn --reload"
	@echo "  make frontend-dev      Vite dev 서버"
	@echo "  make migrate           Alembic upgrade head"
	@echo "  make seed              DB 초기화 + 샘플 시드"
	@echo "  make demo              end-to-end 시연 시나리오"
	@echo "  make clean             빌드/캐시 정리"

up:
	docker compose up -d
	@echo "Waiting for mysql healthy..."
	@until docker compose ps mysql --format json | grep -q '"Health":"healthy"'; do sleep 2; done
	@echo "Infra ready."

down:
	docker compose down

logs:
	docker compose logs -f

backend-install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -e ".[dev]"

frontend-install:
	cd frontend && npm install

install: backend-install frontend-install

backend-dev:
	cd backend && .venv/bin/uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8080

frontend-dev:
	cd frontend && npm run dev

dev:
	@command -v npx >/dev/null || (echo "node/npm required" && exit 1)
	npx -y concurrently -n be,fe -c blue,green "make backend-dev" "make frontend-dev"

migrate:
	cd backend && .venv/bin/alembic upgrade head

seed:
	cd backend && .venv/bin/python -m app.seed.seed --reset --with-samples

demo:
	cd backend && .venv/bin/python -m app.seed.demo

clean:
	rm -rf backend/.venv backend/.pytest_cache backend/.ruff_cache backend/build
	rm -rf frontend/node_modules frontend/dist
