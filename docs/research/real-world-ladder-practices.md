# 실무 래더 로직 작성·사용 실태 조사 (그리고 우리 도구와의 갭)

> 목적: 우리 골든셋(모터 자기유지·컨베이어 정역 등)은 **교과서 예제**라 실무엔 그대로 못 쓰는 경우가 많다.
> 현업에서 래더를 실제로 어떻게 짜고 쓰는지 조사해, 자연어→래더 도구를 현실에 맞게 교정한다.
> 방법: 5개 각도 웹 리서치(병렬 에이전트) → 교차검증 → 종합. 출처는 각 항목에 표기.

---

## 0. 한 줄 결론

우리 **결정론 코어의 방향(이중코일 기계적 제거 · 인터락 검증 · 검증 통과분만 학습)은 실무 통념과 정확히 일치**한다.
그러나 실무 유용성을 막는 **3대 갭**이 있다:

1. **출력 포맷** — 실무는 "래더 JSON"을 안 쓴다. 벤더 IDE(XG5000/GX Works3/TIA/Studio 5000)에서 **컴파일·임포트되는 코드**여야 한다.
2. **골든셋 현실성** — 교과서 예제(자기유지/정역)뿐. 실무는 정수 스텝 레지스터 시퀀서, first-out 알람, 디바운스, 모드(자동/수동/조그), MCR 존, fail-safe NC 정지 등으로 돌아간다.
3. **안전 경계** — 표준 래더의 소프트 인터락은 **안전 시스템이 아니다.** E-stop은 하드와이어 안전릴레이로 전원을 끊어야 한다. "검증"이 안전을 보장한다고 오해되면 위험하다.

---

## 1. 실무에서 래더를 실제로 어떻게 짜는가 (교과서를 넘어선 패턴)

### 1-1. 자기유지(seal-in) vs 래치(SET/RESET) — 현업 최대 논쟁
- **핵심 기준은 "전원 차단 시 상태 유지 여부"다.** OTE(일반 코일)는 프리스캔(재시작/정전)에서 OFF로 리셋되지만, OTL/OTU(래치/언래치)는 프리스캔에서 아무것도 안 해 **정전 후에도 상태가 유지**된다.
  출처: contactandcoil.com — when-to-use-a-sealed-coil-vs-a-latchunlatch
- **실무 룰**: 정전 후에도 켜져 있어야 하는 경우에만 래치를 쓴다. 모션 같은 순간 명령은 자기유지(정전 시 꺼짐)가 맞다. 경험 많은 엔지니어는 스캔순서 의존성 때문에 래치를 **기피**하고, 초보가 남용한다.
  출처: contactandcoil.com; industrialmonitordirect.com — plc-latching-logic-setreset-vs-seal-circuits
- 래치/언래치는 **인접 rung**에 붙여 둔다. 같은 비트에 OTE+OTU 혼용은 "다음 프로그래머를 위한 함정"이고 SW가 경고를 띄운다.
  출처: contactandcoil.com
- **set-dominant vs reset-dominant**: 동시 조건일 때 어느 쪽이 이기는지를 평가 순서로 결정한다. E-stop 우세(estop_dominant)는 우리 골든셋에도 이미 있음.
  출처: contactandcoil.com — setreset

### 1-2. Start/Stop 회로의 fail-safe 설계
- **Stop 버튼은 NC(상시닫힘) 접점**으로 배선해, 단선/정전 시 "정지 누른 것처럼" 동작하게 한다(페일세이프).
  출처: contactandcoil.com — startstop-circuit
- 표준 seal-in 회로는 **stop-dominant**로 설계한다(동시 입력 시 정지 우선; NO 접점이 용착될 수 있으므로).
  출처: contactandcoil.com

### 1-3. 상태 시퀀싱 — 실무는 "정수 스텝 레지스터"
- 많은 현업 프로그래머가 스텝마다 비트 하나가 아니라 **정수 스텝 레지스터 1개**로 상태머신을 구현한다. 각 상태 동작은 `EQU(현재스텝 = N)`로 게이팅하고, `증가` 또는 `MOV`로 스텝을 전이한다.
  출처: solisplc.com — programming-a-state-machine-in-ladder-logic; control.com — state-machine-programming-in-ladder-logic
- 장점: 한 번에 한 상태만 활성 → 막힌 스텝/누락 전이를 현재 스텝 값으로 즉시 진단. **래더로 state machine을 비트 코일로 짜면 "스파게티"가 되기 쉽다.**
  출처: solisplc.com

### 1-4. First-out(최초고장) 알람 — 실무 표준 패턴
- 캐스케이드로 알람이 쏟아질 때 **어느 고장이 먼저 났는지** 식별. 첫 알람을 seal-in하고 나머지를 seal-out.
  출처: plctalk.net — first-out-alarm-sequence
- 전형 구현: 고장 레지스터 + `EQU(레지스터=0)`로 게이팅된 `MOV`로 고유 고장 ID 저장 → 한 번 잡히면 0이 아니라 이후 고장이 덮어쓰지 못함.
  출처: solisplc.com — plc-alarm-programming-advanced-alarm-capturing
- 동작: 첫 알람=경음기+빠른 점멸, 후속=느린 점멸, ACK=경음기만 끔(램프는 계속 점멸).
  출처: plctalk.net

### 1-5. 디바운스·원샷·초기화
- **디바운스**: TON(진짜 ON 확인)+TOF(진짜 OFF 확인) 이중 타이머. 입력은 (1) 기계적 접점 바운스, (2) 개방 시 아크 진동, (3) 전자기 노이즈 3가지로 떤다.
  출처: contactandcoil.com — debounce
- **원샷(ONS/OSR)**: 상승엣지에서 정확히 1스캔만 TRUE. RUN 진입 시 이미 조건이 TRUE면 안 터질 수 있어 **first-scan 비트(S:FS)**로 초기화를 처리.
  출처: solisplc.com — ons-instruction
- **타이머 3종**: TON(ON 지연), TOF(OFF 지연/런온·쿨다운), TP(고정폭 펄스).
  출처: instrumentationtools.com — iec-timers-ton-tof-tp

### 1-6. 실무 코드 규모·구조
- **MCR(마스터 컨트롤 릴레이) 존**: 조건이 false면 존 내 모든 코일을 강제 OFF. 단, 존은 조건과 무관하게 항상 스캔(JSR과 다름), 존으로 JMP 점프 금지.
  출처: industrialmonitordirect.com — mcr-instruction; twcontrols.com
- **Main은 얇다**: 대형 프로젝트의 Main 루틴은 사실상 JSR로 다른 루틴들을 스캔당 1회씩 호출만 한다.
  출처: twcontrols.com
- 현업은 이름 붙은 **패턴 카탈로그**를 공유한다: Sealed-in Coil, State/Fault Coil, Start/Stop, Set/Reset, Flasher, Input Map, Step, Mission, Five Rung, Mode.
  출처: contactandcoil.com — patterns-of-ladder-logic-programming

---

## 2. 프로그램 구조화·표준·언어 선택

- **IEC 61131-3**: 5개 언어(LD/FBD/ST/SFC/IL). IL은 3판(2013) 폐기 예고 → 4판(2025) 완전 삭제. POU 3종(Program/Function/Function Block).
  출처: en.wikipedia.org/wiki/IEC_61131-3
- **언어 선택은 작업 성격 + "유지보수 인력"으로 결정**: LD는 이산/불리언 기계로직(현장 보전 전기공이 읽기 쉬움), ST는 수식/반복/문자열, SFC는 순차/배치, FBD는 PID/모션/아날로그. "새벽 2시 트러블슈팅 때 ST 성능보다 래더 가독성이 이긴다."
  출처: industrialmonitordirect.com — iec-61131-3 language selection; structured-text-vs-ladder
- 래더는 여전히 PLC 프로그래밍 시장 ~47%로 1위.
  출처: coherentmarketinsights.com — plc-market
- **태그/심볼 네이밍**: 생주소가 아닌 **서술적 심볼 태그**. 계측은 ISA-5.1(첫 글자=측정변수 F/T/P, 후속=기능 I/T)로 P&ID와 추적 가능하게(예 `20-FT-1982-A`). Rockwell은 controller-scope vs program-scope + UDT, Siemens TIA는 **심볼릭 어드레싱 권장**(변수 삽입 시 절대주소 밀림 방지), S7-1200/1500 optimized DB는 심볼릭 전용.
  출처: isa.org; ace-net.com; control.com — plc-tags-scope; maplesystems.com; flowfuse.com
- **PLCopen 코딩 가이드라인(2016)**: 63개 규칙(네이밍/주석/코딩관행/언어/벤더확장).
  출처: automation.com — plcopen-coding-guidelines
- **모듈화**: 500 rung 넘으면 머신 스테이션/영역별 서브루틴 분할, 재사용 AOI/FB.
  출처: industrialmonitordirect.com — routine-and-subroutine-organization

---

## 3. 툴·워크플로 (한국/아시아 포함)

- **핵심 디버깅 흐름**: 오프라인 작성 → 다운로드 → **온라인/모니터 모드**에서 라이브 rung 전력흐름(에너자이즈=초록 하이라이트) → **크로스레퍼런스**(Studio 5000 `Ctrl+E`)로 태그 추적 → **I/O 강제(force)**로 시운전 → **스테이지드 온라인 편집**(Accept→Test→Finalize).
  출처: industrialmonitordirect.com — green-bar-status; control.com — cpu-modes; automationreadypanels.com; justanswer
- **강제(force) 위험**: 출력 강제는 액추에이터를 직접 구동하고 래더 인터락을 우회 → 회전기기 주변에선 위험, LOTO 필요, 명시적 해제 전까지 유지.
  출처: industrialmonitordirect.com — io-forcing-safety
- **벤더 지형**: Studio 5000(Rockwell/AB, 북미 지배) · TIA Portal(Siemens, 유럽 1위) · GX Works3(미쓰비시 iQ-R/FX5; GX Works2=레거시 FX/Q, **프로젝트 직접 호환 안 됨, 재설계 필요**) · **XG5000(LS일렉트릭 XGT, 한국)**.
  출처: controlsystemguide.com; plcprogramming.io; supplc.com; linkedin/lselectric
- **한국 시장**: PLC는 한국 FA 시장의 25.7%(2024), 시장 규모 ~$9.7B(2026). LS일렉트릭(구 LS산전)은 한국 FA 핵심 플레이어, 미쓰비시는 2025.2 창원 현지생산 시작. 글로벌 top5(Siemens/Rockwell/Mitsubishi/Schneider/ABB)가 ~77%.
  출처: mordorintelligence.com — south-korea-factory-automation; plc-market
- **주석은 필수**: 실무 래더는 rung 주석·태그 설명이 빽빽하다. 로직만으로는 난해해서 크로스레퍼런스·주석 없이는 추적 불가.
  출처: plc.company — cross-reference-tool (커뮤니티 통념, 단일 영구링크는 미확보)

---

## 4. 안전 — 가장 중요한 현실 체크 ⚠️

- **표준 래더의 소프트웨어 인터락 ≠ 안전 시스템.** E-stop은 PLC가 읽고 판단하는 게 아니라, **안전릴레이를 통해 모터 접촉기로 전원을 직접 차단(하드와이어)**해야 한다. "크러시/절단/감전" 가능한 것에 PLC-only E-stop은 안전하지 않다.
  출처: plcprogramming.io — e-stop-safety-circuit; concepts/interlocks
- 소프트 인터락은 PLC 스캔에 의존 → CPU 손상/버그/변조 시 실패. 하드웨어 인터락은 PLC가 죽어도 유효.
  출처: linkedin — hardwired vs software interlock
- **표준 프레임워크**: ISO 13849(Performance Level a~e, 기계적), IEC 62061(SIL 1~3, 전기/전자/프로그래머블), IEC 60204-1, NFPA 79. PL d≈SIL 2, PL e≈SIL 3; Cat 3/4 = 이중채널+교차감시.
  출처: patsnap.com — sil-vs-pl; machinerysafety101.com
- **정지 카테고리**: Cat 0(즉시 전원차단, 비제어), Cat 1(제어 정지 후 전원차단). E-stop은 Cat 0/1만 허용(Cat 2 금지). NFPA 79는 E-stop 버튼에 self-latching 접점 요구.
  출처: machinerysafety101.com; controldesign.com
- **이중코일(double coil)** 메커니즘: 출력은 스캔 종료 후에만 갱신 → **마지막 rung이 이긴다(last-scan-wins)**, 페이지 위치 무관. 수정: 한 출력의 모든 조건을 1개 rung(OR 병렬+AND 직렬)에 모으거나 SET/RST 사용. → **우리 도구의 M-relay OR 병합 = 정석.**
  출처: industrialmonitordirect.com — double-coil-conflict; resolving-double-coil-gx-works3; contactandcoil — setreset
- **검증은 경험적**: 실무는 형식증명이 아니라 **고장 주입 테스트**(FAT: 필드신호 시뮬레이션으로 인터락/페일세이프 셧다운 확인, SAT: 실설치 환경 확인)로 인터락을 검증한다.
  출처: engineeringservice.net — fat-sat-commissioning

---

## 5. AI 자연어→PLC 생성의 현주소 & 갭

- **순정 LLM은 유효한 PLC 코드를 신뢰성 있게 못 만든다** — 잘못된 명령·벤더 의미를 환각. 외부 검증 툴 필수.
  출처: arxiv 2401.05443 (LLM4PLC)
- **LLM4PLC**: zero-shot 47% → one-shot+LoRA+문법검사기로 72% 통과(Code Llama 34B). MATIEC(IEC 61131-3 ST 컴파일러)+nuXmv 모델체커 피드백 루프. 전문가 정확도 평가 naive GPT-4 2.25/10 → 파이프라인 7.75/10. GPT-3.5 zero-shot ≈ 0%.
  출처: arxiv 2401.05443
- **Agents4PLC**: 형식검증 성공 easy 최대 68.8%(동일 GPT-4o로 LLM4PLC는 0% 검증가능), 문법 컴파일 easy/medium 100%.
  출처: arxiv 2410.14209
- **RAG의 결정적 효과(벤더 의미)**: 순정 LLM은 미쓰비시 `RTRIG_P` 상승엣지나 "변수 선언은 인라인 VAR가 아니라 외부 레이블 에디터에서" 같은 걸 모름. RAG 추가로 **GX Works3 ST 컴파일 성공 38% → 73~87%**.
  출처: arxiv 2511.09122
- **온프레미스 동기**: 산업 운영자는 클라우드 AI를 금지(운영정보 노출 우려) — 데이터보호/보안/품질 중요도 8.9/8.5/8.7. → **우리 LoRA/온프레미스 방향이 맞다.**
  출처: arxiv 2511.09122
- **래더(LD)는 특히 어렵다**: LLM이 SFC는 예제로 생성 가능하나 **"래더 다이어그램 자동 생성은 아주 단순한 경우에도 여전히 난제."** ChatGPT의 ASCII 래더 출력은 사실상 판독 불가.
  출처: arxiv 2410.15200; zipautomations.com
- **실무자 경고**: ChatGPT는 필요한 안전 인터락·고장모드·에러처리를 누락할 수 있어 엔지니어의 검증 필수.
  출처: zipautomations.com
- **상용 동향**: Siemens Engineering Copilot(TIA): 자연어→SCL/LAD/HMI/하드웨어구성 생성, 고객 표준 반영, 컴파일 에러 수정. Rockwell FactoryTalk Design Studio Copilot(Azure OpenAI): Logix 래더 생성. **단, 모두 "유자격 엔지니어 검증 필요한 어시스턴트"로 포지셔닝, SIL 2+ 안전로직 자율생성 아님.**
  출처: siemens.com — engineering-copilot; packworld.com; industrialmonitordirect.com — ai-code-generation-vendor-support
- **인증 갭**: IEC 61508(SIL)은 복잡한 ML에 부적합 → AI 생성 안전로직의 인증 공백.
  출처: hal.science/ineris-03500334

---

## 6. 우리 프로젝트 갭 분석 & 권고

### 6-1. 잘 맞는 것 (유지)
- **이중코일 M-relay OR 병합** = 실무 정석. ✅
- **검증 통과분만 LoRA 학습** = LLM4PLC의 "검증 게이트" 사상과 일치. ✅
- **온프레미스/벤더중립 LLM** = 산업현장 데이터보호 요구·연구 동향과 일치. ✅
- **라이브 웹 에디터(엔지니어가 보고 수정)** = 상용 코파일럿들의 "검증 가능한 어시스턴트" 포지셔닝과 일치. ✅
- **RAG 명령어 규격** = 벤더 의미 주입으로 컴파일률 38→87% 끌어올리는 핵심 레버. ✅ (단 코퍼스 빈약, §6-3)

### 6-2. 큰 갭 (우선순위 높음)
1. **벤더 IDE 임포트 포맷 부재** — 지금은 래더 JSON. 실무자는 이걸 못 쓴다. **XG5000/GX Works3가 임포트하는 포맷**(예: 미쓰비시 ST/IL, LS XGT 프로젝트, PLCopen XML)으로의 익스포트가 있어야 "실사용 가능"해진다. → 다음 마일스톤 1순위 후보.
2. **골든셋이 교과서** — 12개가 전부 단순 예제. 실무 패턴으로 교체/확장 필요(§6-4).
3. **안전 경계 명시 부재** — README/출력에 "이 도구의 검증은 논리 보조이며 안전기능(E-stop 등)은 ISO 13849/IEC 62061 하드와이어 안전회로로 별도 구현해야 함"을 **명문화**. 인터락 검증을 "안전 보장"으로 오해시키지 말 것.

### 6-3. 중간 갭
4. **시퀀싱 모델** — 우리 Sum-of-Products는 조합로직 위주. 실무 시퀀스는 **정수 스텝 레지스터(EQU/MOV)**가 표준. 스텝 시퀀서를 1급 패턴으로 모델링 필요(SFC→스텝 래더 변환).
5. **네이밍/태그** — 생주소(P0000) 대신 **서술적 심볼 + 주소 매핑 주석**을 기본 출력으로. ISA-5.1 스타일 옵션.
6. **주석 생성** — 실무 래더는 주석이 빽빽. rung별 자동 주석(조건→동작 요약)을 출력에 포함.

### 6-4. 골든셋 교체/확장 제안 (교과서 → 실무)
현행 12개에 더해 실무 패턴 케이스 추가:
- 정수 스텝 레지스터 **시퀀서**(예: 3스텝 충진→교반→배출, EQU/MOV 전이)
- **first-out 알람** 매트릭스(레지스터+EQU(=0) MOV 캡처)
- TON+TOF **디바운스**
- **모드 제어**(자동/수동/조그, 조그=모멘터리 유지)
- fail-safe **NC Stop** + stop-dominant seal-in
- **MCR 존**(영역 일괄 비상정지) — 단 "안전 아님" 주석 동반
- 런온/쿨다운 **TOF**(팬 애프터런 등)
- 재시작 **초기화**(first-scan 비트)
각 케이스에 {자연어, 기대 ST, 기대 래더, 금지조건(이중코일 0/인터락 0), 실무 출처} 메타 포함.

### 6-5. 권고 다음 단계 (택1로 시작)
- **A. 현실성 우선**: 골든셋을 실무 패턴 8~10개로 확장(§6-4) + 안전 경계 문구 명문화. (리스크 낮음, 즉시 신뢰도↑)
- **B. 실사용성 우선**: 벤더 임포트 포맷 익스포터 1종(우선순위: LS XG5000 또는 미쓰비시 GX Works3 ST). (임팩트 큼, 조사·검증 필요)
- **C. 정확도 우선**: 정수 스텝 시퀀서 모델 + SFC→스텝 래더 결정론 변환. (모델 작업, H2와 연계)

---

## 부록: 출처 신뢰도 메모
- **다중 교차검증된 핵심 주장**(이중코일 last-scan-wins, E-stop 하드와이어, LLM4PLC 수치, RAG 컴파일률, IEC 61131-3 언어): 독립 출처/복수 에이전트에서 일치 → 신뢰 높음.
- **단일/약한 출처**: plccopilot.com(403, 검색요약), arxiv 2305.15809·2410.15200(초록만), 일부 plctalk/control.com(직접 패치 차단) → 본문에 표기. 정책·수치 인용 시 원문 재확인 권장.
- 주석 관행(빽빽한 rung 주석)은 커뮤니티 통념으로 확립됐으나 단일 영구링크 미확보.
