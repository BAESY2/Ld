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
# ── 2차 정밀 확장 출처(웹 연구분) — 공개 페이지만 ───────────────────────────
_SRC_LS_XGI_CPU = (
    "https://ssq.ls-electric.com/uploads/document/16411831069720/"
    "XGI-CPU_Manual_202012_V2.1_EN.pdf"
)
_SRC_LS_XGI_EDU = (
    "https://ssq.ls-electric.com/uploads/document/16572861196090/"
    "XGI+%EC%B4%88%EA%B8%89(V21).pdf"
)
_SRC_LS_XBF_AD = (
    "https://ssq.ls-electric.com/uploads/document/16401485635220/"
    "XBF-AD04A_T16_Manual_V2.2_202110_KR.pdf.pdf"
)
_SRC_LS_XGB_HSC = "https://ssq.ls-electric.com/kr/ko/product/document/1408"
_SRC_FX3U_PROG942 = (
    "https://www.manualslib.com/manual/1304866/Mitsubishi-Electric-Melsec-Fx3u.html?page=942"
)
_SRC_FX3U_USER291 = "https://www.manualslib.com/manual/1167795/Mitsubishi-Fx3u-Mr-Es.html?page=291"
_SRC_MRPLC_6401 = "https://mrplc.com/forums/topic/44957-parameter-error-6401/"
_SRC_IMD_6708 = (
    "https://industrialmonitordirect.com/blogs/knowledgebase/"
    "mitsubishi-fx-series-plc-intermittent-cpu-e-error-and-operation-error-6708-troubleshooting"
)
_SRC_S7_OB121 = (
    "https://industrialmonitordirect.com/blogs/knowledgebase/"
    "siemens-s7-315-2-pndp-cpu-stop-with-ob121-errors-db-not-loaded-and-area-length-error"
)
_SRC_S7_CYCLE_DB = (
    "https://industrialmonitordirect.com/blogs/knowledgebase/"
    "s7-1200-cycle-time-exceeded-and-db-access-error-fix"
)
_SRC_S7_IO_OB = (
    "https://docs.tia.siemens.cloud/r/en-us/v20/functional-description-of-s7-1500-cpus-s7-1500/"
    "organization-blocks-s7-1500/description-of-all-types-of-organization-blocks-s7-1500/"
    "i/o-access-error-ob-s7-1500"
)
_SRC_S7_EMPTY_OB = (
    "https://industrialmonitordirect.com/blogs/knowledgebase/"
    "siemens-s7-ob82-ob86-why-error-organization-blocks-are-often-empty"
)
_SRC_S7_FSAFE = (
    "https://support.industry.siemens.com/cs/attachments/22304119/"
    "22304119_Passivation_Reintegration_1200F_1500F_ET200SP_V2_1_en.pdf"
)
_SRC_S7_SMC = (
    "https://docs.tia.siemens.cloud/r/en-us/v20/functional-description-of-s7-1500-cpus-s7-1500/"
    "memory-areas-s7-1500/what-you-need-to-know-about-simatic-memory-cards-s7-1500"
)
_SRC_S7_MMC_FIX = (
    "https://industrialmonitordirect.com/blogs/knowledgebase/"
    "siemens-s7-300-mmc-card-recovery-and-memory-reset-procedure"
)
_SRC_CJ2_FATAL_366 = "https://www.manualslib.com/manual/346472/Omron-Cj2-Cpu-Unit.html?page=366"
_SRC_CJ2_FATAL_367 = "https://www.manualslib.com/manual/346472/Omron-Cj2-Cpu-Unit.html?page=367"
_SRC_CJ2_TYPES_202 = "https://www.manualslib.com/manual/346472/Omron-Cj2-Cpu-Unit.html?page=202"


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
    # ── 2차 확장: XGI/XGK 에러 플래그(F 영역 기호 — 숫자 날조 금지 원칙) ──
    _e(vendor=Vendor.LS_ELECTRIC, series="XGI/XGK", code="_IO_TYER",
       title="모듈 타입 불일치 플래그 — 설정 모듈과 실장 모듈이 다름",
       category="IO", severity="FATAL",
       likely_cause="I/O 파라미터에 등록된 모듈 형식과 슬롯의 실제 모듈이 다르거나, 호환되지 "
       "않는 후속 모델로 교체한 뒤 파라미터를 갱신하지 않음.",
       suggested_action="XG5000 에러 이력에서 _IO_TYER 와 함께 기록된 슬롯 번호를 확인 → "
       "해당 슬롯의 실장 모듈 형명과 I/O 파라미터를 대조해 한쪽을 맞춘다. 후속 호환 "
       "모델 교체 시에도 형명이 다르면 타입 에러가 나므로 파라미터를 반드시 재작성.",
       source_url=_SRC_LS_XGI_CPU, source_doc="XGI CPU 매뉴얼(공식 공개 PDF) 플래그 일람",
       keywords=["_IO_TYER", "타입 불일치", "F 플래그", "슬롯"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGI/XGK", code="_IO_RWER",
       title="모듈 입출력(읽기/쓰기) 에러 플래그 — 모듈 액세스 실패",
       category="IO", severity="FATAL",
       likely_cause="모듈 내부 고장, 베이스 커넥터 접촉 불량, 강한 노이즈로 버스 액세스가 "
       "실패. 특정 슬롯에서 반복되면 그 모듈/슬롯 하드웨어가 유력.",
       suggested_action="에러 이력에서 슬롯 위치 특정 → 전원 차단 후 모듈 재장착(커넥터 "
       "청소). 재발 시 정상 슬롯과 모듈을 맞바꿔 '모듈 따라가는지/슬롯에 남는지'로 "
       "고장 부위를 갈라낸다 — 모듈이면 교체, 슬롯이면 베이스 교체.",
       source_url=_SRC_LS_XGI_CPU, source_doc="XGI CPU 매뉴얼 플래그 일람",
       keywords=["_IO_RWER", "모듈 액세스", "베이스", "교차 시험"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGI/XGK", code="_FUSE_ER",
       title="퓨즈 단선 경고 플래그 — 출력 모듈 퓨즈 끊어짐",
       category="IO", severity="WARNING",
       likely_cause="출력 모듈 퓨즈가 부하 단락/과부하로 용단 — 해당 모듈 출력만 죽고 "
       "CPU 운전은 지속되는 경우가 많아 발견이 늦다.",
       suggested_action="퓨즈 교체 전에 반드시 원인(출력단 단락·솔레노이드 소손·배선 피복 "
       "손상)을 먼저 제거 — 원인 없이 갈면 또 끊어진다. 교체 후 _FUSE_ER 플래그를 "
       "HMI 알람에 매핑해 다음번엔 즉시 인지되게 한다.",
       source_url=_SRC_LS_XGI_CPU, source_doc="XGI CPU 매뉴얼 플래그 일람",
       keywords=["_FUSE_ER", "퓨즈", "출력 모듈", "단락"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGI/XGK", code="_CODE_ER",
       title="명령어 코드 에러 플래그 — 해석 불가 코드 실행 시도",
       category="PROGRAM", severity="FATAL",
       likely_cause="다운로드 중 케이블 분리 등으로 프로그램 메모리가 부분 손상됐거나, "
       "CPU OS 버전이 지원하지 않는 신규 명령을 사용.",
       suggested_action="XG5000 으로 프로젝트를 다시 전송(쓰기 후 베리파이까지) → 재발 시 "
       "CPU OS 버전과 XG5000 버전 호환표 확인 후 OS 업데이트. 산발 재발이면 전원· "
       "노이즈 계통(접지/실드) 점검으로 메모리 손상 원인을 제거.",
       source_url=_SRC_LS_XGI_CPU, source_doc="XGI CPU 매뉴얼 플래그 일람",
       keywords=["_CODE_ER", "명령어 코드", "OS 버전", "베리파이"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGI/XGK", code="_ANC_ERR",
       title="외부기기 중고장(어넌시에이터) 플래그 — 프로그램이 올린 중대 알람",
       category="SYSTEM", severity="FATAL",
       likely_cause="(체계 설명) 래더가 외부 기기 중고장을 감지해 어넌시에이터 플래그에 "
       "기록한 것 — PLC 자체 고장이 아니라 설비측 이상 신호다.",
       suggested_action="플래그에 함께 기록된 고장 번호의 의미는 그 설비 프로그램 사양서가 "
       "정답 — PLC 를 의심하기 전에 번호별 의미표부터 찾는다. 의미표가 없으면 래더에서 "
       "_ANC_ERR 기록 위치를 크로스 레퍼런스로 역추적해 어떤 조건이 올렸는지 확인.",
       source_url=_SRC_LS_XGI_EDU, source_doc="XGI 초급 교재(공식 공개 PDF)",
       keywords=["_ANC_ERR", "어넌시에이터", "외부기기", "중고장"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGI/XGK", code="_TASK_ERR",
       title="태스크 충돌 플래그 — 주기/정주기 태스크 처리 지연",
       category="WATCHDOG", severity="WARNING",
       likely_cause="정주기 태스크 실행 시간이 주기보다 길어 다음 기동과 겹침(태스크 충돌). "
       "통신 폭주나 무거운 연산이 태스크 안에 들어간 경우가 전형.",
       suggested_action="태스크별 실행 시간을 모니터해 주기 대비 여유율을 확인 → 무거운 "
       "처리는 메인 스캔으로 빼거나 주기를 늘린다. 충돌 플래그를 알람화해 두면 "
       "간헐 지연을 놓치지 않는다.",
       source_url=_SRC_LS_XGI_CPU, source_doc="XGI CPU 매뉴얼 플래그 일람",
       keywords=["_TASK_ERR", "태스크 충돌", "정주기", "실행 시간"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGB XBF-AD", code="XBF-AD-WIRING",
       title="아날로그 입력 모듈 값 이상/고정 — 외부 결선·설정 불일치",
       category="IO", severity="WARNING",
       likely_cause="전류/전압 입력 모드와 실제 센서 출력 불일치, 미사용 채널 개방, "
       "실드 미접지로 값 떨림.",
       suggested_action="모듈 운전 파라미터(전압/전류, 범위)와 센서 사양을 1:1 대조 → "
       "미사용 채널은 '사용 안 함'으로 막아 진단 알람을 없앤다. 값 떨림은 실드 편측 "
       "접지·동력선 분리 배선으로 잡는 것이 정석.",
       source_url=_SRC_LS_XBF_AD, source_doc="XBF-AD04A 사용설명서(공식 공개 PDF)",
       keywords=["XBF", "아날로그", "결선", "채널 설정"]),
    _e(vendor=Vendor.LS_ELECTRIC, series="XGB HSC", code="XGB-HSC-PARAM",
       title="고속카운터 카운트 누락/불가 — 파라미터·입력 사양 불일치",
       category="PROGRAM", severity="WARNING",
       likely_cause="엔코더 출력(오픈컬렉터/라인드라이버)과 모듈 입력 사양 불일치, 1상/2상 "
       "모드 설정 오류, 입력 필터가 펄스 폭보다 길어 카운트 누락.",
       suggested_action="엔코더 사양서와 모듈 입력 사양(전압·최대 주파수)을 먼저 대조 → "
       "2상 엔코더는 A/B 위상 결선과 모드 일치 확인 → 고주파에서 누락되면 입력 필터 "
       "시간을 펄스 폭 이하로 낮춘다. 설정 후 저속 수동 회전으로 1:1 카운트 검증.",
       source_url=_SRC_LS_XGB_HSC, source_doc="LS ssq — XGB 고속카운터 사용설명서 문서 페이지",
       keywords=["고속카운터", "HSC", "엔코더", "입력 필터"]),

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
    # ── 2차 확장: 67xx 연산 에러 나머지 + 63xx/64xx/65xx/61xx 계열 ──
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6702",
       title="CALL 중첩 한도 초과 — 서브루틴 6단 이상 호출",
       category="PROGRAM", severity="FATAL",
       likely_cause="CALL 의 중첩이 허용 단수(5단)를 넘음 — 서브루틴 안에서 또 CALL 하는 "
       "구조가 누적된 경우. 조건 분기에 따라 런타임에만 터지기도 한다.",
       suggested_action="크로스 레퍼런스로 CALL 호출 트리를 그려 최심 깊이를 센다 → 5단 "
       "이내로 평탄화(말단 서브루틴을 상위로 인라인하거나 플래그+메인 분기로 변경). "
       "재귀성 호출(자기 자신/순환 CALL)은 FX 에서 금물이므로 구조 자체를 제거.",
       source_url=_SRC_FX3U_PROG942, source_doc="FX3U 프로그래밍 매뉴얼 에러표(공개 열람)",
       keywords=["6702", "CALL", "중첩", "서브루틴", "P 라벨"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6703",
       title="인터럽트 중첩 한도 초과 — 3단 이상 중첩",
       category="PROGRAM", severity="FATAL",
       likely_cause="인터럽트 루틴 실행 중 다른 인터럽트가 연쇄로 끼어들어 허용 단수(2단)를 "
       "초과 — 고속 펄스 입력이 몰리는 설비에서 전형적.",
       suggested_action="인터럽트 루틴은 '플래그만 세우고 즉시 IRET' 수준으로 최소화하고 "
       "실처리는 메인 스캔으로 이관. 동시에 쓰는 인터럽트 수 자체를 줄이고, 필요 "
       "구간에서만 EI/DI 로 허가 범위를 좁힌다.",
       source_url=_SRC_FX3U_PROG942, source_doc="FX3U 프로그래밍 매뉴얼 에러표",
       keywords=["6703", "인터럽트", "중첩", "EI", "DI"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6704",
       title="FOR-NEXT 중첩 한도 초과 — 6단 이상",
       category="PROGRAM", severity="FATAL",
       likely_cause="FOR~NEXT 루프가 허용 단수(5단)를 넘게 중첩 — 복붙으로 루프 안에 "
       "루프를 계속 넣다 보면 도달한다.",
       suggested_action="중첩 루프를 1~2중으로 풀어 쓰되, 다차원 순회는 인덱스 산술(행×폭+ "
       "열)로 1중 루프화. 루프가 깊을수록 스캔타임도 같이 폭증하므로 6105(워치독)와 "
       "함께 오는지 D8012 를 확인.",
       source_url=_SRC_FX3U_PROG942, source_doc="FX3U 프로그래밍 매뉴얼 에러표",
       keywords=["6704", "FOR", "NEXT", "중첩", "루프"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6708",
       title="FROM/TO 명령 에러 — 특수 유닛 버퍼메모리(BFM) 액세스 실패",
       category="PROGRAM", severity="FATAL",
       likely_cause="유닛 번호/BFM 번호가 실장 구성과 안 맞거나, 특수 유닛이 응답하지 않음. "
       "간헐 발생이면 증설 케이블 접촉·노이즈로 액세스가 무작위 실패하는 사례가 보고됨.",
       suggested_action="에러 스텝(D8069)의 FROM/TO 에서 유닛 번호(K0부터 좌→우)와 BFM "
       "번호를 그 유닛 매뉴얼과 대조. 간헐성이면 증설 케이블 재삽입·노이즈 대책 후 "
       "M8067(연산 에러 래치)로 재발을 감시한다 — 매번 같은 스텝이면 프로그램, "
       "무작위 스텝이면 하드웨어 쪽이 유력.",
       source_url=_SRC_IMD_6708, source_doc="IndustrialMonitorDirect KB — FX 간헐 6708 사례",
       keywords=["6708", "FROM", "TO", "BFM", "특수 유닛"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6709",
       title="기타 연산 구조 에러 — IRET/SRET 누락·FOR-NEXT 짝 이상",
       category="PROGRAM", severity="FATAL",
       likely_cause="인터럽트/서브루틴의 복귀 명령(IRET/SRET) 누락, FOR-NEXT 짝 불일치, "
       "점프로 루프 중간에 뛰어드는 비정상 흐름.",
       suggested_action="P 라벨 이후 블록마다 SRET, I 포인터 루틴마다 IRET 가 닫히는지 "
       "전수 점검 → FOR/NEXT 개수 일치 확인 → CJ 가 FOR-NEXT 내부로 점프해 들어가는 "
       "경로가 없는지 흐름을 따라간다. 부분 복붙 수정 직후에 가장 잘 터진다.",
       source_url=_SRC_FX3U_PROG942, source_doc="FX3U 프로그래밍 매뉴얼 에러표",
       keywords=["6709", "IRET", "SRET", "FOR-NEXT", "점프"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6103",
       title="I/O 버스 에러 — CPU-증설 간 버스 이상 (M8061/D8061)",
       category="IO", severity="FATAL",
       likely_cause="증설 케이블/커넥터 접촉 불량, 증설 유닛 고장, 버스 라인 노이즈.",
       suggested_action="전원 차단 후 증설 케이블 전부 재삽입 → 최소 구성(본체만)으로 "
       "기동해 정상인지 확인 → 유닛을 하나씩 되붙여 문제 유닛을 특정한다. 진동 "
       "설비라면 커넥터 고정 상태를 정기 점검 항목에 추가.",
       source_url=_SRC_FX3U_MAN, source_doc="FX3U 에러표(하드웨어 에러 D8061)",
       keywords=["6103", "I/O 버스", "D8061", "증설"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6104",
       title="증설 유닛 24V 이상 — 급전형 증설 전원 실패",
       category="POWER", severity="FATAL",
       likely_cause="급전형 증설 유닛의 24V 서비스 전원 이상(과부하·전원부 고장)으로 "
       "증설측 I/O 전체가 무효화.",
       suggested_action="증설 유닛 24V 단자를 멀티미터로 실측 → 외부 센서 부하가 서비스 "
       "전원 용량을 넘지 않는지 합산(넘으면 외부 SMPS 로 분리 급전). 전압 정상인데 "
       "재발하면 유닛 전원부 고장으로 보고 교체.",
       source_url=_SRC_FX3U_MAN, source_doc="FX3U 에러표(하드웨어 에러 D8061)",
       keywords=["6104", "24V", "증설 전원", "과부하"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6301-6305",
       title="시리얼 통신 ch1 에러 — 패리티/오버런/프레이밍·수신 이상 (D8063)",
       category="COMM", severity="WARNING",
       likely_cause="통신 포맷(보레이트/패리티/정지비트) 불일치, 케이블 노이즈, 상대국 "
       "프로토콜 이상 — 채널1 에러는 D8063 에 코드가 남는다.",
       suggested_action="D8063 값을 HMI 에 상시 표시해 발생 빈도를 기록 → 양단 포맷 표 "
       "대조 → 노이즈성(산발)이면 차폐 케이블·배선 분리부터. 채널2 는 D8438 로 "
       "같은 요령으로 본다.",
       source_url=_SRC_FX3U_USER291, source_doc="FX3U 사용자 매뉴얼 에러표(공개 열람)",
       keywords=["6301", "D8063", "패리티", "프레이밍", "시리얼"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6401",
       title="파라미터 섬체크 에러 — 파라미터 영역 손상",
       category="PROGRAM", severity="FATAL",
       likely_cause="다운로드 중단·배터리 소진·노이즈로 파라미터 영역 체크섬 불일치. "
       "타 버전 GX 로 만든 프로젝트 이식 직후에도 보고된다(MrPLC 사례).",
       suggested_action="PLC STOP 상태에서 GX Works 로 파라미터를 다시 쓰고 베리파이 → "
       "재발 시 메모리 카세트 장착 여부 확인(카세트 불량이면 분리 후 내장 메모리로 "
       "시험). 배터리 저하(BATT LED)와 동반되면 배터리부터 교체.",
       source_url=_SRC_MRPLC_6401, source_doc="MrPLC 포럼 — Parameter Error 6401 스레드",
       keywords=["6401", "파라미터", "섬체크", "메모리 카세트"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6402-6409",
       title="파라미터 설정 에러군 — 용량/래치/코멘트/파일레지스터 설정 불일치",
       category="PROGRAM", severity="FATAL",
       likely_cause="메모리 용량(6402)·래치 영역(6403)·코멘트 영역(6404)·파일 레지스터 "
       "(6405) 등 파라미터 설정값이 기종 허용 범위나 실제 메모리와 안 맞음.",
       suggested_action="파라미터 에러 레지스터(D8064)의 64xx 세부 번호를 읽어 특정 → PLC "
       "파라미터의 메모리 배분(프로그램/코멘트/파일 레지스터 합계)이 기종 용량 안에 "
       "들어가는지 재계산해 재작성. 타 기종 프로젝트 이식 시 용량 차이가 단골 원인.",
       source_url=_SRC_FX3U_USER291, source_doc="FX3U 사용자 매뉴얼 에러표",
       keywords=["6402", "6403", "6405", "파라미터", "메모리 배분"]),
    _e(vendor=Vendor.MITSUBISHI, series="FX", code="6501-6510",
       title="문법(신택스) 에러군 — 명령·디바이스 조합/라벨 이상",
       category="PROGRAM", severity="FATAL",
       likely_cause="명령-디바이스 조합 부적합(6501), OUT T/C 설정값 누락(6502), 라벨 "
       "중복(6503), 디바이스 번호 범위 밖(6504), MC 네스팅 이상(6509) 등 작성 단계 오류.",
       suggested_action="쓰기 시점에 검출되므로 GX Works 의 프로그램 체크를 돌려 에러 "
       "스텝으로 점프 → 해당 명령의 디바이스 허용표와 대조해 수정. 라벨(P/I) 중복은 "
       "크로스 레퍼런스 목록으로 한 번에 잡는 것이 빠르다.",
       source_url=_SRC_FX3U_USER291, source_doc="FX3U 사용자 매뉴얼 에러표",
       keywords=["6501", "6502", "문법", "라벨 중복", "MC 네스팅"]),

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
    # ── 2차 확장: OB 별 구체 항목 + F-CPU + 메모리카드 ──
    _e(vendor=Vendor.SIEMENS, series="S7-300/1500", code="OB121",
       title="프로그래밍 오류(동기) — 'DB not loaded'/영역 길이 초과로 STOP",
       category="PROGRAM", severity="FATAL",
       likely_cause="존재하지 않는/미로드 DB 접근, 선언 길이를 넘는 영역 읽기·쓰기 등 "
       "명령 실행 시점의 동기 오류 — OB121 이 없으면 CPU 가 즉시 STOP.",
       suggested_action="진단버퍼의 해당 이벤트에서 'Open in editor' 로 문제 명령으로 점프 "
       "(실측 사례 검증). 누락 DB 는 다운로드 목록에 포함해 재전송, 간접 주소는 접근 "
       "전 DB 번호·오프셋 유효성 검사를 넣는다. OB121 을 (빈 내용이라도) 추가해 두면 "
       "기록 후 운전 지속 — 단, 안전상 STOP 이 맞는 공정인지 먼저 판단.",
       source_url=_SRC_S7_OB121, source_doc="IndustrialMonitorDirect KB — OB121 DB 오류 사례",
       keywords=["OB121", "DB not loaded", "area length", "동기 오류"]),
    _e(vendor=Vendor.SIEMENS, series="S7-1200/1500", code="ARRAY-IDX-OOB",
       title="어레이 인덱스 범위 초과 — 간접 접근이 선언 크기를 벗어남",
       category="PROGRAM", severity="FATAL",
       likely_cause="HMI 입력값·계산 결과가 그대로 배열 인덱스로 들어가 선언 범위를 넘는 "
       "읽기/쓰기 발생(area length error) — 특정 조건에서만 터져 재현이 어렵다.",
       suggested_action="모든 간접 접근 직전에 IF 0 <= idx AND idx <= 상한 가드를 넣는 "
       "것이 정석(공개 정비 사례 권고). HMI 에서 오는 인덱스는 수신 즉시 LIMIT 로 "
       "클램프. 진단버퍼 이벤트에서 블록/네트워크를 특정해 가드 누락 지점을 찾는다.",
       source_url=_SRC_S7_CYCLE_DB, source_doc="IndustrialMonitorDirect KB — DB 액세스 오류 해결",
       keywords=["어레이", "인덱스", "범위 초과", "LIMIT", "간접 접근"]),
    _e(vendor=Vendor.SIEMENS, series="S7 공통", code="OB80",
       title="시간 오류 OB — 사이클 시간 초과 이벤트",
       category="WATCHDOG", severity="FATAL",
       likely_cause="OB1 실행이 최대 사이클 시간을 초과(대량 루프·통신 폭주). OB80 미존재 "
       "시 CPU STOP.",
       suggested_action="온라인 진단의 사이클 시간 통계(최소/현재/최대)로 실측 → 무거운 "
       "처리를 여러 사이클로 분할하거나 저우선 처리로 이동. 최대 사이클 설정 상향은 "
       "원인 제거 후 최후 수단. OB80 추가 시 이벤트 횟수를 카운트해 HMI 에 노출하면 "
       "한계 근접을 조기에 본다.",
       source_url=_SRC_S7_CYCLE_DB, source_doc="IndustrialMonitorDirect KB — 사이클 초과 해결",
       keywords=["OB80", "사이클", "time error", "초과"]),
    _e(vendor=Vendor.SIEMENS, series="S7-1500/ET200", code="OB83",
       title="모듈 착탈 인터럽트 OB — 운전 중 모듈 제거/삽입 감지",
       category="IO", severity="WARNING",
       likely_cause="분산 I/O(ET200) 모듈이 운전 중 빠졌다 꽂힘 — 진동·커넥터 마모, 또는 "
       "활선 교체 작업.",
       suggested_action="OB83 을 프로젝트에 넣어 착탈 이벤트를 기록·알람화(없으면 STOP "
       "위험). 이벤트의 하드웨어 식별자로 어느 스테이션·슬롯인지 특정 → 반복되는 "
       "슬롯은 커넥터/록 기구를 물리 점검. 계획 활선 교체라면 사전 알람 마스킹 절차를 "
       "표준화한다.",
       source_url=_SRC_S7_EMPTY_OB, source_doc="IndustrialMonitorDirect KB — 에러 OB 운용 해설",
       keywords=["OB83", "착탈", "pull plug", "ET200"]),
    _e(vendor=Vendor.SIEMENS, series="S7-1500", code="OB122",
       title="I/O 액세스 오류 OB — 직접 I/O 읽기/쓰기 실패",
       category="IO", severity="WARNING",
       likely_cause="프로세스 이미지 밖 직접 액세스 대상 모듈이 고장/탈락 상태이거나 주소가 "
       "실구성과 불일치 — 명령 단위로 동기 발생한다.",
       suggested_action="진단버퍼에서 실패한 논리 주소를 읽어 하드웨어 구성의 모듈 주소와 "
       "대조 → 모듈 상태(진단 LED)와 함께 보면 주소 오류인지 모듈 고장인지 갈린다. "
       "OB122 를 추가해 실패 시 대체값(안전측)을 쓰는 폴백을 구현하는 것이 정석.",
       source_url=_SRC_S7_IO_OB, source_doc="Siemens TIA 공식 문서 — I/O access error OB",
       keywords=["OB122", "I/O 액세스", "논리 주소", "폴백"]),
    _e(vendor=Vendor.SIEMENS, series="S7-1500/ET200", code="OB86",
       title="랙/스테이션 장애 OB — 분산 I/O 스테이션 전체 상실",
       category="COMM", severity="FATAL",
       likely_cause="PROFINET/PROFIBUS 스테이션 전원 다운, 케이블 단선, 스위치 포트 불량 "
       "으로 스테이션 단위 통신 상실 — OB86 미존재 시 CPU STOP.",
       suggested_action="OB86 으로 상실/복귀 이벤트를 알람화하고 스테이션 번호를 HMI 에 "
       "표시 → 현장에서는 해당 스테이션 전원·링크 LED·케이블 순으로 점검. 복귀 후 "
       "남는 패시브 알람은 이벤트 종류(incoming/outgoing)로 구분해 정리한다.",
       source_url=_SRC_S7_EMPTY_OB, source_doc="IndustrialMonitorDirect KB — 에러 OB 운용 해설",
       keywords=["OB86", "스테이션", "rack failure", "PROFINET"]),
    _e(vendor=Vendor.SIEMENS, series="S7-1200F/1500F", code="F-PASSIVATION",
       title="F-I/O 패시베이션 — 안전 모듈이 페일세이프 값(0)으로 고착",
       category="IO", severity="WARNING",
       likely_cause="PROFIsafe 통신 오류·채널 폴트(단선/단락)·기동 직후 상태에서 F-모듈이 "
       "실값 대신 페일세이프 값을 출력 — 통신성 폴트 후엔 자동 복귀하지 않는다(수동 "
       "재통합 필요).",
       suggested_action="원인(결선·전원·PROFIsafe 네트워크 품질)을 먼저 제거 → 해당 F-I/O "
       "DB 의 ACK_REQ=1 확인 후 ACK_REI 에 상승 에지(또는 ACK_GL 일괄)로 재통합 — "
       "공식 절차. ACK_REI 버튼을 HMI 에 두되 원인 미제거 상태의 맹목 재통합은 금지 "
       "(곧장 재패시베이션된다).",
       source_url=_SRC_S7_FSAFE, source_doc="Siemens 공식 — Passivation/Reintegration 문서",
       keywords=["패시베이션", "ACK_REI", "ACK_REQ", "PROFIsafe", "F-CPU"]),
    _e(vendor=Vendor.SIEMENS, series="S7-1500", code="SMC-FAULT",
       title="SIMATIC 메모리카드 이상 — 카드 없음/비호환/손상으로 기동 불가",
       category="SYSTEM", severity="FATAL",
       likely_cause="S7-1500 은 SMC 가 필수(내장 실행 불가) — 카드 미장착, 시중 SD 카드 "
       "사용(전용 카드만 가능), 파일 시스템 손상이면 기동·다운로드가 실패한다.",
       suggested_action="정품 SMC 인지부터 확인(일반 SD 는 인식돼도 운용 불가 — 공식 "
       "문서 명시) → TIA 의 카드 리더 기능으로 내용 확인, 손상 시 TIA 에서 포맷 후 "
       "프로젝트 재다운로드. 쓰기 수명 임박 카드(빈번한 데이터 로깅)는 교체 주기를 "
       "정해 둔다.",
       source_url=_SRC_S7_SMC, source_doc="Siemens TIA 공식 문서 — SIMATIC memory card",
       keywords=["SMC", "메모리카드", "기동 불가", "포맷"]),
    _e(vendor=Vendor.SIEMENS, series="S7-300", code="MMC-CORRUPT",
       title="MMC 카드 손상 — STOP 고착/다운로드 실패, 메모리 리셋 절차",
       category="SYSTEM", severity="FATAL",
       likely_cause="통전 중 카드 삽발·전원 순단으로 MMC 파일 시스템 손상 — STOP 에서 "
       "복귀하지 못하거나 다운로드가 반복 실패한다.",
       suggested_action="공개 복구 절차: 모드 셀렉터 MRES 유지로 메모리 리셋(LED 점멸 "
       "시퀀스 확인) → 실패 시 PG/카드 리더에서 카드 재포맷 후 프로젝트 재전송. "
       "MMC 는 통전 중 절대 삽발 금지를 작업 수칙으로 명문화한다.",
       source_url=_SRC_S7_MMC_FIX, source_doc="IndustrialMonitorDirect KB — MMC 복구 절차",
       keywords=["MMC", "MRES", "메모리 리셋", "STOP 고착"]),

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
    # ── 2차 확장: CJ2 치명 에러코드 구체화(공개 매뉴얼 에러표 기반) ──
    _e(vendor=Vendor.OMRON, series="CJ2", code="A400",
       title="에러코드 저장 체계 — A400(최고 심각도 코드)·에러 로그",
       category="SYSTEM", severity="INFO",
       likely_cause="(체계 설명) 발생 에러의 코드가 보조 영역 A400 에 저장되고, 동시 다발 "
       "시 더 심각한 쪽 코드가 남는다. 상세는 에러별 보조 워드에 추가 기록.",
       suggested_action="CX-Programmer 접속 전이라도 HMI 에 A400 을 상시 표시해 두면 "
       "현장에서 코드부터 부를 수 있다. 접속 후에는 [PLC]-[에러 로그]에서 이력·시각을 "
       "확인하고, 클리어 전에 반드시 캡처해 정비일지에 남긴다.",
       source_url=_SRC_CJ2_TYPES_202, source_doc="CJ2 CPU 매뉴얼 에러 종류 장(공개 열람)",
       keywords=["A400", "에러 로그", "보조 영역", "심각도"]),
    _e(vendor=Vendor.OMRON, series="CJ2", code="809F",
       title="사이클 타임 초과 — 감시 사이클 시간(watch cycle) 넘김",
       category="WATCHDOG", severity="FATAL",
       likely_cause="사이클 타임이 PLC Setup 의 최대(감시) 사이클 설정을 초과 — 대량 루프, "
       "통신 명령 폭주, 인터럽트 과다가 전형.",
       suggested_action="CX-Programmer 의 사이클 타임 모니터로 평시/피크를 실측 → 무거운 "
       "처리를 분할하거나 태스크 분리. 감시값 상향은 원인 제거 후 최후 수단 — 폭주 "
       "정지 안전망을 스스로 끄는 셈이다.",
       source_url=_SRC_CJ2_FATAL_366, source_doc="CJ2 CPU 매뉴얼 치명 에러표(공개 열람)",
       keywords=["809F", "사이클", "cycle time", "초과"]),
    _e(vendor=Vendor.OMRON, series="CJ2", code="80C0-80C7",
       title="I/O 버스 에러 — CPU-유닛 간 버스 이상/엔드 커버 미장착",
       category="IO", severity="FATAL",
       likely_cause="CPU·증설 랙의 버스 라인 이상, 또는 랙 끝의 엔드 커버 미장착(공개 "
       "에러표에 명시된 의외의 단골) — 코드 하위가 랙/슬롯을 가리킨다.",
       suggested_action="엔드 커버 장착부터 확인(랙마다 필수) → 증설 케이블 재삽입 → "
       "최소 구성 기동으로 문제 랙을 격리. 코드와 함께 기록되는 보조 워드의 랙/슬롯 "
       "정보로 위치를 좁힌다.",
       source_url=_SRC_CJ2_FATAL_366, source_doc="CJ2 CPU 매뉴얼 치명 에러표",
       keywords=["80C0", "I/O 버스", "엔드 커버", "증설 랙"]),
    _e(vendor=Vendor.OMRON, series="CJ2", code="80E0",
       title="I/O 설정 에러 — 등록 I/O 테이블과 실장 유닛 불일치",
       category="IO", severity="FATAL",
       likely_cause="등록된 I/O 테이블과 실제 접속 유닛이 다름 — 유닛 교체/증설 후 테이블 "
       "재생성을 빠뜨린 경우가 전형.",
       suggested_action="CX-Programmer 의 I/O 테이블 화면에서 '실장 기반 생성'으로 테이블을 "
       "재작성 → 전송 → 전원 재투입. 의도된 구성 변경인지 무단 변경인지 정비 이력과 "
       "대조하는 습관이 사고를 줄인다.",
       source_url=_SRC_CJ2_FATAL_367, source_doc="CJ2 CPU 매뉴얼 치명 에러표",
       keywords=["80E0", "I/O 테이블", "불일치", "유닛 교체"]),
    _e(vendor=Vendor.OMRON, series="CJ2", code="80E1",
       title="I/O 점수 초과 — CPU 허용 I/O 포인트 한도 넘김",
       category="IO", severity="FATAL",
       likely_cause="증설을 거듭해 유닛 합계 I/O 점수가 해당 CPU 모델의 최대치를 초과.",
       suggested_action="유닛별 점유 점수를 표로 합산해 CPU 사양 한도와 비교 → 초과분 "
       "유닛을 제거하거나 상위 CPU 로 교체를 검토. 증설 계획 단계에서 점수 여유율 "
       "20% 이상을 남기는 것이 실무 정석.",
       source_url=_SRC_CJ2_FATAL_367, source_doc="CJ2 CPU 매뉴얼 치명 에러표",
       keywords=["80E1", "I/O 점수", "한도 초과", "증설 계획"]),
    _e(vendor=Vendor.OMRON, series="CJ2", code="80E9",
       title="유닛/랙 번호 중복 — CPU 버스 유닛 번호가 겹침",
       category="IO", severity="FATAL",
       likely_cause="둘 이상의 CPU 버스 유닛(통신 유닛 등)에 같은 유닛 번호가 할당 — "
       "유닛 전면 로터리 스위치 설정 실수가 대부분.",
       suggested_action="각 CPU 버스 유닛의 번호 스위치를 눈으로 전수 확인해 중복 제거 → "
       "전원 재투입 → I/O 테이블 재생성. 유닛 번호 배정표를 도면에 명기해 두면 "
       "교체 작업 때 재발하지 않는다.",
       source_url=_SRC_CJ2_FATAL_367, source_doc="CJ2 CPU 매뉴얼 치명 에러표",
       keywords=["80E9", "유닛 번호", "중복", "로터리 스위치"]),

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
