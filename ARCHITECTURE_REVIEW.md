# 아키텍처 검토 — 합법 IP 기준 재정리

> 대상 문서: `PLAN.md` (PLC 래더 변환 멀티 에이전트)
> 검토 관점: **깨끗한 IP 출처 + 모델 교체 가능성(vendor-agnostic)**
> 결론 한 줄: **PLAN.md 아키텍처는 그대로 가도 된다. 차별화 IP는 모델이 아니라 결정론 코어다.**

---

## 0. IP 적합성 판정 (먼저 짚는 부분)

| 항목 | 판정 | 근거 |
|---|---|---|
| 유출/탈취된 Claude 가중치·내부코드 사용 | ❌ **금지** | 도난 영업비밀. 산업 납품 시 소송·계약해지·형사 리스크. 학습 인프라 없이 실행도 불가 |
| Claude API 정식 호출 (`langchain-anthropic`) | ✅ 허용 | 상용 라이선스. PLAN의 기본 설계 |
| 오픈소스 모델 자체 파인튜닝 (Qwen/Llama/DeepSeek 등) | ✅ 허용* | *모델별 라이선스 확인 필수(아래 표) |
| 골든세트(자체 제작 데이터)로 LoRA 튜닝 | ✅ 허용 | 자체 데이터 = 깨끗한 IP. 진짜 "우리만의 AI" |

**핵심 통찰**: 이 시스템의 가치는 LLM이 아니라 **메모리맵 할당기 · 이중코일 기계적 제거 · Z3 인터락 증명**에 있다.
PLAN.md가 이미 "Phase C가 신뢰의 핵심"이라고 정확히 짚었다. 모델은 교체 가능한 부품이고, 정확도는 결정론 코어에서 나온다.

---

## 1. 강점 (PLAN.md가 이미 잘한 것)

1. **결정론 코어 우선** — API 키 없이 Phase A~C까지 무결점 검증. 토큰 태우기 전에 신뢰 기반 확보.
2. **이중코일을 LLM에 안 맡김** — `merge_double_coils` 후처리 + verifier 게이트로 기계적 차단. (§13-2)
3. **Z3 정형 검증** — 문법이 아닌 *논리* 검증. 인터락 위반을 반례와 함께 증명.
4. **mock 가능한 LLM 경계** — `_llm()` 팩토리 분리로 API 키 없이 CI 통과. (§D, §13-5)
5. **무한루프 방지** — `MAX_REVISIONS` 게이트 + give_up 테스트. (§13-4)

이 5개는 산업용으로 직행 가능한 설계다. 손댈 필요 없다.

---

## 2. 모델 교체 지점 (vendor-agnostic 보강)

PLAN.md는 Anthropic에 약하게 결합돼 있다. "우리만의 AI"로 가려면 이 한 곳만 추상화하면 된다.

### 2-1. 단일 교체 지점: `agents.py`의 `_llm(model)`

현재 설계(§D3):
```python
def _llm(model: str):
    return ChatAnthropic(temperature=0, max_tokens=8000)
```

**제안: 프로바이더 추상화로 변경**
```python
# config.py 에 LLM_PROVIDER 추가: "anthropic" | "openai_compatible" | "local"
def _llm(model: str):
    match settings.llm_provider:
        case "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=model, temperature=0, max_tokens=8000)
        case "openai_compatible":            # vLLM / Ollama / TGI 등 자체 호스팅
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model, temperature=0,
                              base_url=settings.local_base_url, api_key="not-needed")
        case "local":                        # transformers 직접 로드
            from app.local_llm import LocalChatModel
            return LocalChatModel(model)
```

이렇게 하면:
- 개발/PoC = Claude API (빠른 검증)
- 운영/온프레미스 = 자체 튜닝 모델 (공장 폐쇄망, 비용↓)
- **테스트 = `FakeStructuredModel`** (§D3 그대로, 변경 없음)

세 경로 모두 같은 `with_structured_output` 인터페이스를 타므로 그래프/API/검증 코드는 한 줄도 안 바뀐다.

### 2-2. 구조화 출력 주의

자체 호스팅 모델은 `method="json_schema"` 강제 디코딩 지원이 모델·런타임마다 다르다.
- vLLM: `guided_json` (outlines) 지원 → JSON 스키마 강제 가능
- Ollama: `format=json` (느슨함) → 파싱 재시도 필요 (§J에 이미 있음)
- 대비책: Phase H1의 **Lark ST 파서**로 렌더러를 결정론화하면 모델 JSON 정확도 의존도 자체가 사라진다. (가장 강력한 보강)

---

## 3. 자체 모델 후보 (라이선스 체크)

| 모델 | 라이선스 | 산업/한국어/코드 적합성 | 비고 |
|---|---|---|---|
| **Qwen2.5-Coder** (7B/14B/32B) | Apache-2.0 | 코드 강함, 한국어 양호 | ST 생성에 1순위 추천 |
| **Llama 3.x** (8B/70B) | Llama Community (월 7억 MAU 미만 무료) | 범용 강함 | MAU 조항 확인 |
| **DeepSeek-Coder-V2** | MIT(코드)+모델약관 | 코드 특화 | 약관 확인 |
| **Mistral / Codestral** | Codestral은 비상용 라이선스 | 코드 강함 | **상용 시 별도 계약 필요** |
| **EXAONE (LG AI)** | 비상용 연구 라이선스 | 한국어 최강급 | 상용 불가 — PoC만 |

> ⚠️ 라이선스는 수시 변경된다. **납품 전 법무 확인 필수.** 위 표는 검토 시점 일반론.

**추천 조합**: Qwen2.5-Coder-14B/32B를 골든세트로 LoRA 파인튜닝 → ST 아키텍트 역할.
analyst(요구분석)는 범용 한국어가 중요하므로 초기엔 Claude API 유지 후 점진 이전.

---

## 4. 파인튜닝 파이프라인 (PLAN의 Phase I와 연결)

PLAN의 **골든세트(Task I1)가 곧 학습 데이터셋**이다. 평가 하니스 = 데이터 공장.

```
Phase I1 골든세트(자연어→기대 spec→기대 ST→기대 래더)
        │
        ├─→ 평가용 (회귀 채점)           ← PLAN 원래 용도
        └─→ 학습용 (SFT/LoRA 데이터)      ← 추가 활용
                │
                ▼
        LoRA 파인튜닝 (Qwen2.5-Coder)
          - 입력: 자연어 요구 + RAG 명령어 규격
          - 출력: 검증 통과한 ST (이중코일 0, 인터락 0)
          - 검증 게이트 통과한 샘플만 학습셋에 채택 (self-improving loop)
                │
                ▼
        vLLM 서빙 → _llm("local") 로 교체
```

**핵심 안전장치**: 학습 데이터는 반드시 `verify()`를 통과한 것만 채택한다.
→ 모델이 나빠도 결정론 코어가 불량 샘플을 걸러내므로 학습셋 품질이 자동 보장된다.

이게 진짜 "우리만의 산업용 AI"다. 깨끗한 자체 데이터 + 검증 게이트 + 도메인 특화 튜닝.

---

## 5. 권장 빌드 순서 (PLAN 체크리스트 보강)

PLAN §12 순서를 따르되, 모델 독립성을 위해 다음을 추가/이동:

```
[기존 PLAN 그대로]
[ ] A1~A2  레포 골격 + config   ← config.py에 LLM_PROVIDER 필드 추가
[ ] B1     models
[ ] C1~C3  결정론 코어 ★         ← 여기가 IP의 핵심. 가장 촘촘히.
[ ] D1~D3  prompts/rag/agents    ← _llm() 을 프로바이더 추상화로 (§2-1)
[ ] E1     graph 루프
[ ] F1     fastapi
[ ] --- 1차 데모 (Claude API) ---

[모델 독립성 보강 — 우선순위 상향]
[ ] H1     Lark ST 파서 ★★       ← 렌더러 결정론화. 모델 JSON 의존 제거.
[ ] I1     골든 100세트 ★★        ← 평가 + 학습데이터 이중 용도
[ ] (신규) FT1  LoRA 파인튜닝 파이프라인
[ ] (신규) FT2  vLLM 서빙 + _llm("local") 통합 테스트
[ ] G1~G2  RAG FAISS
[ ] J      하드닝/배포 (온프레미스 Docker 포함)
```

**변경 요지**: H1(Lark 파서)와 I1(골든세트)을 앞당긴다. 이 둘이 모델 교체의 안전망이자 학습 연료다.

---

## 6. 리스크 & 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| 자체 모델 JSON 구조화 출력 불안정 | 렌더러 깨짐 | H1 Lark 파서로 결정론화 (모델 무관) |
| 오픈소스 라이선스 변경/상용 제약 | 납품 차질 | 다중 모델 추상화로 교체 비용 0, 법무 사전 검토 |
| 파인튜닝 데이터 품질 | 모델 정확도↓ | verify() 게이트 통과분만 학습 채택 |
| 온프레미스 GPU 비용 | 운영비 | 7B/14B로 시작, 정확도는 결정론 코어가 보강 |
| 인터락 누락 (안전사고) | **치명** | Z3 검증 하드 게이트 + 골든세트 인터락 0건 강제 |

---

## 7. 최종 권고

1. **PLAN.md 아키텍처 채택** — 잘 설계됐다. 유출 모델 없이 그대로 간다.
2. **`_llm()` 한 곳만 프로바이더 추상화** — Claude ↔ 자체모델 교체를 1차 설계부터 반영.
3. **H1 + I1 우선순위 상향** — 결정론 렌더러 + 골든세트가 모델 독립성과 자체 튜닝의 토대.
4. **차별화 IP = 결정론 코어 + 검증 게이트 + 도메인 골든데이터.** 모델은 부품이다.
5. **납품 전 라이선스 법무 검토.**

> 다음 단계: 이 검토 반영해서 Phase A~C(API 키 불필요 결정론 코어) 실제 빌드 착수 가능.
