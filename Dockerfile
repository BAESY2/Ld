# PLC 래더 에이전트 — 웹앱 + 자연어 생성(LLM) 포함 이미지.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# 의존성 메타 먼저 (레이어 캐시)
COPY pyproject.toml ./
COPY app ./app
COPY frontend ./frontend
COPY data ./data

# editable 설치로 정적 프론트 경로(app/../frontend)를 유지한다.
RUN pip install -e ".[web,llm]"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"

CMD ["sh", "-c", "uvicorn app.server:app --host 0.0.0.0 --port ${PORT}"]
