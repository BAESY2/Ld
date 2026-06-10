"""제조사별 PLC 에러코드 해결 지식베이스 — 연구·실무 인용 기반 확장판.

error_codes.py 의 수집 원칙을 그대로 따른다: 코드값/현상은 *사실 데이터*로 구조화하고,
원인·조치는 공식 문서와 실무자 공개 글을 *연구해 자체 작성*한다(본문 복제 금지),
근거가 된 공개 출처 URL 을 항목마다 남긴다. 숫자 코드가 시리즈마다 달라 단정할 수
없는 항목은 LED/플래그 기호(예: 'ERR-LED-BLINK')로 표기한다 — 틀린 숫자를 지어내지
않는 것이 원칙이다.

브랜드 목차: LS ELECTRIC(XGT/XGK/XGB) · MITSUBISHI(MELSEC FX/Q) · SIEMENS(S7) ·
OMRON(CJ/CP) · GENERIC(공통 진단 절차).
"""

from __future__ import annotations

from app.error_codes import ErrorCode, Vendor

# 출처 약칭(전 항목 공통 참조) — 공개 페이지만.
_SRC_LS_BATT = "https://ssq.ls-electric.com/kr/ko/community/qna/document/25825"
_SRC_LS_BATT_DOC = "https://ssq.ls-electric.com/uploads/document/17170266719520/PLC+기종별+배터리.pdf"
_SRC_LS_XGK = "https://sol.ls-electric.com/uploads/document/16572866006190/XGK+초급(V21).pdf"
_SRC_FX3U_MAN = "https://www.manualslib.com/manual/1234627/Mitsubishi-Fx3u-Series.html?page=261"
_SRC_MRPLC_6706 = "https://mrplc.com/forums/topic/32854-error-6706-mitsubishi-fx2n/"
_SRC_FX_TRBL = "https://infoneva.com/en/knowledge/dealing-with-mitsubishi-fx-plc-error-codes"
_SRC_S7_LED = "https://instrumentationtools.com/s7-300-led-errors/"
_SRC_S7_1200 = "https://jrmsolutions.net/siemens-s7-1200-error-red-light-blinking-solution/"
_SRC_S7_ALLLED = (
    "https://industrialmonitordirect.com/blogs/knowledgebase/"
    "siemens-s7-cpu-all-led-flashing-troubleshooting-guide"
)
_SRC_S7_AI = (
    "https://industrialmonitordirect.com/blogs/knowledgebase/"
    "siemens-s7-300-analog-module-sf-led-fault-troubleshooting"
)
_SRC_S7_DP = (
    "https://industrialmonitordirect.com/blogs/knowledgebase/"
    "siemens-s7-300-profibus-sfbf-led-diagnostics-and-configuration"
)


def _e(**kw: object) -> ErrorCode:
    kw.setdefault("license", "SELF_AUTHORED")
    return ErrorCode(**kw)  # type: ignore[arg-type]


KB_ENTRIES: list[ErrorCode] = [
    # ════════════════════════════════════════════════════════════════════════
    # LS ELECTRIC — XGT(XGK/XGB/XGI) 계열
    # 목차: 1.CPU/시스템 2.배터리/메모리 3.I/O 4.통신 5.LED 판독
    # ════════════════════════════════════════════════════════════════════════
    _e(vendor=Vendor.LS_ELECTRIC, series="XGT 공통", code="ERR-LED-ON",
       title="ERR LED 점등 — CPU 자기진단 에러(운전 정지급)",
       category="SYSTEM", severity="FATAL",
       likely_cause="자기진단에서 운전 불가 판정(워치독·모듈 구성 불일치·메모리 이상 등).",
       suggested_action="XG5000 접속 → [온라인]-[PLC 이력/에러 이력]에서 에러 코드·발생 시각을 "
       "먼저 읽는다(추측 금지). 이력의 코드로 원인 항목을 특정한 뒤 조치하고, 조치 후 "
       "에러 클리어→RUN 전환. 이력을 지우기 전에 반드시 캡처해 정비일지에 남길 것.",
       source_url=_SRC_LS_XGK, source_doc="XGK 초급 교재(공식 공개 PDF)",
       keywords=["ERR", "LED", "자기진단", "에러이력", "XG5000"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGT 공통", code="ERR-LED-BLINK",
       title="ERR LED 점멸 — 경에러(운전 지속 가능 경고)",
       category="SYSTEM", severity="WARNING",
       likely_cause="운전은 지속되지만 주의가 필요한 상태(배터리 저하·퓨즈 단선·일부 모듈 경고).",
       suggested_action="운전 중이라도 방치 금지. 에러 이력에서 경고 종류 확인 → 배터리/퓨즈류는 "
       "차기 PM(정기보전) 전이라도 즉시 교체 계획 수립. 경고 플래그(F 영역)를 HMI 에 "
       "알람으로 올려 두면 재발 시 즉시 인지 가능.",
       source_url=_SRC_LS_XGK, source_doc="XGK 초급 교재",
       keywords=["ERR", "점멸", "경고", "F플래그"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGT 공통", code="BAT-LED",
       title="BAT LED 점등 — 백업 배터리 전압 저하",
       category="POWER", severity="WARNING",
       likely_cause="CPU 백업 배터리(리튬) 수명 종료 임박 — 정전 시 래치 데이터·시계 소실 위험.",
       suggested_action="통전 상태에서 교체하면 데이터가 보존된다(정전 교체 시 래치 영역 소실 "
       "위험 — LS 공식 Q&A 절차). 교체 전 XG5000 으로 프로젝트/데이터 백업 필수. "
       "기종별 배터리 형번은 공식 '기종별 배터리' 문서로 확인 후 정품 사용.",
       source_url=_SRC_LS_BATT, source_doc="LS ssq Q&A: CPU 백업 배터리 교체방법",
       keywords=["배터리", "BAT", "래치", "백업", "교체"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGK", code="IO_PARAM_MISMATCH",
       title="I/O 파라미터 불일치 — 장착 모듈과 설정 모듈이 다름",
       category="IO", severity="FATAL",
       likely_cause="슬롯에 장착된 모듈 종류가 I/O 파라미터 설정과 다르거나, 모듈 교체 후 "
       "파라미터를 갱신하지 않음.",
       suggested_action="XG5000 [I/O 파라미터]에서 슬롯별 설정과 실장 모듈을 대조. 모듈을 "
       "바꿨다면 파라미터 재작성 후 쓰기. 베이스 증설 케이블 접촉 불량도 동일 증상을 "
       "내므로 케이블 재삽입 확인.",
       source_url=_SRC_LS_XGK, source_doc="XGK 초급 교재",
       keywords=["I/O", "파라미터", "모듈 불일치", "슬롯"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGT 공통", code="IO_DETACH",
       title="운전 중 모듈 착탈 감지 — CPU 정지",
       category="IO", severity="FATAL",
       likely_cause="운전 중 I/O 모듈이 빠졌거나(진동·베이스 록 풀림) 접점 산화로 착탈로 오인식.",
       suggested_action="모듈 록 레버·베이스 고정 나사 점검 후 재장착. 진동 심한 설비는 "
       "베이스 고정 보강. 재발 시 해당 슬롯 커넥터 청소(접점 세정제) 후 이력 클리어.",
       source_url=_SRC_LS_XGK, source_doc="XGK 초급 교재",
       keywords=["모듈 착탈", "탈락", "베이스", "정지"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGT 공통", code="SCAN_WDT",
       title="스캔 워치독 초과 — 연산 지연으로 CPU 정지",
       category="WATCHDOG", severity="FATAL",
       likely_cause="FOR/CALL 중첩·대량 통신 처리로 1스캔이 워치독 설정을 초과.",
       suggested_action="XG5000 [기본 파라미터]의 워치독 시간과 실제 최대 스캔타임(특수 "
       "릴레이로 모니터)을 비교. 무거운 연산은 분할 실행하거나 고정주기 태스크로 이동. "
       "워치독 값 상향은 원인 제거 후 최후 수단.",
       source_url=_SRC_LS_XGK, source_doc="XGK 초급 교재",
       keywords=["워치독", "스캔타임", "WDT", "정지"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGB/XGT Cnet", code="CNET_NO_RESP",
       title="Cnet(시리얼) 통신 무응답/타임아웃",
       category="COMM", severity="WARNING",
       likely_cause="국번·보레이트·패리티 불일치, RS-485 A/B 극성 반전, 종단저항 누락.",
       suggested_action="양단 파라미터(국번/속도/패리티/정지비트)를 표로 만들어 1:1 대조. "
       "485 라인은 A-A/B-B 결선·말단 종단저항(120Ω) 확인. 프레임 모니터 기능으로 "
       "요청/응답 프레임을 캡처하면 어느 쪽이 침묵하는지 즉시 갈린다.",
       source_url=_SRC_LS_XGK, source_doc="XGK 초급 교재",
       keywords=["Cnet", "RS485", "통신", "타임아웃", "국번"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGT FEnet", code="FENET_IP_DUP",
       title="FEnet(이더넷) 통신 두절 — IP 충돌/링크 다운",
       category="COMM", severity="WARNING",
       likely_cause="동일 네트워크에 IP 중복, 스위치 포트 불량, 케이블 단선.",
       suggested_action="모듈 LINK/ACT LED 로 물리 링크부터 확인 → arp/ping 으로 IP 중복 검사 "
       "(중복 시 한쪽 변경). 채널 점유 한계(동시 접속 수) 초과도 두절처럼 보이므로 "
       "접속 클라이언트 수를 확인.",
       source_url=_SRC_LS_XGK, source_doc="XGK 초급 교재",
       keywords=["FEnet", "이더넷", "IP 충돌", "LINK"]),

    # ════════════════════════════════════════════════════════════════════════
    # MITSUBISHI — MELSEC FX 계열 (에러는 D8060~D8067/D8438 에 저장, M806x 플래그)
    # 목차: 1.진단 체계 2.하드웨어 3.프로그램(67xx) 4.통신 5.실무 격리법
    # ════════════════════════════════════════════════════════════════════════
    _e(vendor=Vendor.MITSUBISHI, series="FX 공통", code="D8060-D8067",
       title="에러코드 저장 체계 — 특수 레지스터 D8060~D8067/D8438",
       category="SYSTEM", severity="INFO",
       likely_cause="(체계 설명) 에러 종류별로 다른 D 레지스터에 코드가 저장되고 대응 "
       "M8060~M8067 플래그가 선다.",
       suggested_action="GX Works2/3 [진단]-[PLC 진단]으로 현재/이력 에러를 읽는 것이 첫 "
       "단계. 래더에서 D8060~D8067 을 HMI 로 상시 표시해 두면 현장에서 코드부터 부른다 "
       "— 원격 지원이 한 단계 빨라지는 실무 팁.",
       source_url=_SRC_FX_TRBL, source_doc="FX 트러블슈팅 정리(공개 지식글)",
       keywords=["D8060", "M8060", "진단", "GX Works"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="M8060/D8060",
       title="I/O 구성 에러 — 미실장 I/O 번호를 프로그램이 참조",
       category="IO", severity="WARNING",
       likely_cause="증설 블록 탈락/미장착 상태에서 해당 X/Y 를 프로그램이 사용. D8060 값이 "
       "문제의 선두 I/O 번호를 가리킨다.",
       suggested_action="D8060 값으로 문제 디바이스 특정 → 증설 케이블·블록 전원(증설형은 "
       "별도 24V) 확인. 실제로 뺀 모듈이면 프로그램의 해당 X/Y 참조를 제거하거나 "
       "예비로 남길 거면 주석으로 명시.",
       source_url=_SRC_FX3U_MAN, source_doc="FX3U 사용자 매뉴얼 에러표(공개 열람)",
       keywords=["I/O 구성", "D8060", "증설", "미실장"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6101",
       title="RAM 에러 — CPU 메모리 자기진단 실패",
       category="SYSTEM", severity="FATAL",
       likely_cause="CPU RAM 불량 또는 강한 노이즈/순간정전으로 메모리 파손.",
       suggested_action="전원 재투입 후 재발 여부 확인 → 재발 시 프로그램 백업 후 메모리 "
       "올클리어·재전송. 그래도 반복되면 CPU 하드웨어 불량 — 본체 교체가 정답이며 "
       "노이즈 대책(전원 라인 필터·접지 분리)을 함께 검토.",
       source_url=_SRC_FX3U_MAN, source_doc="FX3U 에러표",
       keywords=["6101", "RAM", "메모리", "노이즈"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6105",
       title="워치독 타임아웃 — 스캔 200ms(기본) 초과",
       category="WATCHDOG", severity="FATAL",
       likely_cause="FOR~NEXT 대량 반복·CALL 깊은 중첩·고밀도 응용명령으로 스캔 폭증.",
       suggested_action="D8012(최대 스캔타임)를 확인해 실측으로 판단. 무거운 루프는 "
       "여러 스캔으로 분할(인덱스 이어달리기). D8000(워치독 설정) 상향은 원인 제거 "
       "후에만 — 무턱대고 올리면 폭주 시 정지 안전망이 사라진다.",
       source_url=_SRC_FX3U_MAN, source_doc="FX3U 에러표",
       keywords=["6105", "워치독", "D8012", "스캔"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6701",
       title="CJ/CALL 점프 대상 없음 — 라벨(P) 미존재",
       category="PROGRAM", severity="FATAL",
       likely_cause="CJ/CALL 이 가리키는 P 라벨이 삭제됐거나 번호가 바뀜(부분 수정 시 흔함).",
       suggested_action="크로스 레퍼런스로 모든 CJ/CALL→P 짝을 검사. 라벨 번호를 직접 치지 "
       "말고 GX Works 의 라벨 점프 기능으로 따라가며 빠진 짝을 복원.",
       source_url=_SRC_FX3U_MAN, source_doc="FX3U 에러표",
       keywords=["6701", "CJ", "CALL", "P 라벨"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6705",
       title="명령 피연산자 부적합 — 대상 디바이스 타입 불일치",
       category="PROGRAM", severity="FATAL",
       likely_cause="응용명령에 허용되지 않는 디바이스 종류를 지정(예: 워드 자리에 비트).",
       suggested_action="에러 스텝(D8069)으로 해당 명령을 특정 → 매뉴얼의 그 명령 '사용 "
       "가능 디바이스' 표와 대조해 교정. 라이브러리 복붙 코드에서 자주 발생.",
       source_url=_SRC_FX3U_MAN, source_doc="FX3U 에러표",
       keywords=["6705", "피연산자", "디바이스 타입"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6706",
       title="디바이스 범위 초과 — 인덱스(V/Z) 수식이 범위 밖을 가리킴",
       category="PROGRAM", severity="FATAL",
       likely_cause="V/Z 인덱스 값이 커져 D/M 의 실제 범위를 벗어난 접근(런타임에 발생, "
       "정지 상태에선 안 보임).",
       suggested_action="실무 검증된 절차(MrPLC 포럼 사례): 에러 시점의 V/Z 를 HMI/래더로 "
       "래치해 두고, 인덱스 사용처마다 상한 비교(CMP)로 가드 — '인덱스 가드 없는 "
       "간접참조는 시한폭탄'. 에러 스텝(D8069)으로 위치 특정 후 가드 삽입.",
       source_url=_SRC_MRPLC_6706, source_doc="MrPLC 포럼 — FX2N Error 6706 해결 스레드",
       keywords=["6706", "인덱스", "V", "Z", "범위 초과", "간접참조"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6707",
       title="파일 레지스터 미설정 접근",
       category="PROGRAM", severity="FATAL",
       likely_cause="파라미터에서 파일 레지스터 영역을 확보하지 않고 R/ER 영역을 접근.",
       suggested_action="PLC 파라미터의 메모리 용량 설정에서 파일 레지스터 블록 수를 확보 "
       "→ 쓰기 → 전원 재투입. 다른 현장 프로그램 이식 때 빠뜨리기 쉬운 항목.",
       source_url=_SRC_FX3U_MAN, source_doc="FX3U 에러표",
       keywords=["6707", "파일 레지스터", "파라미터"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6201-6205",
       title="통신(패리티/오버런/프레이밍) 에러 — 시리얼 품질 불량",
       category="COMM", severity="WARNING",
       likely_cause="보레이트/패리티 불일치, 케이블 길이 초과·노이즈, GND 루프.",
       suggested_action="양측 통신 포맷을 표로 1:1 대조 → 차폐 케이블·실드 편측 접지 적용. "
       "인버터 동력선과 통신선의 동일 덕트 배선이 단골 원인 — 배선 분리.",
       source_url=_SRC_FX_TRBL, source_doc="FX 트러블슈팅 정리",
       keywords=["통신", "패리티", "6201", "노이즈"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX/Q 공통", code="ISOLATE-MIN",
       title="실무 격리 진단법 — 최소 구성 기동",
       category="SYSTEM", severity="INFO",
       likely_cause="(절차) 증설/특수 모듈 다수 장착 시 어느 모듈이 원인인지 불명.",
       suggested_action="모든 증설·특수 모듈을 분리하고 베이스(본체)만으로 기동 → 정상이면 "
       "모듈을 하나씩 되붙이며 재현 지점을 찾는다. 비호환/구버전 펌웨어 모듈이 "
       "문서에 없는 에러를 내는 사례가 보고돼 있다(커뮤니티 검증 절차).",
       source_url="https://www.community.oxmaint.com/discussion-forum/troubleshooting-"
       "mitsubishi-fx-plc-melsec-fx2nc-64mt-dss-error-display-and-malfunction-fix",
       source_doc="Oxmaint 커뮤니티 — FX 시리즈 트러블슈팅 스레드",
       keywords=["격리", "최소 구성", "증설 모듈", "재현"]),

    # ════════════════════════════════════════════════════════════════════════
    # SIEMENS — S7-300/400/1200/1500
    # 목차: 1.LED 판독 2.진단버퍼 절차 3.OB 누락 4.메모리카드 5.통신(DP/PN) 6.아날로그
    # ════════════════════════════════════════════════════════════════════════
    _e(vendor=Vendor.SIEMENS, series="S7-300/400", code="SF-LED",
       title="SF(System Fault) LED 점등 — 시스템 폴트 총괄 표시",
       category="SYSTEM", severity="FATAL",
       likely_cause="하드웨어 고장·펌웨어 이상·프로그래밍/파라미터 오류·연산 오류·I/O 폴트 "
       "중 하나 — LED 만으로는 특정 불가.",
       suggested_action="추측하지 말고 진단버퍼부터: TIA Portal/Step7 [Online & Diagnostics] "
       "→ [Diagnostic Buffer]. 타임스탬프와 평문 원인이 기록돼 있어 사실상 정답지다. "
       "버퍼를 캡처해 두고(전원 재투입 전!) 원인 항목별 조치로 분기.",
       source_url=_SRC_S7_LED, source_doc="instrumentationtools — S7-300 LED 의미 정리",
       keywords=["SF", "LED", "진단버퍼", "diagnostic buffer"]),
    _e(vendor=Vendor.SIEMENS, series="S7-300/400", code="OB-MISSING",
       title="에러 OB 누락으로 CPU STOP — OB80/82/86/121/122",
       category="PROGRAM", severity="FATAL",
       likely_cause="해당 이벤트(사이클 초과·진단 인터럽트·랙/DP 장애·프로그래밍 오류·I/O "
       "액세스 오류) 발생 시 대응 OB 가 프로젝트에 없으면 CPU 가 STOP 한다.",
       suggested_action="빈 내용이라도 OB80/OB82/OB86/OB121/OB122 를 프로젝트에 넣어 두면 "
       "이벤트가 기록만 되고 운전은 지속된다(설비 성격에 따라 STOP 이 안전한 경우도 "
       "있으니 공정 위험도와 함께 결정). 진단버퍼에서 어느 OB 이벤트였는지 확인.",
       source_url=_SRC_S7_LED, source_doc="instrumentationtools — S7-300 LED/OB 정리",
       keywords=["OB121", "OB122", "OB86", "OB82", "STOP"]),
    _e(vendor=Vendor.SIEMENS, series="S7-1200/1500", code="ERROR-LED-BLINK",
       title="ERROR LED 적색 점멸 — 메모리카드/프로그램 손상 의심",
       category="SYSTEM", severity="FATAL",
       likely_cause="SMC(메모리카드)의 프로그램 손상, 펌웨어 비호환, 하드웨어 폴트.",
       suggested_action="실무 절차(공개 정비 글 검증): 전원 OFF → 카드 제거 → 전원 ON. "
       "점멸이 멎으면 CPU 정상·카드(프로그램) 문제 → 카드 포맷 후 프로젝트 재다운로드. "
       "최후 수단 MRES(공장 초기화)는 프로그램이 지워지므로 백업 확인 후에만.",
       source_url=_SRC_S7_1200, source_doc="JRM Solutions — S7-1200 ERROR LED 점멸 해결 글",
       keywords=["ERROR LED", "메모리카드", "SMC", "MRES"]),
    _e(vendor=Vendor.SIEMENS, series="S7 공통", code="ALL-LED-FLASH",
       title="모든 LED 동시 점멸 — 펌웨어 손상/비호환",
       category="SYSTEM", severity="FATAL",
       likely_cause="펌웨어 업데이트 실패·CPU 와 CP(통신프로세서) 펌웨어 조합 비호환이 "
       "가장 흔한 원인으로 보고된다.",
       suggested_action="펌웨어 재설치(공식 절차) → CP 모듈 분리 후 단독 기동으로 호환성 "
       "분리시험. 조합 비호환이면 제조사 호환표에 맞춰 한쪽을 업/다운그레이드.",
       source_url=_SRC_S7_ALLLED, source_doc="IndustrialMonitorDirect KB — 전 LED 점멸 가이드",
       keywords=["전체 점멸", "펌웨어", "CP", "호환성"]),
    _e(vendor=Vendor.SIEMENS, series="S7-300", code="AI-SF",
       title="아날로그 입력 모듈 SF — 모듈 전원/결선 문제",
       category="IO", severity="WARNING",
       likely_cause="SM331 등 AI 모듈은 모듈별 DC24V 급전이 필요 — 미급전/단자 풀림이면 "
       "SF 가 선다. 센서 여자 전원(핀 20-22) 누락 사례가 흔하다.",
       suggested_action="모듈 단자에서 멀티미터로 24V 실측(있어 보여도 단자 풀림이 흔함) "
       "→ 채널 미사용분은 파라미터에서 '비활성'으로 — 개방 채널이 단선 진단을 띄운다. "
       "측정 타입(2/4선, mA/V) 점퍼·파라미터 일치 확인.",
       source_url=_SRC_S7_AI, source_doc="IndustrialMonitorDirect KB — S7-300 AI SF 해결",
       keywords=["SM331", "아날로그", "24V", "단선 진단"]),
    _e(vendor=Vendor.SIEMENS, series="S7-300/400 DP", code="BF-LED",
       title="BF(Bus Fault) LED — PROFIBUS/PROFINET 통신 장애",
       category="COMM", severity="WARNING",
       likely_cause="DP 주소 중복(1~125 고유해야 함), 종단저항 위치 오류, 슬레이브 전원 다운.",
       suggested_action="점멸=구성된 슬레이브 일부 무응답 / 점등=버스 자체 불가로 갈라 읽는다. "
       "주소맵 표로 중복 검사 → 라인 양끝만 종단 ON 확인 → 슬레이브 전원·커넥터 순회 "
       "점검. PN 은 장치명/IP 중복이 같은 증상.",
       source_url=_SRC_S7_DP, source_doc="IndustrialMonitorDirect KB — DP SF/BF 진단",
       keywords=["BF", "PROFIBUS", "DP 주소", "종단저항"]),

    # ════════════════════════════════════════════════════════════════════════
    # OMRON — CJ/CP 계열 (요약 목차: LED·배터리·I/O 버스·사용자 FAL)
    # ════════════════════════════════════════════════════════════════════════
    _e(vendor=Vendor.OMRON, series="CJ/CP", code="ERR/ALM-ON",
       title="ERR/ALM LED 점등 — 치명 에러(운전 정지)",
       category="SYSTEM", severity="FATAL",
       likely_cause="메모리 에러·I/O 버스 에러·프로그램 이상 등 치명 분류.",
       suggested_action="CX-Programmer [PLC]-[에러 로그]로 코드 확인이 첫 단계. 정전 직후라면 "
       "배터리 소진으로 인한 메모리 소실 가능성부터 — 백업 프로젝트 재전송으로 복구.",
       source_url="https://www.fa.omron.co.jp/", source_doc="OMRON FA 공식(시리즈 매뉴얼 경유)",
       keywords=["ERR", "ALM", "에러 로그", "CX-Programmer"]),
    _e(vendor=Vendor.OMRON, series="CJ/CP", code="BATT-ERR",
       title="배터리 에러 — 유지 메모리/시계 백업 위험",
       category="POWER", severity="WARNING",
       likely_cause="리튬 배터리 수명(통상 수년) 종료.",
       suggested_action="통전 중 교체 시 데이터 유지. 교체 주기를 설비 PM 표에 고정해 두는 "
       "것이 정석(에러 뜨고 나서 교체하면 정전 한 번에 래치 소실).",
       source_url="https://www.fa.omron.co.jp/", source_doc="OMRON FA 공식",
       keywords=["배터리", "유지 메모리", "PM"]),
    _e(vendor=Vendor.OMRON, series="CJ", code="IO-BUS-ERR",
       title="I/O 버스 에러 — 증설 랙/커넥터 이상",
       category="IO", severity="FATAL",
       likely_cause="증설 케이블 접촉 불량, 랙 전원 저하, 유닛 장착 불량.",
       suggested_action="증설 케이블 재삽입·랙 전원 전압 실측 → 최소 구성 격리법(본체만 기동) "
       "으로 문제 랙 특정.",
       source_url="https://www.fa.omron.co.jp/", source_doc="OMRON FA 공식",
       keywords=["I/O 버스", "증설", "랙"]),
    _e(vendor=Vendor.OMRON, series="공통", code="FAL/FALS",
       title="사용자 정의 에러(FAL 비치명/FALS 치명) 발보",
       category="PROGRAM", severity="INFO",
       likely_cause="(체계 설명) 프로그램이 의도적으로 올린 사용자 에러 — 설비 고유 의미.",
       suggested_action="코드 번호의 의미는 그 설비 프로그램 주석/사양서가 정답. FAL 번호별 "
       "의미표를 HMI 알람 텍스트와 1:1 로 관리하면 추적이 쉬워진다.",
       source_url="https://www.fa.omron.co.jp/", source_doc="OMRON FA 공식",
       keywords=["FAL", "FALS", "사용자 에러"]),

    # ════════════════════════════════════════════════════════════════════════
    # GENERIC — 브랜드 무관 공통 진단 수칙
    # ════════════════════════════════════════════════════════════════════════
    _e(vendor=Vendor.GENERIC, code="DIAG-FIRST",
       title="공통 수칙 1 — 추측 전에 '에러 이력/진단버퍼'부터 읽는다",
       category="SYSTEM", severity="INFO",
       likely_cause="(절차) 모든 메이저 브랜드는 이력 버퍼를 내장한다(XG5000 이력, GX 진단, "
       "TIA 진단버퍼, CX 에러 로그).",
       suggested_action="전원 재투입·리셋 '먼저' 하지 말 것 — 휘발 이력이 지워진다. "
       "캡처(사진/저장) → 코드 특정 → 조치 → 클리어 순서를 표준 작업 절차로 고정.",
       keywords=["진단버퍼", "이력", "표준 절차"]),
    _e(vendor=Vendor.GENERIC, code="NOISE-24V",
       title="공통 수칙 2 — 원인불명 산발 에러는 전원·노이즈부터",
       category="POWER", severity="INFO",
       likely_cause="24V 리플·순간 강하, 인버터 동력선과의 병주 배선, 접지 불량이 "
       "'재현 안 되는' 에러의 단골 원인.",
       suggested_action="24V 를 오실로스코프/로거로 이벤트 시점 포착 → 동력/제어 배선 분리, "
       "실드 편측 접지, 서지 킬러(MC 코일) 장착 확인.",
       keywords=["노이즈", "24V", "접지", "산발 에러"]),
]
