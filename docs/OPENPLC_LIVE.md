# OpenPLC 외부검증 완료 — 실 런타임 대 우리 시뮬레이터 비트 단위 차분 (증빙)

> 결론: 우리 결정론 시뮬레이터(`app.simulator.simulate`)의 출력이 **실제 OpenPLC v3
> IEC 61131-3 런타임**(MatIEC→C→gcc, 50ms 스캔 태스크, Modbus/TCP :502)과
> *비트 단위로 일치*함을 13개 합성 프로그램(조합·래치·인터락·타이머·카운터·
> 시퀀서)에서 재현 가능하게 입증했다. "디지털 트윈"은 더 이상 자기검증이 아니라
> **외부검증(externally verified)** 이다.

검증 일자: 2026-06-05 · Docker 29.3.1 · Linux x86_64.

---

## 1. 무엇이 통했나 (이미지 / 런타임)

| 항목 | 값 |
|---|---|
| **이미지** | `dainok/openplc:latest` (Docker Hub, OpenPLC **v3**, `thiagoralves/OpenPLC_v3` 기반) |
| 런타임 | Flask 웹 UI :8080 + C 런타임 + 내부 Modbus 슬레이브 :502 |
| 스캔 | `TASK Main(INTERVAL := T#50ms)` (글루 `common_ticktime__ = 50ms`) |
| 컴파일러 | MatIEC `iec2c -f -l -p -r -R -a` → g++ (실제 IEC 61131-3, 장난감 아님) |
| 웹 로그인 | 기본 `openplc` / `openplc` |

### 이미지 풀 시도 기록 (재현용 정직 기록)
- `tiagoshibata/openplc`, `foffan/openplc`, `oitc/openplc` 등 — **존재하지 않음**(pull denied).
- `Autonomy-Logic/openplc-runtime` (v4, MIT) — Docker Hub 공개 태그 없음(소스 빌드 필요).
- **성공**: Docker Hub `search openplc` 결과 중 노출 포트(502/8080)가 v3 임을 명시한
  커뮤니티 이미지 3종(`fdamador/openplc`, `wzy318/openplc`, `dainok/openplc`)을 풀.
  `dainok/openplc` 가 `ExposedPorts=502,8080` 으로 가장 깨끗 → 채택.
- 주의: Docker Hub 익명 pull 레이트리밋(분당 소수)에 쉽게 걸린다. 한 이미지만 풀면 충분.

```bash
docker run -d --name openplc -p 8080:8080 -p 5502:502 dainok/openplc:latest
```

---

## 2. 프로그램 적재 절차 (OpenPLC v3 Flask 웹폼)

우리 합성기는 **ST 바디**만 만든다(예: `MOTOR := ((START AND NOT STOP) OR MOTOR) ...`).
OpenPLC v3 는 `PROGRAM`/`CONFIGURATION`/`RESOURCE` 가 포함된 **완전한 ST 파일**을
컴파일한다. 따라서 `scripts/openplc_live_diff.py` 의 `wrap_st_for_openplc()` 가
바디를 완전한 프로그램으로 감싼다(아래 §3 의 주소맵·주의 적용).

웹 적재는 stdlib 만으로 4단계(스크립트의 `OpenPlcWeb` 가 구현):

1. `POST /login` (`username`/`password`) → 세션 쿠키.
2. `POST /upload-program` multipart `file=<완전한 .st>` → 서버가 `NNNNNN.st` 로 저장,
   응답 HTML 에 생성 파일명이 박혀 옴(정규식 `(\d+\.st)` 로 추출).
3. `POST /upload-program-action` (`prog_name`,`prog_descr`,`prog_file`,`epoch_time`)
   → DB 등록, `/compile-program?file=<fn>` 으로 리다이렉트.
4. `GET /compile-program?file=<fn>` → MatIEC 컴파일. `GET /compilation-logs` 를
   폴링해 **`Compilation finished successfully!`** 확인.
5. `GET /start_plc` → 런타임 기동, :502 Modbus 슬레이브 서빙 시작.

> v4(REST :8443) 경로는 이미지 미공개라 본 검증에서 미사용. `connect_openplc()` seam
> 과 본 적재기는 버전 무관(슬레이브 :502 동일) — v4 적재만 REST 로 바꾸면 됨.

---

## 3. 주소맵 — **핵심 발견 (load-bearing)**

### 3.1 `%IX` 디지털 입력은 Modbus 로 강제할 수 없다
OpenPLC 슬레이브 `core/modbus.cpp` 확인 결과:
- `%IX`(디스크리트 입력, FC02) → `bool_input[]`, **읽기 경로만 존재**(쓰기 없음).
- `%QX`(코일, FC01/05/0F) → `bool_output[]`, 읽기·쓰기 모두 가능.

즉 차분 검증을 위해 **우리 입력 심볼을 `%IX` 로 선언하면 외부에서 강제(force)할 수
없다**. 첫 시도에서 입력을 `%IX0.0/%IX0.1` 로 선언하니 seal-in 래치가 깨졌다(입력이
항상 0 으로 읽혀 MOTOR 가 유지되지 않음).

**해결**: 입력 심볼을 **`%QX` 코일**로 선언해 FC05/0F 로 강제한다. 단, 출력 코일과
주소가 겹치면 한 코일이 두 의미를 가지므로(이중 의미), 입력은 **출력이 차지한 바이트
다음 바이트부터** 배치한다.

### 3.2 비트주소 변환식 (검증됨)
코일번호 = `b*8 + c` (단일 선형 코일 테이블). 예: `%QX0.0→coil 0`, `%QX1.0→coil 8`.
컴파일 글루 `LOCATED_VARIABLES.h` 로 실측 확인:
```
__LOCATED_VAR(BOOL,__QX0_0,Q,X,0,0)   → coil 0
__LOCATED_VAR(BOOL,__QX1_0,Q,X,1,0)   → coil 8
```

### 3.3 우리가 쓰는 매핑 (예: motor_start_stop)
| 심볼 | 방향 | 선언 | 코일 | Modbus |
|---|---|---|---|---|
| `MOTOR` | OUTPUT | `%QX0.0` | 0 | read FC01 |
| `START` | INPUT | `%QX1.0` | 8 | force FC05 |
| `STOP`  | INPUT | `%QX1.1` | 9 | force FC05 |

출력은 코일 `0..`, 입력은 다음 바이트 경계(`8..`)부터. 충돌 0.

---

## 4. 차분 검증 방법 (`run_differential`)

`app.twin.openplc_adapter.run_differential` 가 동일 입력 타임라인을 (a) `simulate()`
와 (b) 실 OpenPLC(`ModbusPlcLink`)에 가하고 **쓰기→정착(settle)→읽기** 표본을
샘플 단위로 대조한다.

### 4.1 스캔-타이밍 — **두 번째 핵심 발견**
실 OpenPLC 의 `TON` 은 **독립 벽시계**(50ms 스캔)로 누산하고, 우리 `simulate()` 는
타이머 누산을 `step_ms` 단위로 **양자화**한다. 표본화 step 이 스캔주기보다 크면
타이머 만료가 표본 *사이*에 떨어져 **전이 표본 한 개**가 어긋난다 — 논리 오차가
아니라 **표본화 양자화 아티팩트**다.

star_delta(2초 후 STAR→DELTA 단일 핸드오프)로 step 을 쓸어 증명:

| 표본 step | 불일치 | 결과 |
|---|---|---|
| 250 ms | 2 (전이 1표본) | DIVERGE |
| 100 ms | 2 (전이 1표본) | DIVERGE |
| **50 ms** (= 스캔주기) | **0** | **AGREE** |

→ **타이머/카운터 레시피는 OpenPLC 스캔주기 50ms 에 맞춰 표본화**하면(`default_timeline`
이 자동으로) 만료가 같은 표본에 떨어져 비트 단위 일치. settle 훅이 표본당 50ms 벽시계를
진행시켜 실 PLC TON 과 우리 논리시각을 lockstep 으로 맞춘다.
조합/래치 레시피는 타이밍 비의존이라 100ms 표본으로 충분.

> **지터 강건성(실측 보강):** 체인 3-타이머 시퀀서(car_wash)는 50ms 마진이 빠듯해,
> 한 표본의 Modbus 왕복지연이 50ms 를 넘기면(호스트 부하 시) 핸드오프가 한 표본
> 어긋날 수 있었다. settle 훅을 **절대 스케줄**(t0 + n*step)에 정렬하도록 바꿔
> 일시적 지연이 다음 표본에서 자기보정되게 했다 → 부하 중 연속 5회 0/5 발산(안정).
> (step 을 75/100ms 로 키우면 1s 타이머 핸드오프가 *항상* 엇 표본에 떨어져 오히려
> 4/4 발산 — 50ms 가 정답이고 절대정렬이 보강책이다.)

### 4.2 합성기 이식성 발견 — **세 번째 발견 (리드 보고 항목, app/ 무수정)**
우리 `synthesize_st` 의 카운터 호출이 **비표준 파라미터명 `RESET`** 을 쓴다:
```
C1(CU := PART_SENSOR, RESET := RESET_PB, PV := 3);   ← 우리 합성기
```
표준 IEC 61131-3 / MatIEC 의 `CTU` 인자는 **`R`** 이다. OpenPLC 는 `RESET` 을 거부한다:
```
error: Invalid parameter 'RESET' when invoking FB 'C1'
```
우리 `app.simulator` 도 내부적으로 `RESET` 를 파싱하므로 **sim↔synth 는 자기일관**
하지만, **synth↔표준 IEC 는 어긋난다**. 적재기는 OpenPLC 로 보내는 ST 사본에서만
`RESET := → R :=` 로 번역해 카운터 *로직*의 일치를 검증한다.

> **권고(리드):** `app/synth.py` 의 `_counter_call` 을 `RESET :=` → `R :=` 로,
> 그리고 `app/simulator.py` 의 카운터 파서가 `R`(또는 `R`/`RESET` 양쪽)를 받게
> 동기화. 그러면 우리 합성 ST 가 *어떤* 표준 IEC 런타임에도 그대로 적재된다.

기타 적재기 보정(OpenPLC/MatIEC 호환, app/ 무수정):
- 합성 바디의 **한국어 `//` 주석 제거** — `iec2c` 는 ASCII C 렉서라 주석 안
  UTF-8 멀티바이트에서 파싱이 깨진다(`too many consecutive syntax errors`).
- **로케이티드(AT %QX) 변수와 FB 인스턴스를 별도 VAR 블록**으로 분리 — 같은 블록에
  섞으면 `invalid located variable declaration`.
- **IEC 예약어 심볼 거부** — `on_delay` 기본 출력명 `OUTPUT` 은 예약어라 컴파일 실패.
  답변으로 비예약어(예: `LAMP`) 지정 필요(스크립트가 친절 메시지로 안내).

---

## 5. 결과 표 (13/13 비트 단위 일치)

조합/래치/인터락 (표본 step 100ms):

| 레시피 | 출력 | 표본 | 결과 |
|---|---|---|---|
| motor_start_stop | MOTOR | 8 | **AGREE** |
| fwd_rev (인터락) | MOTOR_FWD, MOTOR_REV | 10 | **AGREE** |
| jog_run (인터락) | MOTOR_RUN, MOTOR_JOG | 10 | **AGREE** |
| conveyor_divert (인터락) | GATE_A, GATE_B | 10 | **AGREE** |
| auto_manual (파생식) | VALVE | 12 | **AGREE** |
| two_hand_safety | PRESS_ENABLE | 12 | **AGREE** |
| duty_standby | PUMP_LEAD, PUMP_LAG | 10 | **AGREE** |
| hi_lo_level | PUMP | 8 | **AGREE** |
| latch_alarm | ALARM | 12 | **AGREE** |

타이머/카운터/시퀀서 (표본 step 50ms = 스캔주기, 실시간 lockstep):

| 레시피 | 메커니즘 | 표본 | 결과 |
|---|---|---|---|
| on_delay (`output=LAMP`) | TON 5s | 129 | **AGREE** |
| star_delta (`delay_sec=2`) | TON 핸드오프 | 69 | **AGREE** |
| count_eject (`count=3`) | CTU 3 | 53 | **AGREE** |
| car_wash (`t1=t2=t3=1`) | 3× TON 체인 시퀀서 | 49 | **AGREE** |

전부 `mismatches=0`. 합 13 레시피 비트 단위 일치.

---

## 6. 재현 명령

```bash
# 1) 실 OpenPLC v3 기동
docker run -d --name openplc -p 8080:8080 -p 5502:502 dainok/openplc:latest

# 2) 적재+구동+차분 (조합 레시피)
source .venv/bin/activate
OPENPLC_HOST=127.0.0.1 OPENPLC_PORT=5502 \
  python scripts/openplc_live_diff.py motor_start_stop      # → RESULT: PASS

# 3) 타이머/카운터 (예약어/시간 답변 덮어쓰기)
OPENPLC_HOST=127.0.0.1 OPENPLC_PORT=5502 OPENPLC_ANSWERS="output=LAMP" \
  python scripts/openplc_live_diff.py on_delay              # → RESULT: PASS
OPENPLC_HOST=127.0.0.1 OPENPLC_PORT=5502 OPENPLC_ANSWERS="count=3" \
  python scripts/openplc_live_diff.py count_eject           # → RESULT: PASS

# 4) 통합 테스트 (CI 는 OPENPLC_HOST 없으면 깨끗이 스킵)
OPENPLC_HOST=127.0.0.1 OPENPLC_PORT=5502 pytest -q tests/test_openplc_live.py

# 5) 정리
docker rm -f openplc
```

환경변수: `OPENPLC_HOST`(필수 진입), `OPENPLC_PORT`(기본 502), `OPENPLC_WEB`
(기본 `http://{host}:8080`), `OPENPLC_USER`/`OPENPLC_PASS`(기본 openplc),
`OPENPLC_UNIT`(기본 1), `OPENPLC_RECIPE`, `OPENPLC_ANSWERS`(`k=v,k=v`),
`OPENPLC_SKIP_LOAD=1`(기존 실행 검증).

`OPENPLC_HOST` 가 *임의의* OpenPLC 인스턴스(도커/RPi/SL-RP4/원격)를 가리켜도
동일하게 동작한다 — 이것이 "어떤 OpenPLC 에도 재검증 가능한 명령"이다.

---

## 7. 남은 캐비엇 (정직)
- **합성기 카운터 파라미터(`RESET`→`R`)** 는 적재기가 우회 중. 표준 IEC 적재 신뢰성을
  위해 `app/` 본체 수정 필요(리드, §4.2).
- 본 검증은 OpenPLC **v3**(GPL, EOL). v4(MIT) 슬레이브 :502 도 동일 어댑터로 동작할
  것이나 공개 이미지가 없어 미검증(소스 빌드 시 후속). 적재만 REST :8443 로 다름.
- 표본화는 비동기 실 PLC 를 코스 그리드로 관측하므로, 타이밍 레시피는 step 을 스캔
  주기(50ms)에 맞춰야 비트 단위. 더 빠른 스캔/지터 큰 환경은 step 재튜닝 필요.
- E-stop/안전은 여전히 소프트웨어 밖 하드와이어 책임(OpenPLC 비인증).

## Sources / 실측 근거
- OpenPLC v3 슬레이브 Modbus 매핑: `core/modbus.cpp` (`bool_input` 읽기전용 /
  `bool_output` 코일 R/W) — 컨테이너 내부 실측.
- 비트주소 `b*8+c`: `core/LOCATED_VARIABLES.h` 글루 실측.
- 컴파일 파이프라인: `webserver/scripts/compile_program.sh` (`iec2c` → g++).
- 적재 엔드포인트: `webserver/webserver.py` (`/upload-program`,
  `/upload-program-action`, `/compile-program`, `/compilation-logs`, `/start_plc`).
