# Stage 3 — 실기/가상 PLC 직접제어 구현 브리프 (연구 종합)

> 자연어 → 검증 → 가상테스트 → **안전커널 → PLC**. 본 문서는 Modbus-TCP 와이어
> 스펙, OpenPLC 주소맵, LS XGT 매핑, 안전커널(런타임 강제) 설계를 1차 자료에서
> 종합한 구현 기준이다. 모든 어댑터는 `app/comms/protocols.py`의 `PlcLink`
> (BOOL 심볼 단위) 위에서 동작하며, 주소 매핑은 각 어댑터 내부 책임이다.

## 1. Modbus-TCP 와이어 프로토콜 (순수 stdlib 소켓)

**MBAP 헤더 — 7바이트, 빅엔디언, 모든 요청/응답 PDU 앞에 부착:**

| 필드 | 바이트 | 값 |
|---|---|---|
| Transaction ID | 2 | 클라가 정함, 서버가 echo (요청마다 증가, 응답에서 매칭) |
| Protocol ID | 2 | `0x0000` (Modbus/TCP 항상 0) |
| Length | 2 | 이 필드 *뒤* 전체 바이트수 = `1(unit) + len(PDU)` |
| Unit ID | 1 | 슬레이브 id (예 `0x01`) |

`struct.pack(">HHHB", txid, 0, len(pdu)+1, unit)`. CRC 없음(TCP가 무결성 보장). 포트 **502**.

**함수코드 (PDU = FC + data, 멀티바이트 빅엔디언):**
- **0x01 Read Coils** — req `01|start(2)|qty(2)`, resp `01|byteCount(1)|data`. 비트 **LSB-first**: `coil[i] = (data[i//8] >> (i%8)) & 1`.
- **0x02 Read Discrete Inputs** — 0x01과 동일 레이아웃, FC `02`, 읽기전용.
- **0x03/0x04 Read Holding/Input Registers** — `03|start(2)|qty(2)` → `03|bc(=2*qty)|regs(2B each)`.
- **0x05 Write Single Coil** — `05|addr(2)|value(2)`, value **`0xFF00`=ON / `0x0000`=OFF**. resp = 요청 echo.
- **0x0F Write Multiple Coils** — `0F|start(2)|qty(2)|bc(1)|data(LSB-first)` → resp `0F|start(2)|qty(2)`.
- **예외 응답** — `FC | 0x80` + 예외코드 1B (`01`불법함수 `02`불법주소 `03`불법값 `04`기기고장). 클라는 `resp_fc & 0x80` 감지 후 raise.

**예: 주소0에서 코일 8개 읽기 (unit1, txid1):**
```
req:  00 01 00 00 00 06 01 01 00 00 00 08
resp: 00 01 00 00 00 04 01 01 01 05   (코일 0,2 ON → 0b00000101=0x05)
```

## 2. OpenPLC 런타임 Modbus 주소맵 (권위)

내부 Modbus 서버(포트 **502**), 0-base PDU 주소(40001 오프셋 없음):

| IEC 변수 | Modbus 테이블 | FC | 주소 범위 |
|---|---|---|---|
| `%QX0.0–%QX99.7` | Coils(디지털 출력) | 읽기 0x01 / 쓰기 0x05,0x0F | **0–799** |
| `%IX0.0–%IX99.7` | Discrete Inputs(디지털 입력) | 0x02(읽기전용) | **0–799** |
| `%IW0–1023` | Input Registers | 0x04 | 0–1023 |
| `%QW0–1023` | Holding Registers | 0x03/0x06,0x10 | 0–1023 |
| `%MW0–1023` | Holding(메모리) | 0x03/0x10 | 1024–2047 |

**핵심 규칙:** 비트주소 `%QXb.c` → 코일번호 = **`b*8 + c`**. 즉 `%QX0.0→코일0`, `%QX1.0→코일8`. `%IX`도 동일. (마스터측 슬레이브 변수는 `%IX100.0/%QX100.0+` — 내부서버 구동엔 0–799 사용.)

프로그램 적재: `app/export/plcopen.py`의 PLCopen-XML ST POU → OpenPLC Editor 컴파일/업로드, 또는 v3 systemd 서비스가 부팅시 자동기동·실행상태에서 502 서빙. v4는 헤드리스 REST(:8443).

## 3. LS XGT/XGB FEnet

- **Modbus/TCP 지원: YES** (포트 502, 서버/슬레이브 설정 가능) → 우리 Modbus 어댑터가 실 LS PLC도 그대로 구동.
- **매핑은 고정 아님, 설정값**: FEnet Modbus-서버 설정에서 비트R/비트W/워드R/워드W 4개 base 주소를 LS 메모리(`%MX`,`%MW`)에 할당. 심볼의 Modbus 오프셋 = `(LS주소) − (설정 base)`. → 어댑터는 PLC별 base 설정을 심볼맵과 함께 저장해야 함(OpenPLC 0–799 하드코딩 금지).
- **릴레이 클래스**: P=입출력, M=내부릴레이(비트 `%MX`), D=데이터워드.
- **네이티브 FEnet(차기)**: XGT 전용 프로토콜 TCP **2004** (PyXGT 사용). 헤더(`"LSIS-XGT"`+invoke id+body len+checksum) + 명령블록(read/write, bit/word/dword, 변수명 `%MW100`).

## 4. 안전커널 — 쓰기 전 검증 게이트 (`app/comms/safety_kernel.py`)

**패턴(ACM TOPS 10.1145/3546579 + PLC 런타임 강제 arXiv 2105.10668):** 컨트롤러와
액추에이터 사이의 **보안 프록시 모니터**(Ligatti edit automata): 동작별 **suppress**
(불안전 출력 차단) / **correct**(안전값 대체) / **insert**(안전동작 자율 발행).
목표: 투명성·건전성 + **교착/발산 없음**. 핵심 — 설계시 검증은 필요하나 불충분,
**매 사이클 게이트에서 불변식 재검사 후 하드웨어로 전달**.

**모든 쓰기 전 체크리스트(deny-by-default):**
1. **화이트리스트** — 스펙에 있는 쓰기가능 심볼만. 미지/읽기전용 → 거부.
2. **타입/범위** — BOOL 유효성(워드는 INT/WORD 범위). 위반 → 거부.
3. **인터락 상호배제** — *결과 출력 이미지* 기준으로 상호배타 쌍 동시 ON이면 거부.
4. **상태머신 가드** — 현재 상태에서 합법인 쓰기인지(E-stop 래치중 start 금지 등).
5. **레이트리밋/디바운스** — 심볼별 최대 토글 빈도 초과 거부(채터링·명령폭주 방지).
6. **시뮬 dry-run(opt-in)** — 후보 쓰기를 `simulate()`에 적용해 결과 스캔에서 불변식
   위반 없는지 확인. `stop_dominates()`로 STOP/E-stop이 여전히 출력을 끄는지 확인.
7. **Fail-safe** — 어떤 불확실성(미지심볼·sim오류·링크오류·모니터예외)이든 **거부 +
   안전상태(출력 OFF)**. 절대 fail-open 금지.

순서: 싸고 결정론적인 1→5 먼저, 비싼 sim dry-run 6 마지막, 7은 catch-all `except`.

## 5. CI-안전 테스트 (하드웨어 없이)

- **순수 stdlib 인프로세스 Modbus-TCP 목서버**: `socketserver.ThreadingTCPServer` +
  dict 백엔드. MBAP 파싱→FC 디스패치→응답(txid echo, length 재계산). **포트 0**(임시)
  데몬 스레드, 픽스처 teardown에서 `shutdown()`. → MBAP echo·length·LSB 패킹·
  `0xFF00/0x0000`·`fc|0x80` 예외경로 검증.
- **안전커널 테스트**: 소켓 없이 가짜 `PlcLink`(쓰기 기록) + 커널 래핑 → 각 체크리스트
  위반에 `WriteRejected`, 합법 쓰기는 통과.
- **실 OpenPLC 차등 테스트**: `@pytest.mark.skipif(not os.environ.get("OPENPLC_HOST"))`
  로 env 가드 → CI는 스킵, 하드웨어 있을 때만 실연결.

## Sources
- Modbus org 공식 스펙: https://www.modbus.org/file/secure/modbusprotocolspecification.pdf
- Modbus 설명/예시: https://controllerstech.com/modbus-tcp-protocol-explained/ · https://en.wikipedia.org/wiki/Modbus
- OpenPLC Modbus slave 주소표: https://github.com/openplcproject/openplcproject.github.io/blob/master/reference/modbus-slave/index.md
- OpenPLC v3 Modbus 설정: https://deepwiki.com/thiagoralves/OpenPLC_v3/3.3-modbus-configuration
- OpenPLC runtime v4: https://github.com/Autonomy-Logic/openplc-runtime
- LS XBL-EMTA XGB FEnet 매뉴얼 V1.8 (Modbus 서버 주소영역)
- PyXGT (LS XGT/XGB, TCP 2004): https://pypi.org/project/PyXGT/
- ICS Security via Runtime Enforcement — ACM TOPS 10.1145/3546579
- Runtime Enforcement of PLCs — arXiv 2105.10668
- Framework for Runtime Safety of ICS through Runtime Verification — IEEE 10843382
- Python socketserver: https://docs.python.org/3/library/socketserver.html
