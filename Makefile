# PLC 래더 에이전트 — 배포/검증 단축 명령.
# 사내 TLS 가로채기 프록시에서 빌드가 인증서 오류면 CA_BUNDLE 을 넘긴다:
#   make build CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
IMAGE ?= plc-ladder-agent:latest
PORT ?= 8000
CA_BUNDLE ?=

.PHONY: help build run up up-sandbox down smoke logs clean

help:  ## 명령 목록
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

build:  ## 엔진 이미지 빌드(필요 시 CA_BUNDLE 시크릿)
	@if [ -n "$(CA_BUNDLE)" ]; then \
	  DOCKER_BUILDKIT=1 docker build --secret id=cabundle,src=$(CA_BUNDLE) -t $(IMAGE) . ; \
	else \
	  docker build -t $(IMAGE) . ; \
	fi

run: build  ## 단일 컨테이너로 실행 후 /healthz 확인
	docker rm -f plc-ladder >/dev/null 2>&1 || true
	docker run -d --name plc-ladder -p $(PORT):8000 $(IMAGE)
	@echo "→ http://localhost:$(PORT)  (Ctrl-C 후 'make clean')"

up:  ## 한 줄 배포: 엔진만(http://localhost:8000)
	docker compose up --build

up-sandbox:  ## 엔진 + OpenPLC v3 가상 PLC(:502, :8080)
	docker compose --profile sandbox up --build

down:  ## compose 정리
	docker compose down

smoke:  ## Docker 없이 CI 안전 스모크 테스트
	pytest tests/test_deploy_smoke.py -q

logs:  ## 엔진 로그 추적
	docker compose logs -f plc-ladder

clean:  ## 단일 실행 컨테이너 제거
	docker rm -f plc-ladder >/dev/null 2>&1 || true
