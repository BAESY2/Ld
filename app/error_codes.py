"""PLC 에러코드 지식베이스 (스키마 + 합법 수집 원칙).

⚠️ 수집 원칙 (절대 규칙):
  1. 제조사 사이트를 무차별 스크래핑하지 않는다. robots.txt 와 이용약관(ToS)을 존중한다.
  2. 매뉴얼 *본문 텍스트*는 저작권 보호 대상이다. 통째 복제/임베딩하지 않는다.
  3. 에러코드의 *사실 데이터*(코드값, 의미 요약, 분류)만 구조화하고, 반드시 출처를 명기한다.
  4. 공식·공개 레퍼런스(제조사 공개 매뉴얼 PDF, 오픈 데이터)만 정식 경로로 수집한다.
  5. 라이선스가 모호한 항목은 license="UNCLEAR" 로 표시하고 사용 전 법무 확인.

따라서 이 모듈은 *수집기*가 아니라 *출처 추적되는 구조화 DB 의 계약*이다.
실제 적재(ingest)는 사람이 검토·승인한 항목만 추가한다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Vendor(StrEnum):
    LS_ELECTRIC = "LS_ELECTRIC"
    MITSUBISHI = "MITSUBISHI"
    SIEMENS = "SIEMENS"
    OMRON = "OMRON"
    GENERIC = "GENERIC"


class ErrorCode(BaseModel):
    """에러코드 한 건 — 사실 데이터 + 출처."""

    vendor: Vendor
    series: str = Field(default="", description="PLC 시리즈/CPU (예: XGK, iQ-R)")
    code: str = Field(..., description="에러 코드값 (예: '16', 'E0001')")
    title: str = Field(..., description="짧은 의미 (자체 요약, 매뉴얼 본문 복제 금지)")
    category: str = Field(default="", description="분류 (예: WATCHDOG, IO, COMM)")
    likely_cause: str = Field(default="", description="추정 원인 (자체 작성)")
    suggested_action: str = Field(default="", description="권장 조치 (자체 작성)")
    source_url: str = Field(default="", description="공식 출처 URL(있을 때)")
    source_doc: str = Field(default="", description="공식 문서명/버전")
    license: str = Field(default="UNCLEAR", description="데이터 라이선스 상태")
    severity: str = Field(
        default="",
        description="심각도 (예: FATAL, WARNING, INFO). 빈 문자열=미분류.",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="검색 보조 키워드 목록 (자체 작성)",
    )


class ErrorCodeDB:
    """메모리 내 조회. 추후 SQLite/FAISS 로 교체."""

    def __init__(self, entries: list[ErrorCode] | None = None) -> None:
        self._entries: list[ErrorCode] = list(entries or [])

    def add(self, entry: ErrorCode) -> None:
        self._entries.append(entry)

    def lookup(self, vendor: Vendor, code: str) -> ErrorCode | None:
        for e in self._entries:
            if e.vendor == vendor and e.code == code:
                return e
        return None

    def all(self) -> list[ErrorCode]:
        return list(self._entries)

    def search(self, query: str, vendor: Vendor | None = None) -> list[ErrorCode]:
        """Case-insensitive substring search over code/title/category/keywords.

        Args:
            query: Substring to search for.
            vendor: Optional vendor filter; when provided, only entries whose
                    vendor matches are returned.

        Returns:
            List of matching ErrorCode entries (order: insertion order).
        """
        q = query.lower()
        results: list[ErrorCode] = []
        for e in self._entries:
            if vendor is not None and e.vendor != vendor:
                continue
            haystack = " ".join(
                [e.code, e.title, e.category] + e.keywords
            ).lower()
            if q in haystack:
                results.append(e)
        return results


# 사람이 검토·승인한 시드(사실 데이터 + 자체 요약). 매뉴얼 본문 복제 아님.
SEED: list[ErrorCode] = [
    # ── GENERIC concepts ────────────────────────────────────────────────────
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="WDT",
        title="워치독 타임아웃",
        category="WATCHDOG",
        likely_cause="스캔 시간이 설정 한계를 초과(무한 루프/과도한 연산).",
        suggested_action="스캔 부하 분산, 루프 종료 조건 점검, 워치독 설정 확인.",
        severity="FATAL",
        keywords=["watchdog", "scan overrun", "timeout", "loop"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="SCAN_OVERRUN",
        title="스캔 주기 초과",
        category="WATCHDOG",
        likely_cause="단일 스캔에서 처리해야 할 명령어 수가 너무 많거나 인터럽트 폭주.",
        suggested_action="프로그램 분할, 인터럽트 빈도 축소, 워치독 타이머 값 재설정 검토.",
        severity="FATAL",
        keywords=["scan", "overrun", "cycle time", "watchdog"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="BATT_LOW",
        title="배터리 전압 저하 / RAM 백업 손실 위험",
        category="POWER",
        likely_cause="CPU 모듈 내 리튬 배터리 수명 종료 또는 완전 방전.",
        suggested_action="즉시 배터리 교체 후 프로그램·데이터 메모리 재확인.",
        severity="WARNING",
        keywords=["battery", "low", "RAM backup", "backup loss", "lithium"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="IO_BUS_ERR",
        title="I/O 버스 통신 오류",
        category="IO",
        likely_cause="I/O 모듈과 CPU 간 버스 신호 이상(노이즈, 접촉 불량, 모듈 고장).",
        suggested_action="모듈 재장착, 케이블/커넥터 점검, 대체 모듈로 교체 시험.",
        severity="FATAL",
        keywords=["I/O", "bus", "communication", "module", "noise"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="COMM_TIMEOUT",
        title="통신 타임아웃",
        category="COMM",
        likely_cause="원격 장치 응답 없음 또는 네트워크 케이블/설정 불일치.",
        suggested_action="케이블·종단저항 확인, 통신 파라미터(보레이트/IP 등) 재점검.",
        severity="WARNING",
        keywords=["communication", "timeout", "network", "remote", "serial", "ethernet"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="DIV_ZERO",
        title="0으로 나누기 오류",
        category="PROGRAM",
        likely_cause="프로그램 내 나눗셈 명령의 제수가 런타임에 0이 됨.",
        suggested_action="나눗셈 전 제수 0 여부 확인 로직 추가.",
        severity="FATAL",
        keywords=["division", "zero", "arithmetic", "math"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="INDEX_OOB",
        title="인덱스/배열 범위 초과",
        category="PROGRAM",
        likely_cause="간접 주소 또는 인덱스 레지스터 값이 선언된 배열 크기를 벗어남.",
        suggested_action="인덱스 상·하한 클램핑 로직 추가 및 배열 크기 재확인.",
        severity="FATAL",
        keywords=["index", "array", "out of range", "bounds", "indirect address"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="STACK_OVERFLOW",
        title="스택 오버플로",
        category="PROGRAM",
        likely_cause="과도한 중첩 서브루틴 호출 또는 재귀 호출로 스택 공간 소진.",
        suggested_action="호출 깊이 축소, 재귀 구조 제거, 스택 크기 설정 점검.",
        severity="FATAL",
        keywords=["stack", "overflow", "subroutine", "recursion", "nesting"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="INVALID_INSTR",
        title="잘못된 명령어",
        category="PROGRAM",
        likely_cause="CPU가 인식할 수 없는 명령 코드 실행(펌웨어 버전 불일치 또는 메모리 손상).",
        suggested_action="프로그램 재다운로드, CPU 펌웨어 버전 확인, 메모리 자기진단 실행.",
        severity="FATAL",
        keywords=["invalid", "instruction", "opcode", "firmware", "memory corruption"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="PSU_FAULT",
        title="전원 공급 장치 이상",
        category="POWER",
        likely_cause="입력 전압 범위 이탈, 전원 모듈 내부 고장, 과부하.",
        suggested_action="입력 전압·전류 측정, 전원 모듈 교체, 부하 분산 검토.",
        severity="FATAL",
        keywords=["power supply", "PSU", "voltage", "overload", "power fault"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="CPU_FAULT",
        title="CPU 하드웨어 이상",
        category="SYSTEM",
        likely_cause="CPU 모듈 내부 하드웨어 오류 또는 메모리 자기진단 실패.",
        suggested_action="CPU 모듈 교체, 제조사 기술지원 문의.",
        severity="FATAL",
        keywords=["CPU", "hardware", "fault", "self-diagnostic", "replace"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="MISSING_END",
        title="END 명령 누락",
        category="PROGRAM",
        likely_cause="래더 프로그램의 마지막 END 명령이 없거나 잘못 배치됨.",
        suggested_action="프로그래밍 소프트웨어로 프로그램 끝에 END 명령 추가 후 재다운로드.",
        severity="FATAL",
        keywords=["END", "missing", "ladder", "program", "last rung"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="FORCE_ACTIVE",
        title="강제 출력(Force) 활성 경고",
        category="WARNING",
        likely_cause="유지보수 중 특정 비트/코일이 강제 ON/OFF 상태로 남아 있음.",
        suggested_action="강제 설정 목록 전체 해제 후 정상 운전 복귀 확인.",
        severity="WARNING",
        keywords=["force", "forced", "override", "coil", "output", "maintenance"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="MEM_PARITY",
        title="메모리 패리티 오류",
        category="SYSTEM",
        likely_cause="프로그램 또는 데이터 메모리에서 패리티 불일치 감지(EMI, 전원 순간 저하).",
        suggested_action="전원 사이클 후 자기진단 재실행, 지속 시 CPU 모듈 교체.",
        severity="FATAL",
        keywords=["memory", "parity", "checksum", "EMI", "data corruption"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="IO_CONFIG_MISMATCH",
        title="I/O 구성 불일치",
        category="IO",
        likely_cause="프로젝트에 등록된 I/O 모듈 구성과 실제 장착 모듈이 다름.",
        suggested_action="실제 모듈 슬롯 구성과 프로젝트 I/O 파라미터를 일치시키고 재다운로드.",
        severity="FATAL",
        keywords=["I/O", "configuration", "mismatch", "module", "slot", "verify"],
        license="SELF_AUTHORED",
    ),

    # ── LS ELECTRIC – XGK/XGB general concepts ──────────────────────────────
    ErrorCode(
        vendor=Vendor.LS_ELECTRIC,
        series="XGK",
        code="CPU_ERR",
        title="XGK CPU 하드웨어/자기진단 오류",
        category="SYSTEM",
        likely_cause="XGK CPU 모듈 내부 자기진단에서 하드웨어 이상 감지.",
        suggested_action="CPU 모듈 교체 및 LS ELECTRIC 기술지원 문의.",
        severity="FATAL",
        keywords=["XGK", "CPU", "error", "self-diagnostic", "LS ELECTRIC"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.LS_ELECTRIC,
        series="XGK",
        code="WDT_ERR",
        title="XGK 스캔 워치독 초과",
        category="WATCHDOG",
        likely_cause="XGK CPU 스캔 시간이 워치독 타이머 설정값을 초과.",
        suggested_action="스캔 프로그램 최적화, XG5000 소프트웨어로 워치독 시간 재설정.",
        severity="FATAL",
        keywords=["XGK", "watchdog", "WDT", "scan", "LS ELECTRIC"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.LS_ELECTRIC,
        series="XGK",
        code="BATT_ERR",
        title="XGK 배터리 이상",
        category="POWER",
        likely_cause="XGK CPU 모듈 배터리 전압 저하 또는 배터리 미장착.",
        suggested_action="지정 규격의 배터리로 교체 후 메모리 데이터 재확인.",
        severity="WARNING",
        keywords=["XGK", "battery", "BATT", "LS ELECTRIC", "RAM backup"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.LS_ELECTRIC,
        series="XGK",
        code="IO_CONF_ERR",
        title="XGK I/O 구성 오류",
        category="IO",
        likely_cause="XGK 기저부에 장착된 모듈이 XG5000 프로젝트 I/O 파라미터와 불일치.",
        suggested_action="XG5000 I/O 파라미터를 실제 장착 모듈에 맞게 수정 후 재다운로드.",
        severity="FATAL",
        keywords=["XGK", "I/O", "configuration", "LS ELECTRIC", "XG5000"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.LS_ELECTRIC,
        series="XGK",
        code="PROG_ERR",
        title="XGK 프로그램 오류",
        category="PROGRAM",
        likely_cause="래더 프로그램 내 문법 오류, 잘못된 명령어 사용, 또는 END 명령 누락.",
        suggested_action="XG5000으로 오류 위치 확인 후 수정 및 재다운로드.",
        severity="FATAL",
        keywords=["XGK", "program", "error", "ladder", "LS ELECTRIC"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.LS_ELECTRIC,
        series="XGB",
        code="CPU_ERR",
        title="XGB CPU 이상",
        category="SYSTEM",
        likely_cause="XGB CPU 자기진단 실패 또는 내부 하드웨어 불량.",
        suggested_action="CPU 모듈 전원 재투입 후 지속 시 모듈 교체.",
        severity="FATAL",
        keywords=["XGB", "CPU", "error", "LS ELECTRIC"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.LS_ELECTRIC,
        series="XGB",
        code="WDT_ERR",
        title="XGB 워치독 타임아웃",
        category="WATCHDOG",
        likely_cause="XGB 스캔 처리 시간이 워치독 설정을 초과.",
        suggested_action="프로그램 처리 부하 감소, 워치독 설정 값 조정.",
        severity="FATAL",
        keywords=["XGB", "watchdog", "WDT", "scan", "LS ELECTRIC"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.LS_ELECTRIC,
        series="XGB",
        code="COMM_ERR",
        title="XGB 통신 오류",
        category="COMM",
        likely_cause="내장 시리얼 또는 Cnet 통신 포트의 응답 불량.",
        suggested_action="통신 파라미터(보레이트, 프로토콜) 재확인, 케이블 및 종단저항 점검.",
        severity="WARNING",
        keywords=["XGB", "communication", "serial", "Cnet", "LS ELECTRIC"],
        license="SELF_AUTHORED",
    ),

    # ── MITSUBISHI – iQ-R / FX general concepts ──────────────────────────────
    ErrorCode(
        vendor=Vendor.MITSUBISHI,
        series="iQ-R",
        code="WDT_ERR",
        title="iQ-R 워치독 오류",
        category="WATCHDOG",
        likely_cause="iQ-R CPU 스캔 시간이 워치독 타이머 설정을 초과.",
        suggested_action="GX Works3로 스캔 시간 확인 및 프로그램 최적화, 워치독 설정 재검토.",
        severity="FATAL",
        keywords=["iQ-R", "watchdog", "WDT", "Mitsubishi", "scan"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.MITSUBISHI,
        series="iQ-R",
        code="IO_VERIFY_ERR",
        title="iQ-R I/O 모듈 검증 오류",
        category="IO",
        likely_cause="실제 장착된 I/O 모듈이 파라미터로 설정된 모듈 정보와 불일치.",
        suggested_action="GX Works3 파라미터를 실제 구성에 맞게 수정 후 재쓰기.",
        severity="FATAL",
        keywords=["iQ-R", "I/O", "verify", "module", "Mitsubishi", "parameter"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.MITSUBISHI,
        series="iQ-R",
        code="BATT_ERR",
        title="iQ-R 배터리 오류",
        category="POWER",
        likely_cause="iQ-R CPU 모듈 배터리 전압 저하.",
        suggested_action="지정 배터리로 교체 후 프로그램·래치 데이터 재확인.",
        severity="WARNING",
        keywords=["iQ-R", "battery", "Mitsubishi", "RAM", "latch"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.MITSUBISHI,
        series="iQ-R",
        code="PARAM_ERR",
        title="iQ-R 파라미터 오류",
        category="PROGRAM",
        likely_cause="CPU 파라미터 설정값이 유효 범위를 벗어나거나 파라미터 파일 손상.",
        suggested_action="GX Works3로 파라미터 재확인 및 올바른 값으로 수정 후 재쓰기.",
        severity="FATAL",
        keywords=["iQ-R", "parameter", "error", "Mitsubishi", "GX Works3"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.MITSUBISHI,
        series="iQ-R",
        code="LINK_COMM_ERR",
        title="iQ-R 네트워크 링크 통신 오류",
        category="COMM",
        likely_cause="CC-Link IE 또는 MELSECNET 링크 모듈의 통신 이상(케이블 단선, 국번 중복).",
        suggested_action="네트워크 케이블·커넥터 점검, 국번 중복 제거, 링크 파라미터 재확인.",
        severity="WARNING",
        keywords=["iQ-R", "CC-Link", "MELSECNET", "link", "communication", "Mitsubishi"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.MITSUBISHI,
        series="FX",
        code="WDT_ERR",
        title="FX 시리즈 워치독 오류",
        category="WATCHDOG",
        likely_cause="FX CPU 스캔 시간 초과 또는 인터럽트 과부하.",
        suggested_action="프로그램 처리량 감소, GX Works2/Developer로 워치독 설정 재확인.",
        severity="FATAL",
        keywords=["FX", "watchdog", "WDT", "scan", "Mitsubishi"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.MITSUBISHI,
        series="FX",
        code="BATT_ERR",
        title="FX 배터리 저하",
        category="POWER",
        likely_cause="FX CPU 내장 배터리 전압 저하로 래치 데이터 보존 불가 상태.",
        suggested_action="FX 시리즈 호환 배터리로 즉시 교체.",
        severity="WARNING",
        keywords=["FX", "battery", "Mitsubishi", "latch", "backup"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.MITSUBISHI,
        series="FX",
        code="PROG_ERR",
        title="FX 프로그램/명령어 오류",
        category="PROGRAM",
        likely_cause="FX CPU가 실행할 수 없는 명령어 또는 피연산자 범위 초과.",
        suggested_action="GX Works2로 오류 스텝 확인 후 명령어 수정 및 재전송.",
        severity="FATAL",
        keywords=["FX", "program", "instruction", "error", "Mitsubishi"],
        license="SELF_AUTHORED",
    ),

    # ── SIEMENS – general S7 / SIMATIC concepts ──────────────────────────────
    ErrorCode(
        vendor=Vendor.SIEMENS,
        series="S7",
        code="OB_MISSING",
        title="필수 OB(조직 블록) 누락",
        category="PROGRAM",
        likely_cause="CPU가 이벤트 처리에 필요한 OB(예: OB 80 시간 오류)가 프로젝트에 없음.",
        suggested_action="TIA Portal로 해당 OB 추가 및 다운로드.",
        severity="FATAL",
        keywords=["S7", "OB", "organization block", "missing", "Siemens", "SIMATIC"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.SIEMENS,
        series="S7",
        code="CPU_STOP_PROG_ERR",
        title="프로그램 오류로 CPU STOP 전환",
        category="PROGRAM",
        likely_cause=(
            "런타임 프로그램 오류(잘못된 포인터, 접근 불가 DB 등)로 CPU가 STOP 상태로 전환."
        ),
        suggested_action="진단 버퍼 확인(TIA Portal / STEP 7), 오류 블록 수정 후 RUN 전환.",
        severity="FATAL",
        keywords=["S7", "CPU", "STOP", "program error", "diagnostic buffer", "Siemens"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.SIEMENS,
        series="S7",
        code="CYCLE_TIME_OVF",
        title="최대 사이클 시간 초과",
        category="WATCHDOG",
        likely_cause="OB1 실행 시간이 설정된 최대 사이클 시간 초과(기본 150ms).",
        suggested_action="OB1 처리량 감소 또는 최대 사이클 시간 파라미터 재설정.",
        severity="FATAL",
        keywords=["S7", "cycle time", "OB1", "watchdog", "overflow", "Siemens"],
        license="SELF_AUTHORED",
    ),

    # ── OMRON – general CJ/CP/NX concepts ────────────────────────────────────
    ErrorCode(
        vendor=Vendor.OMRON,
        series="CJ",
        code="WDT_ERR",
        title="CJ 시리즈 워치독 오류",
        category="WATCHDOG",
        likely_cause="CJ CPU 사이클 타임이 워치독 설정 이내에 완료되지 않음.",
        suggested_action="CX-Programmer로 사이클 모니터 확인, 프로그램 부하 감소.",
        severity="FATAL",
        keywords=["CJ", "watchdog", "WDT", "cycle", "Omron"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.OMRON,
        series="CJ",
        code="BATT_LOW",
        title="CJ 배터리 전압 저하",
        category="POWER",
        likely_cause="CJ CPU 모듈 배터리 전압이 하한값 이하로 저하.",
        suggested_action="CJ 호환 배터리로 교체, 교체 후 메모리 보존 상태 확인.",
        severity="WARNING",
        keywords=["CJ", "battery", "low", "Omron", "backup"],
        license="SELF_AUTHORED",
    ),
    ErrorCode(
        vendor=Vendor.OMRON,
        series="NX",
        code="IO_VERIFY_ERR",
        title="NX I/O 슬레이브 검증 오류",
        category="IO",
        likely_cause="NX 슬레이브 유닛 구성이 Sysmac Studio 프로젝트와 불일치.",
        suggested_action="Sysmac Studio로 실제 구성과 프로젝트를 동기화 후 재전송.",
        severity="FATAL",
        keywords=["NX", "I/O", "slave", "verify", "Omron", "Sysmac"],
        license="SELF_AUTHORED",
    ),
]

# 연구·실무 인용 기반 확장 지식베이스(error_kb)를 합류시킨다 — 같은 수집 원칙.
from app.error_kb import KB_ENTRIES  # noqa: E402  (스키마 정의 후 의도적 후행 임포트)

DB = ErrorCodeDB(SEED + KB_ENTRIES)
