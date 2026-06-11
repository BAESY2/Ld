# OpenPLC 심층 분석 + 한국식 요리 전략 (BNS ROBO)

> 결론 요약: OpenPLC **v4(MIT)** 를 *프로세스 경계 너머* 무료 IEC 런타임으로 쓰되
> 세 역할(검증 오라클 · 무료 가상시운전 샌드박스 · SMB용 임베드 소프트PLC)에 한정.
> 우리의 가치(한국어 NL 합성 · 정형검증 · 안전커널 · **LS XGT/FEnet 네이티브**)는
> 전부 우리 쪽(독점)에 둔다. XGK 검증은 OpenPLC가 못 하므로 **우리 XGK 인터프리터**로.

## 0. 두 갈래의 정합 (XGK vs OpenPLC)
- **XGK 고객** → 우리 **자체 XGK 니모닉 스캔 인터프리터**가 검증(OpenPLC 무관 — LS 니모닉 미지원).
- **XGI/IEC · 가상시운전 · LS 없는 SMB** → **OpenPLC v4** 가 오라클/샌드박스/소프트PLC.
이 둘은 경쟁이 아니라 **상보적**. 1차 타겟은 XGK(확정).

## 1. 아키텍처: v3 vs v4
공통 스캔모델: `입력 읽기 → 로직 실행 → 출력 갱신` 루프. 컴파일 파이프라인 핵심 =
**MatIEC**(`iec2c`, flex→bison→의미분석→ANSI-C) → gcc → 런타임 글루 링크. **HAL**로
보드 독립(RPi/Arduino/ESP32/blank Linux 소프트PLC).

- **v3** (`thiagoralves/OpenPLC_v3`, **GPL-3.0, EOL**): 모놀리식(Flask UI + C 런타임 +
  MatIEC), Modbus master/slave·DNP3·EtherNet/IP, SQLite, 내부 Modbus 슬레이브 :502.
- **v4** (`Autonomy-Logic/openplc-runtime`, **MIT**): 헤드리스 2-프로세스 — Flask REST
  **:8443**(업로드/컴파일/실행 제어) + **SCHED_FIFO 실시간 런타임 프로세스**, IPC=유닉스
  소켓. 운영 UI 없음(Editor가 REST로 제어). JWT/TLS/PBKDF2 보안, CMake로 공유라이브러리
  빌드. **언어는 여전히 C/C++**(Rust/Go 아님), 새 부분이 Python/Flask+CMake.

> 우리 어댑터는 Modbus 슬레이브 :502를 쓰므로 **버전 무관**. 프로그램 적재만 v3(Flask form)
> vs v4(REST :8443)로 다름 — `connect_openplc()` seam이 이미 분리해 둠.

## 2. OpenPLC의 진짜 강점(해자)
1. **MatIEC 기반 진짜 IEC 61131-3 준수** — 장난감 인터프리터가 아닌 실제 컴파일러. 복제 난도 최상.
2. **$0 소프트PLC** — 무료·합법 IEC 런타임. 우리에겐 무료 *오라클* + 무료 *샌드박스*.
3. **저렴한 광범위 하드웨어** — RPi/Arduino/ESP32 → 물리 데모 ~$50.
4. **멀티 프로토콜** — Modbus master+slave, DNP3, EtherNet/IP, EtherCAT, Snap7.
5. **오픈소스 + v4 MIT** — 상업제품에 합법 래핑/임베드 가능.
6. **OSS ICS 연구·교육 사실상 표준** — 2014년 "사이버보안 연구용 최초 IEC 오픈 컨트롤러".
   학술 테스트베드/허니팟/디지털트윈 다수 → "이거 진짜냐?" 신뢰도 리스크 0.

## 3. 약점/공백 (우리 기회)
1. **stock Linux 경실시간 보장 없음** — v4도 PREEMPT-RT 필요(메카피온 모션엔 치명적).
2. **안전 인증 없음** — SIL/PLe 미인증 → 방호/E-stop 안전 컨트롤러로 **법적으로 불가**.
   우리 **안전커널**이 *애플리케이션 레이어*에서 메우지만 *인증은 아님*(정직히).
3. **HMI/SCADA 약함** (v4는 운영 UI 아예 없음), **온라인 디버깅 약함**.
4. **한국 생태계 전무** — LS XGT/XGB(FEnet/Cnet) 네이티브 없음, 한국어 UI/문서 없음,
   KS/KOSHA 프레이밍 없음. Modbus가 LS와의 유일한 다리(그나마 *설정*).
5. **확장/엔터프라이즈 공백**(단일노드, HA/플릿관리 없음 — 유료 Edge Cloud).
6. **지원 모델 빈약** + **v3 EOL**.

## 4. 라이선스 현실 (법무 검토 포인트 — load-bearing)
| 구성요소 | 라이선스 |
|---|---|
| OpenPLC Runtime **v3** | **GPL-3.0** (EOL) |
| OpenPLC Runtime **v4** | **MIT** (2025 Autonomy-Logic) |
| OpenPLC Editor v4 | GPL-3.0 |
| MatIEC | GPL-3.0 (Beremiz는 IDE=GPL/Runtime=LGPL 분리) |

- **네트워크/서브프로세스로 v4 래핑 + 우리 엔진 독점 유지 → 합법(깨끗).** GPL엔 네트워크
  사용 조항 없음(그건 AGPL, OpenPLC 아님). 소켓 통신 = 집합/사용이지 링킹 아님. 우리
  `connect_openplc()`/Modbus 경계가 가장 안전한 자세.
- **v4 런타임 MIT** → 폐쇄제품에 **임베드·수정·배포 가능**(귀속표시만). → **v4 표준화 이유.**
- **MatIEC 생성C copyleft 뉘앙스** — FSF 입장: GPL 컴파일러 *사용*은 입출력에 GPL 안 옮김.
  단 Bison식으로 *자기 일부를 출력에 복사*하면 그 조각은 라이선스 따름(MatIEC `lib/` 글루가
  미해결). **실무 결론: 우리는 MatIEC/생성C를 재배포 안 함**(사용자 박스에서 OpenPLC가 내부
  컴파일) → copyleft 미부착. *번들 배포 시에만* 법무 사인오프.

**경계 요약:** 링킹(동일 주소공간)=오염 → v3/MatIEC 절대 링크 금지. 서브프로세스/네트워크=깨끗.
v4 런타임 MIT=자유 임베드. **결정론 합성/검증 엔진은 항상 프로세스 경계 우리 쪽에.**

## 5. 상업 선례
**Autonomy/Synergy Logic**(메인테이너): 오픈코어(무료) + 하드웨어(SL-RP4, UL인증 RPi4+
PREEMPT-RT) + 클라우드 SaaS(Edge Cloud 플릿/vPLC 오케스트레이션). v4 MIT 전환이 이 폐쇄가치를
가능케 함. SI/OEM은 저가 컨트롤러·물/에너지/교육 제품에 임베드. → **우리 레인 = 무료 런타임 위
독점 부가가치 레이어.**

## 6. 한국식 요리 — 우리가 얹는 것 (글로벌 OSS엔 없는)
1. **LS XGT/XGB 네이티브** — Modbus 설정주소(`%MX`/`%MW`) 이미 대응, 로드맵에 **FEnet :2004(PyXGT)**
   네이티브. OpenPLC는 전무 → 한국 해자.
2. **한국어 NL → 작동 PLC ("문과생도 공장 가동")** — 한국어 합성은 어떤 글로벌 OSS도 안 함.
3. **결정론 + 정형 증명**(Z3/k-귀납 + 차등트윈 + 이중코일금지/IEC타입/LS디바이스클래스) — OpenPLC는
   "실행"만, 우리는 "증명".
4. **안전커널의 KOSHA/ISO13849/산안법 프레이밍** — deny-by-default·fail-safe·인터락 dry-run·감사로그.
   *인증은 아님(정직)*, 그러나 감사가능한 런타임 강제 레이어 = OpenPLC 공백 정조준.
5. **메카피온 모션 + 뿌리산업(주조/금형/표면처리/용접) 패턴** — `app/patterns/library.py` 확장.

## 7. Build-vs-Wrap + 로드맵
- **Build(독점, GPL 절대 격리):** 한국어 NL→명세, 결정론 ST 합성, Z3/k-귀납 검증, 스캔 시뮬,
  안전커널, **LS XGT/FEnet 네이티브**, 패턴 라이브러리, **XGK 니모닉 검증 인터프리터**.
- **Wrap(OpenPLC v4 MIT):** IEC 실행 런타임(오라클 + 샌드박스 + 선택적 소프트PLC). MatIEC/IEC 런타임
  재구현 금지(수년치 작업을 무료로 얻음).

**3-스텝:**
1. **v4 오라클 경화(지금·XGI 경로):** v4 컨테이너에 ST를 REST :8443 적재, :502로 `run_differential`,
   `OPENPLC_HOST` 가드(CI 스킵). 산출물: "비트 단위 외부검증" 제품 주장 + `docs/` 증빙.
2. **vPLC 샌드박스 UX(Stage 2):** 한국어 NL→검증→v4 vPLC→트윈+안전커널 게이트를 프론트에 연결.
   신규 `app/twin/openplc_v4_loader.py`(REST 업로드).
3. **LS 네이티브 + 안전 프레이밍(Stage 3):** `app/comms/fenet_xgt.py`(:2004), KOSHA/13849 감사 export.
   여기서 LS 보유 고객은 OpenPLC를 떠난다 — OpenPLC는 진입로, LS-네이티브가 목적지.

## 8. 리스크/완화
| 리스크 | 완화 |
|---|---|
| GPL 오염 | v3/MatIEC 링크 금지, Modbus/REST 경계만, **v4(MIT) 표준화**. |
| MatIEC 생성C 모호성 | MatIEC/생성C 재배포 안 함(사용자 박스 컴파일). 번들 배포 시에만 법무. |
| 실시간/안전 책임 | 비인증 명시, 소프트PLC는 best-effort(PREEMPT-RT 요구), 안전커널=감사가능 위험저감(≠인증).
  실기 E-stop은 소프트웨어 밖 하드와이어 릴레이. |
| OpenPLC 로드맵 의존 | v4 MIT라 포크/자가유지 가능. 오라클/샌드박스로만 arm's length, 코어는 무의존. 알려진 v4 릴리스 pin. |
| v3 EOL | 전부 v4 가정으로 이전. v3는 레거시 Modbus 호환 타겟으로만. |

## Sources
- OpenPLC v3 (GPL, EOL): https://github.com/thiagoralves/OpenPLC_v3 · DeepWiki: https://deepwiki.com/thiagoralves/OpenPLC_v3
- OpenPLC v4 (MIT): https://github.com/Autonomy-Logic/openplc-runtime · LICENSE: https://raw.githubusercontent.com/Autonomy-Logic/openplc-runtime/main/LICENSE
- OpenPLC v4 제품/헤드리스/:8443: https://autonomylogic.com/runtime · https://autonomylogic.com/docs/2-1-openplc-runtime-overview/
- SL-RP4 (사업모델): https://autonomylogic.com/product/sl-rp4/
- MatIEC (GPLv3): https://directory.fsf.org/wiki/Matiec · Beremiz 라이선스 스레드: https://sourceforge.net/p/beremiz/mailman/beremiz-devel/thread/7607357.c4XKiqkX06@junk/
- GNU GPL FAQ(GPL 도구 출력/Bison 예외): https://www.gnu.org/licenses/gpl-faq.html
- OpenPLC 논문(Alves et al.): https://www.researchgate.net/publication/326542218
- PyXGT (LS, :2004): https://pypi.org/project/PyXGT
