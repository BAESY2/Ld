# PLC 래더 에이전트 — 웹앱 + 자연어 생성(LLM) 포함 이미지.
# 결정론 경로(ST→래더·마법사·검증·시뮬)는 API 키 없이 동작. 자연어 생성에만 키 필요.
FROM python:3.11-slim

# 보안: 비루트 사용자로 실행
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    GEN_OUT_DIR=/app/out

# 의존성 메타 + 패키지 소스(레이어 캐시: pyproject 변경 없으면 재설치 안 함)
COPY pyproject.toml README.md ./
COPY app ./app
COPY frontend ./frontend

# editable 설치로 정적 프론트 경로(app/../frontend)를 유지한다.
# web = FastAPI/uvicorn, llm = langgraph/langchain(자연어 생성 — 키 없으면 비활성).
# 참고: 사내 TLS 가로채기 프록시 환경에서는 빌드시 CA 번들을 넘길 수 있다(선택):
#   DOCKER_BUILDKIT=1 docker build --secret id=cabundle,src=/etc/ssl/certs/ca-certificates.crt .
# 일반 네트워크에서는 시크릿 없이 그대로 빌드된다(required=false).
RUN --mount=type=secret,id=cabundle,required=false \
    if [ -f /run/secrets/cabundle ]; then export PIP_CERT=/run/secrets/cabundle; fi; \
    pip install --no-cache-dir -e ".[web,llm]"

# 런타임 codegen 출력 디렉터리(비루트가 쓸 수 있게 소유권 부여)
RUN mkdir -p /app/out && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# 컨테이너 자체 헬스체크 — compose 가 "healthy" 판정에 사용
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"

CMD ["sh", "-c", "uvicorn app.server:app --host 0.0.0.0 --port ${PORT}"]
