# LS FEnet · Mitsubishi MELSEC(MC) 프로토콜 + OpenPLC v4 포크 브리프 (연구 종합)

> 상품화 핵심: 우리 박스가 **LS·미츠비시·Modbus 어느 PLC든 네이티브로** 말한다.
> 순수 stdlib 어댑터(`app/comms/`)로 구현 → 동시에 포크한 OpenPLC v4 C-HAL에
> 포팅할 레퍼런스. 모든 어댑터는 `PlcLink`(BOOL 심볼) 위에서 동작.
> ⚠️ 실배포 전 실제 CPU/GX Works·Wireshark로 첫 프레임 패킷 대조 필수(아래 주의).

## 1. Mitsubishi MELSEC — MC protocol / SLMP (3E 바이너리)
멀티바이트 **리틀엔디언**(서브헤더만 BE 관례 표기). TCP 포트 **고정 기본 없음**(개방설정,
흔히 5007/5000대) → 생성자 인자 필수.

**3E 요청 프레임:**
| 오프셋 | 바이트 | 필드 | 값 |
|---|---|---|---|
| 0 | 2 | 서브헤더 | `50 00`(요청)/`D0 00`(응답) |
| 2 | 1 | 네트워크No | `00` |
| 3 | 1 | PC No | `FF` |
| 4 | 2 | 요청대상 모듈 I/O | `FF 03`(=0x03FF, LE) |
| 6 | 1 | 멀티드롭 | `00` |
| 7 | 2 | 요청데이터길이(LE) | 모니터타이머~끝 바이트수 |
| 9 | 2 | 모니터링타이머(LE) | `10 00`(250ms 단위) |
| 11 | 2 | 명령(LE) | `01 04`(일괄read)/`01 14`(write) |
| 13 | 2 | 서브명령(LE) | `01 00`(비트)/`00 00`(워드) |
| 15 | 1 | 디바이스코드 | 표 참조 |
| 16 | 3 | 선두 디바이스번호(LE) | |
| 19 | 2 | 디바이스 점수(LE) | |

**디바이스 코드:** X=0x9C, Y=0x9D, M=0x90, L=0x92, F=0x93, V=0x94, B=0xA0, D=0xA8,
W=0xB4, SM=0x91, SD=0xA9, TS=0xC1/TC=0xC0/TN=0xC2, CS=0xC4/CC=0xC3/CN=0xC5, R=0xAF.
**번지수 진법:** X/Y/B/W/SB/SW/ZR = **16진**, M/L/D/T/C/R/SM/SD = **10진** (`X10`→16).
**비트 패킹:** 1점=1니블(2점/바이트, 짝수점=상위니블), Modbus의 LSB 8비트/바이트와 다름.
**예:** M0서 16비트 read `50 00 00 FF FF 03 00 0C 00 10 00 01 04 01 00 90 00 00 00 10 00`;
D100=1234 write `... 01 14 00 00 A8 64 00 00 01 00 D2 04`. 응답 end code≠0 → 에러.
**4E**=서브헤더 `54 00`+2바이트 시리얼(응답 echo, txn_id 역할). ASCII 모드=2배 바이트.

## 2. LS XGT/XGB FEnet 전용 프로토콜 (TCP **2004**)
**헤더·명령블록 모두 LE(리틀엔디언)** — 정정: 초판은 "헤더 BE"라 잘못 적었으나,
LS 공식 매뉴얼(XBL-EMTA V1.5 Ch.5.2 요청프레임 바이트예시 `54 00 / 01 00 / 04 00`)
+ Wireshark dissector(xgb.lua `add_le`) + golanglsplc 가 **전 필드 LE**로 일치 확인.
(`tests/test_fenet_conformance.py` 가 바이트로 못박음.)

| 오프셋 | 크기 | 필드 | 값 |
|---|---|---|---|
| 0 | 8 | Company ID | `"LSIS-XGT"` |
| 13 | 1 | Source of Frame | 0x33(요청)/0x11(응답) |
| 14 | 2 | Invoke ID(LE) | 응답 echo(txn id) |
| 16 | 2 | Length(LE) | 명령블록 바이트수 |
| 19 | 1 | BCC | TCP선 대개 무시(0) |
| 20 | 2 | Command(LE) | 0x0054 read-req/0x0055 resp/0x0058 write-req/0x0059 resp |
| 22 | 2 | Data type(LE) | 0x0000 bit/0x0002 word/0x0014 연속 |
| 26 | 2 | Block count(LE) | 변수 블록수(1..16) |
| 28 | 2 | Var-name len(LE) | |
| 30 | N | Var name | ASCII `"%MW100"`/`"%MX0"` (≤16) |

**예:** `%MX0` 비트 read instr `54 00 00 00 00 00 01 00 04 00 25 4D 58 30`(len=0x0E);
`%MW100=1` write instr `58 00 02 00 00 00 01 00 06 00 25 4D 57 31 30 30 01 00`(len=0x12).
**XGK vs XGI:** 와이어 프레임 동일, **디바이스 이름체계만 다름**. XGI=IEC(`%MX/%MW/%IX/%QX`),
XGK=LS 디바이스(P/M/K/F/T/C/D/L/N/R…, 워드-비트 별칭 `M0010`워드/`M001A`비트). →
XGK 타겟이면 주소 빌더가 **XGK 이름**을 내야 함(어댑터에 XGK/XGI 모드 플래그).

## 3. OpenPLC v4 HAL 커스텀 드라이버 (포크용)
v4(MIT) 드라이버: `core/src/drivers/`(C는 `native/`, Python은 `python/`), `plugins.conf`
등록, CMake 빌드. **플러그인 ABI:** `init/start_loop/stop_loop/cleanup` (+옵션
`cycle_start/cycle_end`). `plugin_runtime_args_t`가 프로세스 이미지 포인터 노출:
`bool_input/bool_output[byte][bit]`(%IX/%QX), `int_input/int_output`(%IW/%QW) 등.
→ **LS-FEnet/MELSEC 마스터 드라이버** = `cycle_start`에서 원격 PLC 일괄read→입력이미지,
`cycle_end`에서 출력이미지→일괄write. NULL 체크 필수. v3 콜백 HAL(`initializeHardware/
updateBuffersIn/Out/finalizeHardware` + `bufferLock`)도 호환 — `blank.cpp` 본떠 작성.
**리브랜딩(MIT):** CMake project명·버전배너·TLS CN·로고·LICENSE/NOTICE(상위 MIT 표기 유지+우리것 추가).
**금지:** Editor v4(GPLv3, Beremiz+MatIEC 번들)·MatIEC를 **링크/번들 금지**. Editor↔Runtime은
REST :8443 경계로만. 런타임 I/O는 Modbus :502.

## 4. Build 권고
1. **LS FEnet(:2004) 먼저** — 1차 시장·OpenPLC 사각지대·프레임 단순. `app/comms/fenet_xgt.py`.
2. **MELSEC 3E 둘째** — `app/comms/melsec.py`. (구현 완료)
3. `modbus_tcp.py` 스타일 그대로: stdlib만, 목서버로 CI, `PlcLink`, `WriteRejected`, invoke/serial=txn.
4. Python이 바이트를 *증명*, C HAL은 스캔루프에서 *수행*만.

**정직한 비용:** C 포크 영구 머지·CMake/ARM 크로스컴파일 / stock Linux 비실시간(PREEMPT-RT 필요,
모션 부적합) / **SIL·PLe 미인증**(안전커널=감사가능 위험저감≠인증, 실 E-stop은 하드와이어).
**엔디언:** MELSEC 전부 LE / **FEnet 도 전부 LE**(헤더 포함; 초판 BE 표기는 오류, 정정됨).

## Sources
- MELSEC MC Ref (SH-080008): https://dl.mitsubishielectric.com/dl/fa/document/manual/plc/sh080008/sh080008ab.pdf
- SLMP Ref (SH-080956): https://dl.mitsubishielectric.com/dl/fa/document/manual/plc/sh080956eng/sh080956engl.pdf
- pymcprotocol: https://github.com/senrust/pymcprotocol · s-pms/melsec_mc_net: https://github.com/s-pms/melsec_mc_net
- MC 3E 예제(LinuxTut): https://www.linuxtut.com/en/78814da5756de76f1a77/
- LS XGT FEnet 매뉴얼 V2.30: https://www.ls-electric.com/upload/customer/download/f8a96bfb-6212-4a0f-8d07-a1ba8868240f/User's%20Manual_XGT%20FEnet_V2.30.pdf
- Pro-face LS XGT 드라이버: https://www.pro-face.com/otasuke/files/manual/gpproex/v3_10/device/data/ls_xgte.pdf
- golanglsplc(헤더 오프셋): https://github.com/song9063/golanglsplc/blob/main/lsplc.go
- OpenPLC v4 드라이버 README: https://github.com/Autonomy-Logic/openplc-runtime/blob/main/core/src/drivers/README.md
- OpenPLC v3 blank.cpp HAL: https://github.com/thiagoralves/OpenPLC_v3/blob/master/webserver/core/hardware_layers/blank.cpp

> 주의(확실성): 미쓰비시 PDF는 FlateDecode로 직접 디코드 불가 → 3개 독립 구현 교차검증.
> LS 오프셋은 golanglsplc+Pro-face 기반. **실 CPU/Wireshark 패킷 대조 후 출하.**
