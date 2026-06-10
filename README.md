# PLC 래더 변환 멀티 에이전트

![CI](https://github.com/baesy2/ld/actions/workflows/ci.yml/badge.svg)
![python](https://img.shields.io/badge/python-3.11+-blue)
![license](https://img.shields.io/badge/license-Apache--2.0-green)

자연어(한국어) → 상태머신 명세 → IEC 61131-3 ST → **정형 검증** → 래더 JSON.
산업 자동화(LS일렉트릭/메카피온 등) PLC 래더 변환 백엔드 + 라이브 웹 에디터.

> 설계 원칙: **결정론(테스트 가능) 코어 먼저 → LLM 레이어.** 신뢰의 핵심은 모델이 아니라
> 메모리맵 할당 · 이중코일 기계적 제거 · Z3 인터락 증명이다. 자세한 검토는
> [`ARCHITECTURE_REVIEW.md`](ARCHITECTURE_REVIEW.md), 전체 플랜은 [`PLAN.md`](PLAN.md).

### 📘 핵심 문서
- **[백서 `docs/WHITEPAPER.md`](docs/WHITEPAPER.md)** — 난제·아키텍처·재현 가능 측정치·형식 증명 사례·한계.
- **[사용자 매뉴얼 `docs/MANUAL.md`](docs/MANUAL.md)** — 한국어 작성법·표준회로 카탈로그·정밀테스트·내보내기·FAQ.
- **[에러코드 자료집 `docs/ERRORCODES.md`](docs/ERRORCODES.md)** — LS·미쓰비시·지멘스·오므론+공통 101건(출처 인용).
- 측정 재현: `python scripts/capability_report.py`
- 영문 브리프(글로벌 제조사용): [`docs/BRIEF_EN.md`](docs/BRIEF_EN.md)

## 맥/리눅스에서 바로 실행 (라이브 래더 에디터)

```bash
./run.sh
# → http://localhost:8000 자동 오픈
```

왼쪽에 ST를 입력하면 **즉시** 오른쪽에 래더가 그려진다(결정론 변환, API 키 불필요).
- 접점 클릭 → NO↔NC 토글, 라벨 클릭 → 심볼 일괄 리네임, Ctrl/Cmd+Z 실행취소.
- 상단 **자연어 입력** → ST 자동 생성 (LLM, `ANTHROPIC_API_KEY` 필요 · `pip install -e ".[llm]"`).
- 우측 하단 **에러코드 조회** → 벤더별(LS/미쓰비시/지멘스/옴론) 검색.
- 이중코일·인터락은 실시간 검출.

데스크톱 앱(.app)으로 감싸려면 [`desktop/README.md`](desktop/README.md) 참조 (Tauri).

> Windows: `python -m venv .venv && .venv\Scripts\activate && pip install -e ".[web]" && uvicorn app.server:app`

## Docker 로 실행

```bash
docker compose up --build           # http://localhost:8000
# 자연어 생성까지: .env 에 ANTHROPIC_API_KEY 설정 후 위 명령
```

## API

| 메서드 | 경로 | 설명 | 키 |
|---|---|---|---|
| POST | `/api/transpile` | ST → 래더 JSON + 검증 | 불필요 |
| POST | `/api/generate` | 자연어 → ST + 래더 + 검증 | 필요 |
| GET | `/api/errorcodes?vendor=&q=` | 에러코드 조회 | 불필요 |
| GET | `/healthz` · `/version` | 헬스/버전 | 불필요 |

## 현재 구현 상태

| Phase | 내용 | 상태 |
|---|---|---|
| A | 골격 · 타입 안전 설정(vendor-agnostic `LLM_PROVIDER`) | ✅ |
| B | Pydantic 데이터 계약 (spec/verification/ladder) | ✅ |
| C | 디바이스 할당기 · 이중코일 OR 병합 · **Z3 인터락 검증** | ✅ |
| H1 | **결정론 ST→래더 트랜스파일러** (boolexpr DNF) | ✅ |
| D | 4-에이전트 (analyst LLM · architect LLM · verifier/renderer 결정론) | ✅ |
| E | 파이프라인 피드백 루프 (verify→architect, give_up 게이트) | ✅ |
| F | FastAPI `/api/transpile` · `/api/generate` · `/api/errorcodes` · `/healthz` | ✅ |
| — | 웹 래더 에디터 (라이브 SVG · 접점 토글 · 심볼 리네임 · undo/redo · 자연어 입력) | ✅ |
| — | 에러코드 KB (37개 시드, LS/미쓰비시/지멘스/옴론, 출처추적·ToS존중) | ✅ |
| — | 데스크톱 앱 (Tauri 셸 스캐폴드) | ✅(스캐폴드) |
| G | RAG 명령어 규격 검색 (BM25-lite, FAISS 옵션) | ✅ |
| I | 골든셋 평가 하니스 (이중코일 0 · 인터락 0 게이트) | ✅ |
| — | 자체모델 LoRA 튜닝 파이프라인 (Qwen2.5-Coder) | ✅(스캐폴드) |
| J | Docker · CI · 입력가드 · 로깅 · 재시도 | ✅ |

## 개발

```bash
uv venv --python 3.11 && uv pip install -e ".[dev,web]"
source .venv/bin/activate

pytest                  # 단위 테스트 (API 키 불필요)
ruff check app tests scripts training
mypy app                # 타입 (strict)
python scripts/eval.py  # 골든셋 회귀 게이트
```

CI(`.github/workflows/ci.yml`)가 위 전부를 PR마다 검증한다. Claude Code 웹 세션은
`.claude/settings.json` 의 SessionStart 훅으로 환경을 자동 구성한다.

## 자체 모델 튜닝 (선택)

API 의존을 줄이고 온프레미스(공장 폐쇄망)로 가려면 허용 라이선스 모델을
자체 클린 데이터로 튜닝한다. [`training/README.md`](training/README.md):

```bash
python training/export_dataset.py --kind both --out data/sft.jsonl  # verify 통과분만 학습셋
# GPU 박스에서: python training/train_lora.py --data data/sft.jsonl
# vLLM 서빙 후: LLM_PROVIDER=openai_compatible LOCAL_BASE_URL=http://localhost:8000/v1
```

**안전장치**: `verify()` 를 통과한 샘플만 학습 데이터로 채택 → 모델이 나빠도
결정론 게이트가 불량을 거른다.

## 프로젝트 구조

```
app/
  config.py       설정 (LLM_PROVIDER: anthropic|openai_compatible|local)
  models.py       Pydantic 데이터 계약
  memory_map.py   디바이스 할당기 + 이중코일 병합
  verifier.py     정형 검증 (이중코일 · Z3 인터락 · 도달성)
  boolexpr.py     불리언 AST + DNF(Sum-of-Products)
  transpiler.py   결정론 ST → 래더 (Phase H1)
  prompts.py      에이전트 시스템 프롬프트
  rag.py          명령어 규격 검색 (BM25-lite + FAISS 옵션)
  agents.py       4 에이전트 (_llm 팩토리 = vendor-agnostic + 재시도)
  graph.py        파이프라인 오케스트레이션 (피드백 루프 + give_up)
  error_codes.py  에러코드 KB (스키마 + 합법 수집 원칙)
  server.py       FastAPI (입력가드 · CORS · 로깅 · 예외핸들러)
frontend/         웹 래더 에디터 (라이브 SVG · 토글 · 리네임 · undo/redo · 자연어)
data/             instructions.jsonl (RAG 코퍼스)
scripts/          eval.py (골든셋 게이트) · setup.sh
training/         LoRA 튜닝 파이프라인 (export_dataset · train_lora)
desktop/          Tauri 데스크톱 셸
.github/          CI 워크플로
```

## 에러코드 통합 — 합법 수집 원칙

제조사 사이트 무차별 스크래핑은 하지 않는다. `app/error_codes.py` 참조:
robots.txt/ToS 존중, 매뉴얼 본문 복제 금지, **에러코드 사실 데이터 + 출처 명기**만,
공식·공개 레퍼런스만 정식 경로로 수집, 라이선스 모호 항목은 법무 확인.

## ⚠️ 안전 경계 (필독)

**이 도구의 검증(이중코일 제거·Z3 인터락 증명·도달성)은 논리 보조이며 기능 안전을
보장하지 않는다.** E-stop·가드·정역 전원차단 등 안전 기능은 표준 PLC 래더의 소프트웨어
인터락이 아니라 **하드와이어 안전릴레이 / 안전인증 PLC로 전원을 차단**해 구현해야 한다
(ISO 13849 / IEC 62061 / IEC 60204-1 / NFPA 79). 생성 코드는 SIL2+ 안전로직에 그대로
쓰지 말고 유자격 엔지니어가 반드시 검토·검증한다. 자세한 내용은 [`docs/SAFETY.md`](docs/SAFETY.md),
실무 근거는 [`docs/research/real-world-ladder-practices.md`](docs/research/real-world-ladder-practices.md) §4.
고지문은 `GET /api/safety` 로도 제공된다.

## 학습·설계 문서 (docs/research)

웹의 래더 교육·실무 자료를 조사·학습해 정리한 문서:
- [`real-world-ladder-practices.md`](docs/research/real-world-ladder-practices.md) — 실무 래더 작성·사용 실태 + 갭 분석
- [`ladder-knowledge-base.md`](docs/research/ladder-knowledge-base.md) — 커리큘럼·벤더 명령어셋·한일 용어·예제·표현포맷
- [`design-direction.md`](docs/research/design-direction.md) — 학습 기반 설계 방향 + 로드맵(Phase K~N)
