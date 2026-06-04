# PLC 래더 변환 멀티 에이전트 — Claude Code 빌드 플랜

> 이 문서는 Claude Code에 그대로 먹여서 단계별로 빌드하기 위한 실행 스펙이다.
> 원칙: **결정론적(테스트 가능) 코어 먼저 → LLM 레이어 → 오케스트레이션 → API → RAG/프론트.**
> 각 작업(Task)은 독립적으로 빌드·검증·커밋할 수 있게 쪼개져 있다.

---

## 0. 시작 전 결정 사항 (Decision Log)

빌드 시작 전에 아래 기본값을 그대로 쓸지 결정한다. (변경 안 하면 이 값으로 진행)

| 항목 | 기본값 | 비고 |
|---|---|---|
| Python | 3.11+ | match 문, 최신 typing |
| 패키지 매니저 | `uv` (없으면 `pip + venv`) | 빠른 설치 |
| LLM | Anthropic Claude | analyst/renderer=Sonnet, architect=Opus |
| 오케스트레이션 | LangGraph `StateGraph` | 순환(피드백) 때문에 필수 |
| 검증 | Z3 (`z3-solver`) | 인터락 수학 증명 |
| RAG 스토어 | 1차 더미 → 2차 FAISS | Month 1엔 미사용 |
| API | FastAPI + uvicorn | |
| 테스트 | pytest | |
| 코드 품질 | ruff + mypy | |
| 프론트 | 별도 레포(웹 래더 에디터) | API로만 연동 |

---

## 1. Claude Code 사용법 (이 플랜 먹이는 방법)

### 1-1. 레포 최상단에 `CLAUDE.md` 생성 (Claude Code가 자동으로 읽는 컨텍스트)

```markdown
# 프로젝트 규칙 (Claude Code 필독)

## 정체성
산업 자동화(LS일렉트릭/메카피온) PLC 래더 변환 멀티 에이전트 백엔드.
자연어(한국어) → 상태머신 명세 → IEC 61131-3 ST → 정형 검증 → 래더 JSON.

## 절대 규칙
1. 모든 변수는 IEC 61131-3 표준 타입(BOOL/INT/DINT/REAL/TIME/WORD)만 사용.
2. 디바이스 클래스는 LS 체계(P=입출력, M=내부릴레이, T=타이머, C=카운터, D=데이터)만.
3. 동일 출력 심볼을 두 번 이상 코일로 대입(이중 코일)하지 않는다.
4. 새 모듈을 만들면 반드시 같은 커밋에 pytest 테스트를 추가한다.
5. LLM을 호출하는 코드는 테스트에서 반드시 mock 한다 (API 키 없이 CI 통과해야 함).
6. 타입 힌트 100%, ruff/mypy 통과 상태 유지.

## 빌드 순서 (PLAN.md 참조)
결정론적 코어 → LLM 에이전트 → LangGraph → API → RAG → 프론트 연동.
각 Task는 "완료 기준"의 명령이 통과해야 다음으로 넘어간다.

## 테스트 명령
- 단위: `pytest -q`
- 타입: `mypy app`
- 린트: `ruff check app`
```

### 1-2. 작업 투입 방식
각 Task를 **하나씩** 클로드 코드에 지시한다. 한 번에 전부 시키지 말 것 (검증 누락 위험).
각 Task 끝에 적힌 **[지시 프롬프트]** 를 복사해 붙이면 된다.

---

## 2. Phase A — 프로젝트 토대 (API 키 불필요)

### Task A1. 레포 골격
**목표**: 디렉터리·의존성·설정 파일 생성.

생성할 트리:
```
plc_ladder_agent/
├── CLAUDE.md
├── PLAN.md                  # 이 문서
├── pyproject.toml
├── .env.example
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── memory_map.py
│   ├── rag.py
│   ├── verifier.py
│   ├── prompts.py
│   ├── agents.py
│   ├── graph.py
│   └── server.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/            # 골든 명세/ST 샘플
    ├── test_models.py
    ├── test_memory_map.py
    ├── test_verifier.py
    ├── test_agents.py
    └── test_graph.py
```

`pyproject.toml` 의존성 (버전 핀):
```toml
[project]
name = "plc-ladder-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "langgraph>=0.2,<0.4",
  "langchain-anthropic>=0.3,<0.4",
  "langchain-core>=0.3,<0.4",
  "pydantic>=2.7,<3",
  "fastapi>=0.110",
  "uvicorn[standard]>=0.29",
  "z3-solver>=4.13",
  "python-dotenv>=1.0",
]
[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.4", "mypy>=1.10", "httpx>=0.27"]
rag = ["faiss-cpu>=1.8", "langchain-community>=0.3"]
```

`.env.example`:
```
ANTHROPIC_API_KEY=
ANALYST_MODEL=claude-sonnet-4-6
ARCHITECT_MODEL=claude-opus-4-8
RENDERER_MODEL=claude-sonnet-4-6
MAX_REVISIONS=3
USE_RAG=false
USE_Z3=true
```

**완료 기준**: `uv sync`(또는 `pip install -e ".[dev]"`) 성공, `pytest -q` 가 "0 tests" 로 정상 종료.
**커밋**: `chore: scaffold project structure and deps`

> **[지시 프롬프트]**
> "PLAN.md의 Task A1을 수행해줘. 위 트리대로 빈 파일과 pyproject.toml, .env.example, .gitignore, CLAUDE.md를 만들고, 가상환경에 dev 의존성까지 설치한 뒤 pytest가 깨끗하게 도는지 확인해줘. 아직 로직은 비워둬."

---

### Task A2. config.py (설정 로딩)
**목표**: 환경변수 → 타입 안전 설정 객체.
- `python-dotenv`로 `.env` 로드.
- `Settings` dataclass: 모델명 3종, temperature, max_revisions, use_rag, use_z3.
- 모듈 전역 `settings = Settings()`.

**완료 기준**: `tests/test_config.py` — 환경변수 monkeypatch 시 값이 반영되는지 1케이스.
**커밋**: `feat: typed settings loader`

---

## 3. Phase B — 데이터 계약 (모델) · 테스트 우선

### Task B1. models.py — 전체 스키마
**목표**: 파이프라인 공유 Pydantic 모델 정의. (자세한 필드는 첨부 초안 `models.py` 참조)

정의할 모델:
- 열거형: `DataType`, `DeviceClass`, `IODirection`, `TimerType`, `CounterType`, `ElementType`
- A1 산출물: `IOPoint`, `TimerSpec`, `CounterSpec`, `SfcState`, `Transition`, `Interlock`, **`StateMachineSpec`**
- A3 산출물: `VerificationIssue`, **`VerificationReport`** (`has_errors` 프로퍼티)
- A4 산출물: `LadderElement`, `LadderBranch`, `LadderRung`, **`LadderProgram`**

**래더 스키마 설계 결정**: 1차는 *Sum-of-Products*(직렬 안의 병렬) — `LadderRung.input_branches`(OR) + 각 branch의 `elements`(AND) + `outputs`(코일). 다중 중첩 브랜치는 Phase H에서 재귀 모델로 확장.

**완료 기준**: `test_models.py` — 각 모델 인스턴스화 + `model_dump_json()` 왕복(round-trip) 동등성, enum 직렬화 확인.
**커밋**: `feat: pydantic data contracts for spec/ladder/verification`

> **[지시 프롬프트]**
> "Task B1: models.py를 PLAN.md 명세대로 작성하고, test_models.py에 모든 모델의 round-trip 직렬화 테스트를 추가해줘. 첨부한 초안 models.py를 출발점으로 삼되 필드 누락 없게 검토해줘."

---

## 4. Phase C — 결정론적 코어 (API 키 불필요, **여기가 신뢰의 핵심**)

> 이 Phase는 LLM 없이 100% 단위 테스트 가능하다. 환각이 끼어들 수 없는 영역이므로
> 가장 먼저, 가장 촘촘하게 검증한다. (이미 초안에서 동작 확인됨)

### Task C1. memory_map.py — 디바이스 할당기
**목표**: 심볼↔주소 1:1 캐싱으로 이중 코일을 *구조적으로* 차단.

구현:
- `DeviceAllocator`
  - `allocate(symbol, device_class, fixed_address=None) -> str` : 1회만 발급, 재호출 시 캐시 반환, 주소 충돌 시 `ValueError`.
  - `allocate_internal_relay(hint) -> str` : 우회용 M 신규 발급.
  - `build_from_spec(spec) -> self` : 명세 전 변수 선발급.
  - `as_comment_block() -> str` : ST 상단 맵핑 주석.
- 디바이스 포맷 테이블: P/M/T/C/L/K=4자리, D=5자리.

**완료 기준** (`test_memory_map.py`):
1. `allocate` 동일 심볼 2회 → 같은 주소.
2. `fixed_address` 충돌 → `ValueError`.
3. `build_from_spec` 후 4개 입출력이 `P0000~P0003` 순차 발급.

**커밋**: `feat: device allocator with collision-safe caching`

---

### Task C2. memory_map.py — 이중 코일 병합 (Phase 2 핵심 ①)
**목표**: ST에서 동일 출력 중복 대입을 M으로 우회 후 OR 병합.

구현:
- `detect_double_coils(st_code) -> dict[str, list[str]]` : `SYMBOL := expr;` 정규식 스캔, 2회+ 만 반환.
- `merge_double_coils(st_code, allocator) -> DoubleCoilResult` :
  - 각 중복 대입을 고유 `_AUX_*`(M 디바이스)로 치환,
  - 말미에 `SYMBOL := M0 OR M1 ...;` 병합문 추가.

알고리즘 (의사코드):
```
dups = detect_double_coils(st)
for sym, exprs in dups:
    aux = []
    for i, 각 'sym := ...' 출현:
        m = allocator.allocate_internal_relay(f"{sym}_{i}")
        그 줄의 좌변을 sym -> m 로 치환
        aux.append(m)
    append: f"{sym} := {' OR '.join(aux)};"
```

**완료 기준** (`test_memory_map.py`):
- 입력 `MOTOR_FWD := A; MOTOR_FWD := B;` →
  `M000x := A; M000y := B; MOTOR_FWD := M000x OR M000y;` 형태 생성 검증.
- 중복 없으면 원본 그대로 반환.

**커밋**: `feat: double-coil elimination via M-relay OR merge`

> **검증된 예시 출력** (초안 테스트 결과):
> ```
> M0000 := START_PB AND NOT STOP_PB;
> M0001 := AUTO_CMD;
> MOTOR_FWD := M0000 OR M0001;  // 이중코일 병합(OR)
> ```

---

### Task C3. verifier.py — 정형 검증기 (Phase 2 핵심 ②③)
**목표**: 문법이 아닌 *논리* 검증. 출력→조건 역추적 + Z3 인터락 증명.

구현 3종:
1. **이중 코일**: `detect_double_coils` 결과를 `error` 이슈로.
2. **인터락 (Z3)**: `check_interlocks_z3(spec)`
   - 조건식 파서 `_to_z3(expr, vars)` : `AND/OR/NOT/괄호/심볼` 재귀하강 파싱.
   - `_collect_output_conditions(spec)` : 각 출력이 켜지는 전이 조건 수집(to_state.on_entry의 `OUT := TRUE` ← 그 전이의 condition).
   - 인터락 쌍의 ON 조건들을 `And`로 묶어 `solver.check()==sat` 이면 **위반 + 반례** 반환.
   - z3 미설치 시 `warning`만 남기고 통과(파이프라인 중단 금지).
3. **도달성/데드락**: `check_reachability(spec)` — 진입 전이 없는 상태=경고, 초기 상태 없음=에러.

진입점: `verify(spec, st_code) -> VerificationReport` (3종 합산, error 있으면 `passed=False` + `suggested_fix` 한글 생성).

**완료 기준** (`test_verifier.py`):
1. `_to_z3('A AND NOT B OR C')` 가 올바른 z3 식 생성.
2. 정/역 모터가 동시에 켜질 수 있는 명세 → `INTERLOCK` error + 반례 문자열 포함.
3. 정상 상호배타 명세 → 인터락 통과.
4. 초기 상태 없는 명세 → `DEADLOCK` error.

**커밋**: `feat: formal verifier (double-coil, Z3 interlock, reachability)`

> **검증됨**: 초안에서 컨베이어 정/역 예제로 인터락 위반을 반례(`START_PB=..`)와 함께 정확히 검출.

---

## 5. Phase D — LLM 에이전트 (API 키 필요, 단 테스트는 mock)

> 핵심 설계: 에이전트 함수를 **mock 가능하게** 만든다. `_llm(model)` 팩토리를 분리하고,
> 테스트에서는 `FakeChatModel` 또는 monkeypatch로 구조화 출력을 주입한다.
> → API 키 없이 CI 통과 가능.

### Task D1. prompts.py
**목표**: 4 에이전트 시스템 프롬프트. 원본 단일 역할 규정(문서 1)을 멀티로 분배.
- `_COMMON_RULES` (인사말 금지/IEC 타입/LS 맵핑)
- `REQUIREMENTS_ANALYST_SYSTEM` (I/O·조건·동작·타이머 추출, 인터락 강제 명시)
- `ST_ARCHITECT_SYSTEM` (SFC→ST 강제, `{instruction_context}` RAG 슬롯, `{feedback}` 슬롯)
- `LADDER_RENDERER_SYSTEM` (Sum-of-Products 정규화 규칙)

**완료 기준**: import 되고 `.format(instruction_context=.., feedback=..)` 가 깨지지 않음(테스트 1케이스).
**커밋**: `feat: agent system prompts`

---

### Task D2. rag.py — 명령어 규격 RAG (스텁 → 확장)
**목표**: 아키텍트가 허용 명령어 규격 안에서만 코드 짜도록 컨텍스트 주입.
- `InstructionRetriever.retrieve(query, k) -> str`
- `USE_RAG=false` 면 `_FALLBACK_INSTRUCTIONS`(더미 규격) 반환.
- `get_instruction_context(query)` 싱글톤 진입점.
- Phase G에서 FAISS 적재로 교체.

**완료 기준**: `USE_RAG=false`일 때 더미 규격 반환 테스트.
**커밋**: `feat: instruction-set RAG stub`

---

### Task D3. agents.py — 4 에이전트
**목표**: 실제 에이전트 함수 4종.
- `_llm(model) -> ChatAnthropic(temperature=0, max_tokens=8000)` (분리/주입 가능하게).
- `run_analyst(req) -> StateMachineSpec` : `with_structured_output(StateMachineSpec, method="json_schema")`.
- `run_architect(spec, feedback=None) -> (st_code, allocator)` :
  1. `DeviceAllocator().build_from_spec(spec)` 선캐싱,
  2. RAG 규격 주입, 프롬프트에 spec_json + 맵핑 동봉,
  3. LLM 호출(순수 ST),
  4. **`merge_double_coils` 후처리로 잔여 이중코일 강제 제거**,
  5. 맵핑 주석 + 병합 ST 반환.
- `run_verifier(spec, st) -> VerificationReport` : `verifier.verify` 위임(결정론).
- `run_renderer(spec, st, allocator) -> LadderProgram` : 검증된 ST + 맵핑 → 구조화 출력.

**테스트 전략** (`test_agents.py`, **API 키 없이**):
- `FakeStructuredModel`: `invoke()`가 고정 `StateMachineSpec`/`LadderProgram` 픽스처 반환하도록 `_llm`을 monkeypatch.
- `run_architect`에서 LLM이 이중코일 ST를 뱉어도 후처리로 제거됨을 검증(이게 회귀 방지의 핵심 테스트).

**완료 기준**: 위 테스트 통과 + (선택) `ANTHROPIC_API_KEY` 있을 때만 도는 `@pytest.mark.live` 실호출 1케이스.
**커밋**: `feat: four agents with mockable llm boundary`

> **[지시 프롬프트]**
> "Task D3: agents.py를 작성하되 _llm 팩토리를 monkeypatch 가능하게 분리하고, test_agents.py에서 FakeStructuredModel로 4개 에이전트를 API 키 없이 테스트해줘. 특히 run_architect가 이중코일 ST를 받아도 merge_double_coils 후처리로 단일 코일이 되는 회귀 테스트를 꼭 넣어줘."

---

## 6. Phase E — 오케스트레이션 (LangGraph)

### Task E1. graph.py — StateGraph + 피드백 루프
**목표**: `analyst→architect→verifier→(renderer|loop|give_up)`.

- `PipelineState(TypedDict, total=False)`: user_request, spec, st_code, allocator, verification, ladder, feedback, revision_count, error.
- 노드: `node_analyst/architect/verifier/renderer/give_up`.
- 조건부 라우팅 `route_after_verify`:
  - `passed` → `renderer`
  - `revision_count >= MAX_REVISIONS` → `give_up`
  - else → `architect` (피드백 주입, revision_count+1)
- `build_graph()` → `compile()`, 전역 `PIPELINE`, `run_pipeline(req) -> PipelineState`.

**테스트** (`test_graph.py`, mock 에이전트로):
- 에이전트 함수들을 monkeypatch:
  - verifier가 처음엔 실패→ 두번째 통과하도록 시퀀스 → 루프가 정확히 1회 돌고 renderer 도달.
  - 항상 실패 → `MAX_REVISIONS` 후 `give_up`, `error` 채워짐, 무한루프 없음.

**완료 기준**: 위 2 시나리오 통과.
**커밋**: `feat: langgraph pipeline with verify->architect feedback loop`

---

### Task E2. (선택) Checkpointer
**목표**: 장시간 세션/디버깅·재개. 개발=`MemorySaver`, 운영=`PostgresSaver`.
- `build_graph(checkpointer=None)` 인자화, `compile(checkpointer=...)`.
**완료 기준**: thread_id로 중간 상태 재개 테스트 1케이스.
**커밋**: `feat: optional checkpointer for durable runs`

---

## 7. Phase F — API 서버

### Task F1. server.py — FastAPI
**목표**: 프론트 단일 진입점. 문서 1의 [Output Format] 3섹션을 응답에 매핑.
- `POST /generate` : `{request}` → `{logic_analysis, structured_text, ladder, verification, error}`.
- `_logic_analysis(spec)` : 3줄 이내 Condition→Action 요약.
- `GET /healthz`.
- CORS 미들웨어(프론트 도메인 허용).
- 예외 핸들러: LLM 타임아웃/검증 실패를 깔끔한 에러로.

**테스트** (`test_server.py`, `httpx` + `run_pipeline` monkeypatch):
- `/generate` 200 + 스키마 형태 검증.
- `/healthz` 200.

**완료 기준**: 위 통과 + 수동 `uvicorn app.server:app` 기동 확인.
**커밋**: `feat: fastapi /generate endpoint`

---

## 8. Phase G — RAG 락다운 강화 (Month 2)

### Task G1. 명령어 규격 코퍼스 구축
- LS일렉트릭/메카피온 명령어 1개 = 청크 1개(명령어명·인자·디바이스 제약·예제).
- 포맷: JSONL → 임베딩.

### Task G2. FAISS 적재 + 검색
- 임베딩: 한국어 강한 모델(예: BGE-m3) 권장.
- `rag.py`의 `_load_store`/`retrieve`를 FAISS 검색으로 교체, `USE_RAG=true`.
**완료 기준**: 질의 "타이머" → TON/TOF 규격 청크가 top-k에 등장.
**커밋**: `feat: FAISS-backed instruction retrieval`

---

## 9. Phase H — 정밀도 강화 (래더 정확도 끌어올리기)

### Task H1. ST 파서 도입 (렌더러 결정론화)
**목표**: A4를 LLM 의존에서 *결정론적 변환*으로 전환(무결점 목표).
- Lark로 ST 서브셋 문법 정의(대입·CASE·불리언식·TON/CTU 호출).
- AST → Sum-of-Products 정규화 → `LadderProgram`.
- 이중코일 처리도 텍스트가 아닌 AST 노드 단위로 재구현.
**완료 기준**: 골든 ST 20개 → 래더 JSON이 기대 트리와 일치.
**커밋**: `feat: deterministic ST->ladder transpiler (Lark)`

### Task H2. 다중 중첩 브랜치 지원
- `LadderRung`을 재귀 `LadderNode(SERIES|PARALLEL|ELEMENT)` 모델로 확장.
- 복합 인터락/병렬 브랜치 수십 개 케이스 커버.

---

## 10. Phase I — 평가 하니스 (Month 1 후반 필수)

### Task I1. 골든 세트 & 회귀 평가
**목표**: 문서가 말한 "컨베이어/엘리베이터/자동문 100세트" 자동 채점.
- `tests/fixtures/golden/`에 `{자연어, 기대 spec, 기대 인터락, 금지 조건}` 케이스.
- 평가 지표:
  - **이중코일 0건** (하드 게이트),
  - **인터락 위반 0건**,
  - I/O 누락률, 상태 전이 정확도.
- `scripts/eval.py` : 케이스 배치 실행 → 점수표 출력.
**완료 기준**: 100세트에서 이중코일/인터락 위반 0, 통과율 리포트 생성.
**커밋**: `feat: golden-set eval harness`

---

## 11. Phase J — 하드닝 & 배포

- 구조화 출력 파싱 실패 시 재시도(backoff).
- LangSmith 트레이싱(에이전트별 호출 추적).
- Dockerfile + `uvicorn --workers`.
- Rate limit / 입력 길이 가드.
- `mypy app` / `ruff check app` CI 게이트.
**커밋**: `chore: hardening, tracing, docker`

---

## 12. 빌드 순서 요약 (체크리스트)

```
[ ] A1 레포 골격         (키 X)  pytest 0 tests
[ ] A2 config            (키 X)
[ ] B1 models            (키 X)  round-trip 테스트
[ ] C1 allocator         (키 X)  ★ 신뢰 코어
[ ] C2 double-coil merge (키 X)  ★ Phase2 핵심①
[ ] C3 verifier+Z3       (키 X)  ★ Phase2 핵심②③
[ ] D1 prompts           (키 X)
[ ] D2 rag stub          (키 X)
[ ] D3 agents            (mock) ★ 후처리 회귀 테스트
[ ] E1 graph 루프        (mock) ★ 무한루프 방지
[ ] E2 checkpointer      (선택)
[ ] F1 fastapi           (mock)
[ ] --- 여기서 1차 동작 데모 가능 ---
[ ] G1/G2 RAG FAISS
[ ] H1 ST 파서 (결정론 렌더러)
[ ] H2 중첩 브랜치
[ ] I1 골든 100세트 평가
[ ] J  하드닝/배포
```

**1차 데모 마일스톤**: A~F 완료 시 `자연어 → ST + 래더 JSON + 검증리포트`가 끝까지 흐른다.
C 단계까지는 API 키 없이 끝나므로, 토큰을 쓰기 전에 토대의 무결점성이 보장된다.

---

## 13. 자주 막히는 지점 (미리 경고)

1. **재귀 스키마 + 구조화 출력**: `LadderRung`을 처음부터 재귀로 만들면 tool schema가 무한 전개되어 구조화 출력이 깨진다. → 1차는 Sum-of-Products(유한)로, 재귀는 H2에서.
2. **이중코일은 LLM을 믿지 말 것**: 프롬프트로 금지해도 샌다. 반드시 `merge_double_coils` 후처리 + verifier 게이트로 *기계적으로* 막는다.
3. **Z3 조건식 파서**: ST의 모든 식을 다 파싱하려 하지 말 것. 인터락 검증에 필요한 불리언식(AND/OR/NOT)만 다룬다. 산술/타이머는 별도 추상화.
4. **피드백 루프 무한반복**: `MAX_REVISIONS` 게이트 없으면 토큰을 태운다. graph 테스트에 "항상 실패→give_up" 케이스 필수.
5. **API 키 의존 테스트**: 에이전트/그래프 테스트가 키를 요구하면 CI가 못 돈다. `_llm` 경계에서 mock.
```
