# DEMO — 한국어 한 문장 → 이해 → 정형검증된 래더 (end-to-end 증거)

이 문서는 **한국어 한 문장이 전 파이프라인을 통과해 *기계검증된* 래더가 되는 과정**을
한 화면에 보여준다. AI/LLM·API 키 없이 **결정론**으로 돌고, 못 하면 **정직하게 보류**한다.

재현:

```bash
source .venv/bin/activate
python scripts/demo_e2e.py        # 사람이 읽는 단계별 전사
pytest -q tests/test_demo_e2e.py  # 불변식(이중코일0·verify passed·보류) 회귀
```

---

## 1. 한 화면 요약: 입력(한국어) → 이해 → 검증된 래더

대표 문장 **`"셔터 열고 닫아"`** — 개·폐 동시구동 금지(인터락)가 *기계증명*되는 사례.

```
------------------------------------------------------------------------
입력(한국어): '셔터 열고 닫아'
  (a) 형태소 분석 : 인식 ['셔터', '열고', '닫아'] | coverage=1.00
  (b) 의도 프레임 : 동작: 셔터 열기 / 동작: 닫기 | 확신도=1.00 (confident=True)
  (c) 레시피 매핑 : shutter_gate ('셔터/게이트 개폐') | 점수=3.0
  (d) 합성 ST    : 대입문 2개 | 이중코일=0
        MTR_OPEN := ((OPEN_PB AND NOT CLOSE_PB AND NOT STOP_PB AND NOT OPEN_LS) OR MTR_OPEN) AND NOT ((STOP_PB OR OPEN_LS OR CLOSE_PB)) AND NOT MTR_CLOSE;
        MTR_CLOSE := ((CLOSE_PB AND NOT OPEN_PB AND NOT STOP_PB AND NOT CLOSE_LS) OR MTR_CLOSE) AND NOT ((STOP_PB OR CLOSE_LS OR OPEN_PB)) AND NOT MTR_OPEN;
  (e) 정형검증    : passed=True | k-귀납 증명 인터락 쌍=MTR_CLOSE!=MTR_OPEN, MTR_OPEN!=MTR_CLOSE
  (f) 래더        : 렁 2개, 접점 20개 (ST 대입문->Sum-of-Products 렁)
```

읽는 법:
- **(a)** 한글 자모 산술(받침)·조사·어미로 어절을 형태소로 분해한다 — `coverage` 는 인식
  비율(설명가능 확신도의 근거).
- **(b)** SOV·조건절(-면) 문법으로 `(조건 → 동작·대상)` 프레임을 만들고 사람 말로 설명한다.
- **(c)** 키워드 겹침이 아니라 *구조 특징*(predicate·device·단위)으로 검증된 레시피를 고른다.
- **(d)** 명세를 자기유지(seal-in) ST 로 **결정론 합성** → 출력당 대입 1회(**이중코일 0**).
- **(e)** Z3 + **k-귀납**으로 인터락 상호배제를 *모든 도달 스캔*에 대해 증명한다
  (증명된 쌍만 표시 — `MTR_OPEN`/`MTR_CLOSE` 동시 ON 불가).
- **(f)** ST 대입문을 DNF(Sum-of-Products) 래더 렁으로 변환한다.

---

## 2. 무엇이 결정론·기계검증인가 (과장 없음)

| 단계 | 무엇 | 성질 |
|------|------|------|
| (a) 형태소 분석 | `korean.analyze` | **결정론**(한글 자모 산술·규칙). LLM 없음. |
| (b) 의도 프레임 | `intent.extract` | **결정론**. coverage 기반 확신도(보정). |
| (c) 레시피 매핑 | `intent.match_by_frame` | **결정론**. 구조 특징 점수. |
| (d) ST 합성 | `synth.synthesize_st` | **결정론**. 이중코일 0 보장(출력당 1대입). |
| (e) 정형검증 | `verifier.verify` + `proven_safe_pairs` | **기계증명**(Z3 / k-귀납). 인터락 상호배제. |
| (f) 래더 | `transpiler.transpile_st` | **결정론**(DNF 변환). |

핵심 불변식(데모가 매 실행 단정):
- 확신 문장은 **전원 이중코일 0**, **`verify` passed**.
- 인터락 쌍은 *증명된 것만* 안전으로 표시(positive proof only) — 증명 못 하면 표시 안 함.

---

## 3. 정직 단서 (못 하는 건 보류한다 — 환각 0)

`demo_e2e.py` 는 두 경우 **거짓 래더를 만들지 않고 '보류(HELD)'** 한다:

```
입력(한국어): '5초 뒤에 모터를 돌려라'
  (a) 형태소 분석 : 인식 ['5초', '모터를', '돌려'] | coverage=0.60
  (b) 의도 프레임 : 동작: 모터 5초 가동 | 확신도=0.60 (confident=False)
  [보류 HELD] 확신 미달(certainty<0.8) — 인식 못 한 형태소가 있어 거짓 이해를 막음
     -> 거짓 래더를 생성하지 않습니다(환각 0).

입력(한국어): '오늘 점심 뭐 먹지'
  (a) 형태소 분석 : 인식 [] | coverage=0.00
  (b) 의도 프레임 : 이해한 지시가 없습니다. | 확신도=0.00 (confident=False)
  [보류 HELD] 확신 미달(certainty<0.8) — 인식 못 한 형태소가 있어 거짓 이해를 막음
     -> 거짓 래더를 생성하지 않습니다(환각 0).
```

- **도메인 한정**: 산업 제어 어휘(범용 한국어 NLP 아님). 어휘 밖 형태소는 coverage 를
  떨어뜨려 확신을 낮춘다 → 그 자체가 정직 신호다.
- **미인식·비확신은 보류**: `certainty < 0.8` 이거나 매핑되는 검증된 레시피가 없으면
  생성하지 않는다.
- **소프트 로직 한계**: 합성된 인터락은 *소프트웨어* 상호배제다. 비상정지·안전 인터락은
  반드시 안전인증 부품으로 **하드와이어** 구현해야 한다(각 레시피 `safety_note` 참조).

---

## 4. 전체 전사(8문장) 요약

`python scripts/demo_e2e.py` 의 마지막 줄:

```
요약: 총 8문장 | 확신·검증 6건 (전원 이중코일0·verify passed) | 보류 2건
```

확신 6건: `모터를 돌려`(motor_start_stop) · `컨베이어를 멈춰`(motor_start_stop) ·
`부품10개세면배출해`(count_eject, **띄어쓰기 없는 변형**) ·
`저수위가 되면 펌프를 켜고 고수위가 되면 꺼라`(hi_lo_level) ·
`압력이 5바 넘으면 펌프 켜`(pressure_band, 아날로그 비교) ·
`셔터 열고 닫아`(shutter_gate, 인터락 증명).
보류 2건: `5초 뒤에 모터를 돌려라`(확신 미달) · `오늘 점심 뭐 먹지`(도메인 밖).
