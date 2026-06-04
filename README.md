# PLC 래더 변환 멀티 에이전트

자연어(한국어) → 상태머신 명세 → IEC 61131-3 ST → **정형 검증** → 래더 JSON.
산업 자동화(LS일렉트릭/메카피온 등) PLC 래더 변환 백엔드 + 라이브 웹 에디터.

> 설계 원칙: **결정론(테스트 가능) 코어 먼저 → LLM 레이어.** 신뢰의 핵심은 모델이 아니라
> 메모리맵 할당 · 이중코일 기계적 제거 · Z3 인터락 증명이다. 자세한 검토는
> [`ARCHITECTURE_REVIEW.md`](ARCHITECTURE_REVIEW.md), 전체 플랜은 [`PLAN.md`](PLAN.md).

## 맥/리눅스에서 바로 실행 (라이브 래더 에디터)

```bash
./run.sh
# → http://localhost:8000 자동 오픈
```

왼쪽에 ST를 입력하면 **즉시** 오른쪽에 래더가 그려진다(결정론 변환, API 키 불필요).
접점을 클릭하면 NO↔NC가 토글되며 ST에 반영된다. 이중코일은 실시간으로 검출된다.

> Windows: `python -m venv .venv && .venv\Scripts\activate && pip install -e ".[web]" && uvicorn app.server:app`

## 현재 구현 상태

| Phase | 내용 | 상태 |
|---|---|---|
| A | 골격 · 타입 안전 설정(vendor-agnostic `LLM_PROVIDER`) | ✅ |
| B | Pydantic 데이터 계약 (spec/verification/ladder) | ✅ |
| C | 디바이스 할당기 · 이중코일 OR 병합 · **Z3 인터락 검증** | ✅ |
| H1 | **결정론 ST→래더 트랜스파일러** (boolexpr DNF) | ✅ |
| F | FastAPI `/api/transpile` · `/healthz` + 정적 프론트 | ✅ |
| — | 웹 래더 에디터 (라이브 SVG 미리보기 + 접점 토글 편집) | ✅ |
| — | 에러코드 KB 스키마 (출처 추적 · ToS 존중 원칙) | ✅(스텁) |
| D/E | LLM 4-에이전트 + LangGraph 피드백 루프 | ⏳ |
| D/E 후 | `/api/generate` 자연어 경로 | ⏳ |

## 개발

```bash
uv venv --python 3.11 && uv pip install -e ".[dev,web]"
pytest          # 단위 테스트 (API 키 불필요)
ruff check app  # 린트
mypy app        # 타입 (strict)
```

## 프로젝트 구조

```
app/
  config.py       설정 (LLM_PROVIDER: anthropic|openai_compatible|local)
  models.py       Pydantic 데이터 계약
  memory_map.py   디바이스 할당기 + 이중코일 병합
  verifier.py     정형 검증 (이중코일 · Z3 인터락 · 도달성)
  boolexpr.py     불리언 AST + DNF(Sum-of-Products)
  transpiler.py   결정론 ST → 래더
  error_codes.py  에러코드 KB (스키마 + 합법 수집 원칙)
  server.py       FastAPI
frontend/
  index.html      웹 래더 에디터
  app.js          라이브 변환 + SVG 렌더러 + 접점 토글
```

## 에러코드 통합 — 합법 수집 원칙

제조사 사이트 무차별 스크래핑은 하지 않는다. `app/error_codes.py` 참조:
robots.txt/ToS 존중, 매뉴얼 본문 복제 금지, **에러코드 사실 데이터 + 출처 명기**만,
공식·공개 레퍼런스만 정식 경로로 수집, 라이선스 모호 항목은 법무 확인.
