"""패턴 라이브러리 (Phase L2) — 이름붙은 결정론 ST 템플릿.

학습(docs/research)에서 확인: 실무자는 이름붙은 패턴(자기유지·인터록·first-out·
모드 등)으로 사고하며, **LD 자유생성은 연구상 미해결**이다. 그래서 LLM 에 래더를
자유작성시키는 대신, 검증된 패턴 템플릿을 I/O 로 파라미터화해 **조립**한다.

각 빌더는 ``OUT := <불리언식>;`` 형태의 ST 문자열을 반환한다(트랜스파일러/검증기가
그대로 처리). 템플릿은 설계상 **이중코일 0**이며, 인터록 패턴은 상대 출력의 NOT 을
포함해 상호배제를 보장한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.boolexpr import parse  # 생성 ST 자체 검증용
from app.memory_map import detect_double_coils


# ---------------------------------------------------------------------------
# 패턴 빌더 (각각 ST 문자열 반환)
# ---------------------------------------------------------------------------
def seal_in(output: str, start: str, stop: str) -> str:
    """자기유지(seal-in): 시동으로 ON, 자기 접점으로 유지, 정지로 해제.

    stop 은 NC(b접점)로 배선해 단선 시 정지되게 한다(페일세이프).
    """
    return f"{output} := ({start} OR {output}) AND NOT {stop};"


def jog(jog_output: str, jog_button: str, run_output: str) -> str:
    """조그(모멘터리): 버튼을 누르는 동안만 ON, 연속운전과 상호배제."""
    return f"{jog_output} := {jog_button} AND NOT {run_output};"


def interlock_pair(
    output_a: str,
    start_a: str,
    output_b: str,
    start_b: str,
    stop: str,
) -> str:
    """상호배제 자기유지 쌍(정역 운전 등): 두 출력이 동시에 켜지지 않는다."""
    return (
        f"{output_a} := ({start_a} OR {output_a}) AND NOT {stop} AND NOT {output_b};\n"
        f"{output_b} := ({start_b} OR {output_b}) AND NOT {stop} AND NOT {output_a};"
    )


def hi_lo_level(pump: str, lo_switch: str, hi_switch: str) -> str:
    """수위 히스테리시스: 저수위에서 ON, 고수위에서 OFF(쌍안정)."""
    return f"{pump} := ({lo_switch} OR {pump}) AND NOT {hi_switch};"


def mode_select(
    output: str,
    mode_auto: str,
    auto_cmd: str,
    manual_cmd: str,
    stop: str,
) -> str:
    """자동/수동 모드 선택: mode_auto 가 TRUE 면 자동, FALSE 면 수동 명령으로 구동."""
    return (
        f"{output} := (({mode_auto} AND {auto_cmd}) "
        f"OR (NOT {mode_auto} AND {manual_cmd})) AND NOT {stop};"
    )


def flasher(lamp: str, clock: str, enable: str) -> str:
    """점멸(플리커): 클록 펄스(타이머 구동)와 enable 의 AND."""
    return f"{lamp} := {clock} AND {enable};"


def first_out_alarm(
    latch_a: str,
    fault_a: str,
    latch_b: str,
    fault_b: str,
    reset: str,
) -> str:
    """최초고장(first-out): 먼저 난 고장만 래치되고 다른 쪽은 잠금(lock-out)."""
    return (
        f"{latch_a} := ({fault_a} AND NOT {latch_b} OR {latch_a}) "
        f"AND NOT ({reset} AND NOT {fault_a});\n"
        f"{latch_b} := ({fault_b} AND NOT {latch_a} OR {latch_b}) "
        f"AND NOT ({reset} AND NOT {fault_b});"
    )


def star_delta(
    main: str,
    star: str,
    delta: str,
    start: str,
    stop: str,
    timer_done: str,
) -> str:
    """스타-델타 기동: 주접촉기 자기유지, 타이머 완료 시 스타→델타 전환(상호배제)."""
    return (
        f"{main} := ({start} OR {main}) AND NOT {stop};\n"
        f"{star} := {main} AND NOT {timer_done} AND NOT {delta};\n"
        f"{delta} := {main} AND {timer_done} AND NOT {star};"
    )


# ---------------------------------------------------------------------------
# 레지스트리
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Pattern:
    """패턴 메타데이터 + 빌더."""

    name: str
    summary: str
    params: tuple[str, ...]
    build: Callable[..., str]


PATTERNS: dict[str, Pattern] = {
    "seal_in": Pattern(
        "seal_in", "자기유지(시동/유지/정지)", ("output", "start", "stop"), seal_in
    ),
    "jog": Pattern(
        "jog", "조그(모멘터리, 연속운전과 배타)",
        ("jog_output", "jog_button", "run_output"), jog
    ),
    "interlock_pair": Pattern(
        "interlock_pair", "상호배제 자기유지 쌍(정역 등)",
        ("output_a", "start_a", "output_b", "start_b", "stop"), interlock_pair
    ),
    "hi_lo_level": Pattern(
        "hi_lo_level", "수위 히스테리시스(쌍안정)",
        ("pump", "lo_switch", "hi_switch"), hi_lo_level
    ),
    "mode_select": Pattern(
        "mode_select", "자동/수동 모드 선택",
        ("output", "mode_auto", "auto_cmd", "manual_cmd", "stop"), mode_select
    ),
    "flasher": Pattern(
        "flasher", "점멸(클록 AND enable)", ("lamp", "clock", "enable"), flasher
    ),
    "first_out_alarm": Pattern(
        "first_out_alarm", "최초고장 래치(lock-out)",
        ("latch_a", "fault_a", "latch_b", "fault_b", "reset"), first_out_alarm
    ),
    "star_delta": Pattern(
        "star_delta", "스타-델타 기동(상호배제)",
        ("main", "star", "delta", "start", "stop", "timer_done"), star_delta
    ),
}


def available_patterns() -> list[str]:
    """등록된 패턴 이름 목록."""
    return list(PATTERNS)


def build_pattern(name: str, **params: str) -> str:
    """패턴 이름 + 파라미터로 ST 를 생성한다."""
    return PATTERNS[name].build(**params)


def compose(*snippets: str) -> str:
    """여러 패턴 ST 를 합치고 교차 이중코일을 검사한다.

    합친 결과에 이중코일이 있으면 ValueError(설계 오류 — 같은 출력을 두 패턴이 구동).
    """
    code = "\n".join(s for s in snippets if s.strip())
    dups = detect_double_coils(code)
    if dups:
        raise ValueError(f"패턴 조립 중 이중코일 발생: {', '.join(dups)}")
    # 생성 ST 의 각 우변이 파싱 가능한지 자체 검증
    for line in code.splitlines():
        if ":=" in line:
            _, expr = line.split(":=", 1)
            parse(expr.rstrip(";").strip())
    return code
