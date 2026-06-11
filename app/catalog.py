"""PLC 기종 카탈로그 + 설계 적합성 검사 (결정론, 의존성 없음).

제조사별 대표 CPU 모델의 공개 사양 요약(개략치)과, 설계(spec+ladder)가 해당
기종 한계(I/O 점수·프로그램 용량·타이머/카운터 수) 안에 들어가는지 검사한다.

⚠ 수치는 공개 카탈로그 요약(개략)이며 납품 전 반드시 제조사 데이터시트로
확인할 것. source 는 제조사 제품 페이지(시리즈 단위) URL.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import LadderProgram, StateMachineSpec

# 래더 스텝 추정 가중치(접점 1·코일 2·FB 3) — 벤더 IL 변환 시 대략치
_W_CONTACT = 1
_W_COIL = 2
_W_FB = 3


@dataclass(frozen=True)
class CpuModel:
    vendor: str          # "LS" | "MITSUBISHI" | "SIEMENS" | "OMRON"
    series: str          # 예: "XGK"
    model: str           # 예: "XGK-CPUH"
    dio_max: int         # 최대 디지털 I/O 점수(증설 포함, 개략)
    steps_k: int | None  # 프로그램 용량(K스텝, 개략) — 바이트 표기 기종은 None
    capacity: str        # 표기 그대로의 용량 문자열
    timers_max: int | None
    counters_max: int | None
    comm: tuple[str, ...]
    profile: str | None  # app.vendors 프로파일명(주소 체계 연동)
    source: str


CATALOG: tuple[CpuModel, ...] = (
    # ── LS ELECTRIC ─────────────────────────────────────────────
    CpuModel("LS", "XGK", "XGK-CPUE", 1536, 32, "32K 스텝", 2048, 2048,
             ("RS-232C", "USB"), "LS_XGK",
             "https://www.ls-electric.com/products/category/Automation/PLC"),
    CpuModel("LS", "XGK", "XGK-CPUH", 6144, 64, "64K 스텝", 2048, 2048,
             ("RS-232C", "USB", "Ethernet(옵션)"), "LS_XGK",
             "https://www.ls-electric.com/products/category/Automation/PLC"),
    CpuModel("LS", "XGB", "XBC-DR32H", 384, 15, "15K 스텝", 256, 256,
             ("RS-232C", "RS-485"), "LS_XGK",
             "https://www.ls-electric.com/products/category/Automation/PLC"),
    CpuModel("LS", "XGI", "XGI-CPUU", 6144, None, "1MB(IEC)", 2048, 2048,
             ("USB", "Ethernet(옵션)"), "LS_XGI",
             "https://www.ls-electric.com/products/category/Automation/PLC"),
    # ── MITSUBISHI ──────────────────────────────────────────────
    CpuModel("MITSUBISHI", "FX5U", "FX5U-32MR/ES", 512, 64, "64K 스텝", 1024, 1024,
             ("RS-485", "Ethernet"), "MITSUBISHI_FX",
             "https://www.mitsubishielectric.com/fa/products/cnt/plc/"),
    CpuModel("MITSUBISHI", "Q", "Q03UDECPU", 4096, 30, "30K 스텝", 2048, 1024,
             ("USB", "Ethernet"), "MITSUBISHI_FX",
             "https://www.mitsubishielectric.com/fa/products/cnt/plc/"),
    CpuModel("MITSUBISHI", "iQ-R", "R04CPU", 4096, 40, "40K 스텝", 2048, 1024,
             ("USB", "Ethernet"), "MITSUBISHI_FX",
             "https://www.mitsubishielectric.com/fa/products/cnt/plc/"),
    # ── SIEMENS ─────────────────────────────────────────────────
    CpuModel("SIEMENS", "S7-1200", "CPU 1212C", 282, None, "100KB", None, None,
             ("PROFINET",), None,
             "https://www.siemens.com/global/en/products/automation/systems/industrial/plc/s7-1200.html"),
    CpuModel("SIEMENS", "S7-1200", "CPU 1214C", 284, None, "125KB", None, None,
             ("PROFINET",), None,
             "https://www.siemens.com/global/en/products/automation/systems/industrial/plc/s7-1200.html"),
    CpuModel("SIEMENS", "S7-1500", "CPU 1515-2 PN", 8192, None, "500KB+3MB", None, None,
             ("PROFINET×2",), None,
             "https://www.siemens.com/global/en/products/automation/systems/industrial/plc/simatic-s7-1500.html"),
    # ── OMRON ───────────────────────────────────────────────────
    CpuModel("OMRON", "CP1L", "CP1L-EM30", 150, 10, "10K 스텝", 256, 256,
             ("USB", "Ethernet"), "OMRON_CJ",
             "https://www.ia.omron.com/products/category/automation-systems/programmable-controllers/"),
    CpuModel("OMRON", "CJ2M", "CJ2M-CPU31", 2560, 60, "60K 스텝", 4096, 4096,
             ("USB", "Ethernet"), "OMRON_CJ",
             "https://www.ia.omron.com/products/category/automation-systems/programmable-controllers/"),
    CpuModel("OMRON", "NX1P2", "NX1P2-1140DT", 256, None, "1.5MB(IEC)", None, None,
             ("EtherCAT", "EtherNet/IP"), "OMRON_NX",
             "https://www.ia.omron.com/products/category/automation-systems/programmable-controllers/"),
)


def list_models(vendor: str | None = None) -> list[CpuModel]:
    """카탈로그 조회(벤더 필터 선택)."""
    if vendor is None:
        return list(CATALOG)
    v = vendor.upper()
    return [m for m in CATALOG if m.vendor == v]


def estimate_steps(ladder: LadderProgram) -> int:
    """래더 → 벤더 IL 변환 시 프로그램 스텝 수 개략 추정."""
    steps = 0
    for rung in ladder.rungs:
        for branch in rung.input_branches:
            steps += _W_CONTACT * len(branch.elements)
        for out in rung.outputs:
            et = out.element_type.value if hasattr(out.element_type, "value") else out.element_type
            steps += _W_FB if et in ("TIMER", "COUNTER") else _W_COIL
    return steps


def check_fit(
    spec: StateMachineSpec, ladder: LadderProgram, model: CpuModel
) -> list[str]:
    """설계가 기종 한계 안인지 검사 — 위반 메시지 목록(빈 리스트=적합)."""
    issues: list[str] = []
    io_n = len(spec.io_points)
    if io_n > model.dio_max:
        issues.append(f"I/O {io_n}점 > {model.model} 최대 {model.dio_max}점")
    timers = sum(
        1 for r in ladder.rungs for o in r.outputs
        if (o.element_type.value if hasattr(o.element_type, "value") else o.element_type)
        == "TIMER"
    )
    counters = sum(
        1 for r in ladder.rungs for o in r.outputs
        if (o.element_type.value if hasattr(o.element_type, "value") else o.element_type)
        == "COUNTER"
    )
    if model.timers_max is not None and timers > model.timers_max:
        issues.append(f"타이머 {timers}개 > 최대 {model.timers_max}개")
    if model.counters_max is not None and counters > model.counters_max:
        issues.append(f"카운터 {counters}개 > 최대 {model.counters_max}개")
    if model.steps_k is not None:
        est = estimate_steps(ladder)
        if est > model.steps_k * 1000:
            issues.append(f"추정 {est}스텝 > 용량 {model.capacity}")
    return issues


def suggest(
    spec: StateMachineSpec, ladder: LadderProgram, vendor: str | None = None
) -> CpuModel | None:
    """적합한 최소 기종 제안(카탈로그 순서 = 시리즈 내 저가→고가 개략)."""
    for m in list_models(vendor):
        if not check_fit(spec, ladder, m):
            return m
    return None
