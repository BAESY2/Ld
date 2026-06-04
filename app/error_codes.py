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


# 사람이 검토·승인한 시드(사실 데이터 + 자체 요약). 매뉴얼 본문 복제 아님.
SEED: list[ErrorCode] = [
    ErrorCode(
        vendor=Vendor.GENERIC,
        code="WDT",
        title="워치독 타임아웃",
        category="WATCHDOG",
        likely_cause="스캔 시간이 설정 한계를 초과(무한 루프/과도한 연산).",
        suggested_action="스캔 부하 분산, 루프 종료 조건 점검, 워치독 설정 확인.",
        license="SELF_AUTHORED",
    ),
]

DB = ErrorCodeDB(SEED)
