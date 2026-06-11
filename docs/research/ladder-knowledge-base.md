# 래더 로직 지식베이스 (학습 종합)

> 웹의 교육·실무 자료(언어 불문: 영/한/일)를 수집·학습해 구조화한 문서.
> 목적: 자연어→래더 도구의 (a) RAG 코퍼스, (b) 골든셋, (c) 벤더 어댑터, (d) 분석 에이전트 프롬프트의 기반.
> 원칙: 매뉴얼 본문 복제 금지 — **사실 데이터(명령어명·디바이스 문자·주소 체계)+출처**만. 출처는 각 절 말미.

---

## 1. 래더 교육 커리큘럼 (표준 학습 순서)

전 세계 교재·대학 강의가 거의 동일한 순서를 따른다. 우리 골든셋·난이도 태깅의 기준으로 쓴다.

| 레벨 | 주제 | 도입 명령(AB/IEC) | 정규 예제 | core/adv |
|---|---|---|---|---|
| 0 | 스캔 사이클·전력레일 멘탈모델 | — | (개념) | core |
| 1 | 접점·코일 | XIC/XIO/OTE, `--\| \|-- --\|/\|-- --( )--` | 푸시버튼→램프 | core |
| 2 | 자기유지/seal-in·래치 | seal-in branch, OTL/OTU, S/R | **모터 기동/정지** (3단계로 교육) | core |
| 3 | 타이머 | TON/TOF/RTO/TP | 탱크충진 지연, 팬 런온(TOF), 가동시간(RTO) | core |
| 4 | 카운터 | CTU/CTD/CTUD + RES | 주차장 카운터 | core |
| 5 | 비교 | EQU/NEQ/GRT/GEQ/LES/LEQ/LIM | 레벨 설정점 제어 | core→int |
| 6 | 연산·데이터 이동 | MOV/ADD/SUB/MUL/DIV/CPT | 아날로그 스케일링·레시피 | int |
| 7 | 엣지/원샷 | ONS/OSR/OSF, R_TRIG/F_TRIG | 1회 트리거(버튼당 카운트) | int |
| 8 | 시퀀싱/상태머신 | SQO/SQI/SQL + 스텝 래치 | **신호등**, 배칭(충진→교반→배출) | adv |
| 9 | 프로그램 제어·구조 | JSR/SBR/RET, JMP/LBL, MCR, FOR | 재사용 모터 서브루틴 | adv |

**강사들이 공통 경고하는 4대 오개념**: ① 접점/코일=물리 I/O로 착각(실은 읽기/쓰기 명령, 출력비트도 접점으로 읽음) ② 스캔순서 무시 ③ 이중코일 ④ Stop은 NC(XIO)로 — 단선 시 정지(페일세이프).

> 출처: plcacademy.com/ladder-logic-tutorial; solisplc.com/tutorials/how-to-read-ladder-logic; control.com/textbook (LD); cdn.automationdirect.com PLC Handbook; ladderlogicworld.com/plc-timer; controlsystemguide.com/plc-counter; utoledo EECS-4220 syllabus.

---

## 2. 벤더 명령어셋·주소 체계 (RAG 핵심 데이터)

**가장 가치 높은 데이터.** 순정 LLM이 환각하는 부분이고, RAG로 주입 시 컴파일률 38→87%(GX Works3, arxiv 2511.09122).
**핵심 교훈: 주소 모델이 벤더마다 근본적으로 호환 불가** → 벤더중립 IR 후 어댑터로 렌더해야 함.

### 2-1. LS Electric XGK/XGB (XG5000) — 비트=16진, 워드=10진 · **한국 기본 타깃**
- 디바이스: **P**=I/O릴레이, **M**=보조(내부)릴레이, **K**=킵릴레이(유지), **L**=링크릴레이, **F**=시스템/플래그, **T**=타이머, **C**=카운터, **S**=스텝제어, **D**=데이터, **Z**=인덱스, **R**=파일, **U**=특수모듈
- 주소: 비트는 **16진** 비트위치(`M0000~M255F`, `K00000~K2559F` 끝자리 0~F = 16비트/워드). 워드/설정값은 10진(최대 hFFFF=65535).
- 접점/코일: `LOAD`=A접점(NO), `LOAD NOT`=B접점(NC), `OUT`=코일 / Set·Reset: `SET`,`RST`
- 원샷: `OUTP`(상승), `OUTN`(하강)
- 타이머: `TON`,`TOFF`,`TMR`(적산),`TMON`(단안정),`TRTG`(재트리거) — 10ms/100ms 베이스
- 카운터: `CTU`,`CTD`,`CTUD`,`CTR`(링)
- 주의: IEC 라인(XGI/XGR/XEC)은 위 디바이스레터 대신 IEC 61131-3 심볼릭 사용.

### 2-2. Mitsubishi MELSEC FX5/iQ-R (GX Works3) — **I/O는 8진**, 내부 10진 · 한일 다수
- 디바이스: **X**=입력, **Y**=출력, **M**=보조릴레이, **T**=타이머, **C**=카운터, **D**=데이터레지스터, **S**=스텝
- 주소 진법: **X/Y는 OCTAL**(X0~X177, 8·9 건너뜀), M/T/C/D/S는 10진(FX: D0~7999, S0~999)
- 접점/코일: `LD`/`LDI`(NO/NC), `OUT`=코일 / `SET`,`RST`
- 원샷: `PLS`(상승 1스캔), `PLF`(하강) / 엣지접점 `LDP`/`LDF` — PLS/PLF는 Y·M만 대상
- 타이머/카운터: `OUT T<n> K<preset>` / `OUT C<n> K<preset>` (K값에 시간베이스 적용); FX5엔 IEC TON FB도
- **핵심 10개 명령(현장 대부분 커버)**: LD/LDI/AND/ANI/OR/ORI/OUT/SET/RST/END (+PLS/PLF)

### 2-3. Siemens S7-1200/1500 LAD (TIA Portal) — **byte.bit 주소** · 유럽 1위
- 디바이스: **I**=입력PII, **Q**=출력PIQ, **M**=비트메모리, **DB**=데이터블록, **L**=temp
- 주소: 영역+크기(B/W/D)+**byte.bit**: `%I0.0~%I0.7`, `%MB10`,`%MW20`,`%MD30`,`%Q0.1`
- 접점/코일: NO/NC/코일 / Set·Reset 코일 `S`,`R`, SR/RS 플립플롭
- 원샷: `P`(상승엣지)/`N`(하강) 접점·코일
- 타이머: **IEC** `TON/TOF/TP/TONR` — 각자 인스턴스 DB 필요, `PT`=프리셋(TIME), `ET`=경과, `Q`=출력
- 카운터: IEC `CTU/CTD/CTUD`
- TIA는 **심볼릭 어드레싱 권장**(변수 삽입 시 절대주소 안 밀림), S7-1200/1500 optimized DB는 심볼릭 전용.

### 2-4. Omron CJ/CP/NX (Sysmac/CX-Programmer) — CIO+문자영역
- 디바이스: **CIO**=I/O&내부, **W**=워크, **H**=홀딩(유지), **A**=보조(시스템), **D/DM**=데이터메모리, **T**=타이머, **C**=카운터
- 접점/코일: `LD`/`LD NOT`, `OUT` / `SET`,`RSET`
- 원샷: `DIFU(013)`(상승 1사이클), `DIFD(014)`(하강)
- 타이머: `TIM`=**감산(카운트다운)** 온딜레이, 100ms 베이스, BCD #0000~#9999 / `TIMX`(바이너리 &0~65535) / `TIMH`,`TIMHX`(10ms)
- 카운터: `CNT`/`CNTX`, 리셋 `CNR`

### 2-5. Rockwell ControlLogix (Studio 5000) — **태그 기반, 고정주소 없음** · 북미 지배
- 모델: 명명 태그(BOOL/DINT/REAL/TIMER/COUNTER…), 디바이스레터·고정주소 없음
- 접점/코일: `XIC`(NO, bit=1 시 참), `XIO`(NC, bit=0 시 참), `OTE`(코일) / `OTL`,`OTU`
- 원샷: `ONS`,`OSR`,`OSF`
- 타이머: `TON/TOF/RTO`, 구조체 `.PRE/.ACC/.DN/.EN/.TT`, ms 단위 (DN: .ACC≥.PRE)
- 카운터: `CTU/CTD`, `.PRE/.ACC/.DN`

### 2-6. 벤더 차이 요약 (생성기가 절대 가정하면 안 되는 것)
| 축 | LS XGK | Mitsubishi FX | Siemens | Omron | Rockwell |
|---|---|---|---|---|---|
| 주소 | 16진 비트/10진 워드 | **8진 I/O**/10진 | byte.bit (B/W/D) | 채널.비트, 문자영역 | 태그(주소 없음) |
| 입력/출력 | **P 하나** | X/Y 분리 | I/Q | CIO | 태그 |
| 상승엣지 원샷 | `OUTP` | `PLS` | `P`접점 | `DIFU` | `OSR`/`ONS` |
| 온딜레이 타이머 | `TON`(증가) | `OUT T K`(증가) | IEC `TON`(증가) | `TIM`(**감산**) | `TON`(증가) |
| NO 접점 시작 | `LOAD` | `LD` | `--\| \|--` | `LD` | `XIC` |

> 출처: LS XGK/XGB Instructions Manual V2.2; MELSEC iQ-F FX5 Programming Manual; TIA Portal docs(memory/addressing, IEC timers); Omron SYSMAC CP W451; Rockwell 1756-RM003; automationdirect c-more(FX octal); plc.home.blog(PLS/PLF).

---

## 3. 한국어·일본어 현장 관행 (입력 이해의 핵심)

### 3-1. 결정적 통찰
- **한·일 사용자는 래더를 "코드"가 아니라 "그려진 릴레이 배선"으로 사고**한다. 자연어 입력이 불리언 식이 아니라 **물리 접점·동작**으로 들어온다: "누르면 붙고, 떼면 떨어진다". → 분석 에이전트는 이 멘탈모델을 전제해야 함.
- **자기유지(自己保持) 회로가 모든 것의 원자**: ① 기동조건(a접점) ② 자기유지 접점(코일 자신의 a접점) ③ 해제조건(b접점). 한·일 엔지니어는 "눌러서 시작, 계속 동작, 눌러서 정지"를 반사적으로 이 3원소로 분해.
- **안전은 b접점에 산다**: 정지·비상정지·인터록은 NC로, **자기유지 경로 자체를 끊도록** 배치(하류 코일만 끊으면 안 됨).
- **인터록 = 각 출력의 b접점을 상대 rung에**(정역 운전이 원형).
- 복잡 시퀀스는 자기유지 체인 대신 **스텝/상태 제어**(번호매김) 권장. SET/RST는 다중 스텝 동시활성 위험으로 주의.

### 3-2. 한↔영 용어 매핑 (분석 에이전트·UI용)
| 한국어 | English | 비고 |
|---|---|---|
| 자기유지(회로) | self-hold / seal-in | 가장 기초 회로 |
| 인터록 | interlock | 상호배제(b접점 교차) |
| 순차/시퀀스 제어 | sequential control | 래더 교육의 큰 틀 |
| a접점 | NO contact | `LD`(미쓰비시), LOAD(LS) |
| b접점 | NC contact | `LDI`; stop·E-stop·인터록 |
| 코일 | coil(OUT) | 이중코일 금지 |
| 내부/보조릴레이 | internal/aux relay | M |
| 킵릴레이 | keep relay | LS K(정전유지) |
| 타이머/카운터 | timer/counter | T/C |
| 정역 운전 | fwd/rev operation | 인터록 필수 |
| 비상정지 | emergency stop | NC로 자기유지 차단 |
| Y-Δ 기동 | star-delta start | 기동전류 저감 후 전환 |
| 스텝/상태 제어 | step/state control | 번호매김 상태머신 |
| 셋/리셋 | SET/RST | 래치 |
| 플리커/점멸 | flicker/flasher | 타이머 1~2개 |
| 원샷/펄스 | one-shot/pulse | PLS(상승)/PLF(하강) |
| 선입력/후입력 우선 | first/last-input priority | 자기유지 변형 |

> 출처: plckouza.com(自己保持·a/b접점); elec-tech.info(기본회로); plc-memo.com·control-career.com(미쓰비시 명령/인터록); LS XGK 초급 V21(P/M/K/L/F/S); datawizard.co.kr(a/b접점); insightforgelab.com(스텝제어); netpilgrim.net(XG5000 타이머 100ms).

---

## 4. 실무 예제 코퍼스 (골든셋 확장용 ~30종)

난이도·I/O·핵심패턴 포함. 각 케이스를 {자연어, 기대 spec, 기대 ST, 기대 래더, 금지조건(이중코일0/인터락0), 출처}로 인코딩.

**Basic**: ①모터 기동/정지 seal-in(2I/1O) ②정역+인터록(3I/2O) ③2버튼 선택 ④조그(seal-in 없음) ⑤AND램프(OR-of-AND) ⑥4센서 NOR ⑦교번 모터
**Timer/Counter**: ⑧스타델타(4I/3O+T, star↔delta NC인터록) ⑨온/오프딜레이 ⑩플래셔(2T 교차리셋) ⑪주기듀티 ⑫주차장 카운터(CTU/CTD 공유ACC, GEQ) ⑬물체 카운트+팩(CTU프리셋→RES)
**Sequencing**: ⑭병충진(센서정지→밸브seal-in) ⑮충진+캡(순차2T) ⑯탱크80%+히터 ⑰신호등(6스텝, 타이머ACC 비교) ⑱4거리 교차로 ⑲자동문(TOF홀드) ⑳세차(4스테이지T) ㉑컨베이어 분류(2광전) ㉒배칭(충진→교반→배출, 유량비교) ㉓4탱크 혼합 ㉔엘리베이터(층별래치+리밋)
**Process/Safety**: ㉕펌프 리드래그/듀티스탠바이(역할비트+런타임교번) ㉖수위 hi/lo(LO래치·HI언래치) ㉗first-out 알람(최초래치 락아웃, ACK/RESET, 빠른/느린점멸) ㉘E-stop처리(NC직렬+래치, 하드웨어안전릴레이 권장) ㉙자동/수동/조그 모드

**고급 5종 구조 스케치(패턴 레벨)**:
- **스타델타**: R1 MAIN(START∥MAIN seal·STOP NC·OL NC); R2 STAR(MAIN·T1 NC·DELTA NC); R3 TON T1; R4 DELTA(MAIN·T1.DN·STAR NC)
- **신호등**: 마스터 seal래치 → 자유진행 타이머체인 → ACC 비교로 6구간 → 각 구간이 해당 녹/황 구동, 적=NOT(자기 녹·황); 최종 T.DN→RES→반복
- **배칭**: START·TankEmpty→배치래치; 성분 i: 배치·(Flow_i<Target_i)→Inlet_i(LES로 닫힘); 전성분 도달=완료→교반; 배출
- **first-out**: 점 i: fault_i·NOT(이미최초) →FirstOut_i 래치(전역 락); any FirstOut→Horn; FirstOut_i→빠른점멸; 후속→느린점멸; ACK→Horn봉인; RESET→해소된 것만 언래치 (확장: 고장레지스터+MOV로 최초ID 저장)
- **리드래그**: 역할비트(Lead/LagA/LagB/Standby)+Last포인터; 수요단계화(압력/레벨 비교); 교번트리거(자정/런타임)→역할회전; 펌프출력=호출조건 OR

> 출처: instrumentationtools.com(예제색인·스타델타·신호등·세차·물체카운트); plcacademy.com/ladder-logic-examples; solisplc.com/tutorials/plc-programming-example(배칭); sanfoundry.com(주차장); corsosystems.com(리드래그); plctalk.net(first-out); electrical-engineering-portal.com(정역 인터록).

---

## 5. 래더 표현·교환 포맷 (출력 포맷 갭 해법)

| 포맷 | 타입 | 언어 | 벤더/툴 | 중립임포트? |
|---|---|---|---|---|
| **PLCopen XML (IEC 61131-10:2019)** | XML+xsd | LD/FBD/ST/IL/SFC 전체(+그래픽 배치) | CODESYS, Beckhoff, B&R, Beremiz, **OpenPLC Editor**, MULTIPROG | **YES**(단 서브셋) |
| Rockwell L5X | XML(텍스트) | LD/ST/FBD/SFC | Studio 5000 v20+/RSLogix v17+ | PARTIAL(벤더전용 XML) |
| Siemens TIA Openness | XML+.scl/.db/.udt | SCL/LAD/FBD/GRAPH | TIA v15+(Openness API) | PARTIAL |
| Mitsubishi GX Works3 | CSV(라벨/디바이스)+XML(HMI) | **로직 아님**(심볼만) | GX Works3 | NO(로직) |
| LS XG5000 | 바이너리+CSV(변수/주석) | **로직 아님**(심볼만) | XG5000 | NO(로직) |
| OpenPLC/Beremiz 프로젝트 | PLCopen XML | LD/FBD/ST/SFC/IL | OpenPLC/Beremiz | YES |
| matiec 출력(.st→.c) | 텍스트 | ST→C | matiec(OpenPLC/Beremiz 내장) | n/a(**컴파일 게이트**) |

### 권고
- **중립 익스포트 1순위 = PLCopen XML.** 유일한 ISO/IEC 표준 중립 포맷, LD 표현 가능, **OpenPLC Editor·CODESYS가 직접 임포트** → 무료 오픈에디터로 라운드트립 가능. 단 서브셋(벤더 FB·HW I/O맵·독자타입 미전송).
- 벤더 어댑터 2순위: **L5X(Rockwell), TIA Openness XML(Siemens)** — 둘 다 평문 XML이라 스크립트 가능. GX Works3·XG5000은 로직 중립포맷 없음 → 심볼 CSV만.
- **컴파일/검증 게이트(오픈소스, API키 불필요)**: **matiec**(ST→C 문법 게이트) + **nuXmv**(모델체커, 명세 대비 검증) = LLM4PLC 스택과 동일. 우리 CI(키 없이 통과) 규칙에 부합.

> 출처: en-standard.eu(IEC 61131-10:2019); plcopen.org TC6 XML doc; infosys.beckhoff.com(PLCopenXML import/export+서브셋); github.com/thiagoralves/OpenPLC_Editor; industrialmonitordirect(L5X); docs.tia.siemens.cloud(Openness); arxiv 2401.05443(matiec+nuXmv).

---

## 부록: 신뢰도 메모
- 벤더 명령어·디바이스 사실은 1차 매뉴얼(LS/미쓰비시/지멘스/옴론/Rockwell)에 다수 근거 → 신뢰 높음. 단 일부 2차 교육출처 인용분(Rockwell 비트의미, PLS/PLF 제약)은 1차 매뉴얼 재확인 권장.
- 일부 PDF(LS 한글, 일부 일본 교재)는 본 환경에서 텍스트 추출 실패 → 검색요약+병행 HTML로 교차확인.
- 직접 패치 차단(control.com 403, plcacademy 520) 항목은 복수 병행출처로 교차검증함.
