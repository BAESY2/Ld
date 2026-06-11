# 엔진 재설계 계획 (5-에이전트 분석 종합)

> 역할별 5개 병렬 분석 에이전트(합성 커버리지 · 검증 건전성 · 엔진 아키텍처 · UI/UX · Codegen)의
> 종합. **구현 완료분**과 **남은 로드맵**을 구분한다.

## 구현 완료 (이번 세션)

| 영역 | 내용 | 모듈 |
|---|---|---|
| 합성 커버리지 | `derived_outputs` 로 조합출력 커버 → **골든 20/20 완전 결정론** | `app/models.py`,`app/synth.py` |
| 검증 건전성 | `check_interlocks_st` — 명세가 아닌 **실제 합성 ST**의 seal-in 래치를 Z3 귀납 검증 | `app/verifier.py` |
| 컴파일 게이트 | matiec를 eval `--compile` 로 연결(선택적, skip-safe) | `scripts/eval.py` |
| 파일 생성 | `generate_project()` — 입력→프로젝트 파일셋(매니페스트·ST·ladder·PLCopen·벤더 IL) | `app/generate.py` |
| CLI | `plc-gen` / `python -m app.gen` (ST 경로 키 불필요) | `app/gen.py` |
| 스트리밍 UX | SSE `POST /api/generate/files` + Codex식 라이브 생성 페이지 | `app/server.py`,`frontend/generate.html` |

## 난제 해법 — 현재 상태
**자연어 →(LLM, 구조화 추출)→ 명세 →(결정론 합성)→ ST →(Z3 인터록+이중코일+matiec)→ 래더 →(벤더 에미터/PLCopen)→ 실코드/파일.**
래더 로직 생성에서 LLM을 제거. 골든 20/20이 LLM 없이 생성·검증 통과.

## 남은 로드맵 (우선순위순, 미구현)

### 1. 타이머/카운터 결정론 합성 (실무 최대 갭)
- `TimerSpec`/`CounterSpec`에 `enable_condition` 등 추가, `synth.py`가 IEC FB 콜(`TON(IN:=…, PT:=T#…)`) 생성.
- `boolexpr` 토큰을 점표기(`T1.Q`) 허용으로 확장, 트랜스파일러에 FB-콜 분기, **`detect_double_coils`가 FB콜을 코일로 오탐하지 않게** 보강(공통 선결).
- 현재 골든은 타이머를 BOOL 입력으로 위장 중 → 실타이머 픽스처 추가 필요.

### 2. SET/RST · 엣지 원샷 · MCR
- `ElementType.COIL_SET/RESET`는 이미 있음 → spec 필드 + 합성 경로 + `detect_double_coils`가 S/R 쌍을 단일 코일로 인식.
- 엣지(R_TRIG/F_TRIG) 2-rung 합성, MCR은 존 조건을 출력식에 AND-게이팅으로 근사.

### 3. 검증 강화 (P5/P6/P9, agent 2)
- E-stop 우세(`ESTOP ⇒ 모든 출력 OFF`), 래치 해제가능성, 데드락(enabled 전이 없음)을 Z3로.
- `check_reachability`를 조건 충족성(SAT) 기반으로 업그레이드.
- (스트레치) **nuXmv** 모델체크로 명세-코드 시간적 동치(LLM4PLC 스택).

### 4. 엔진 아키텍처 (agent 3) — 점진 적용
- **저위험**: 제네릭 `Registry[T]`로 벤더/패턴/합성기/익스포터 플러그인화(기존 dict 위임).
- **중위험**: 재귀 `LadderNode(SERIES/PARALLEL/ELEMENT)` IR + `to_sum_of_products()` 하위호환(PLAN H2). DNF 평탄화의 접점 중복/토폴로지 손실 해소.
- **스트리밍**: `Stage`/`RunContext`/`PipelineEvent` async 러너로 파이프라인 일반화(현재는 generate.py 콜백으로 부분 달성).
- 7단계 무중단 마이그레이션, M5(graph.run_pipeline)가 `agents.*` monkeypatch를 깨지 않게 호출 경유 유지.

### 5. 정수 스텝 시퀀서
- 긴 시퀀스(≥5스텝)용 INT 스텝 레지스터(`EQU(STEP,k)`/`MOV`) 합성. seal-in 대비 상호배제가 구조적으로 보장(STEP은 단일값).

## UI/UX 확장 (agent 4) — 부분 구현
- 구현: SSE 스트림, 파일트리 워크스페이스, 라이브 이벤트 타임라인, 파일 미리보기.
- 남음: rung별 증분 SVG 드로잉(기존 `drawRung` 재사용), 수정 루프 "자가교정" 시각화, 파일 diff/zip 다운로드, 기존 에디터와 통합(3분할 셸).
