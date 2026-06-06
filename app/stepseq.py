"""정수 스텝-레지스터 시퀀서 합성기 (결정론 코어, PLAN.md Phase M).

순차 기계(신호등, 배치 충진→교반→배출, 세차)처럼 "한 번에 한 스텝만 활성"이
자기유지(seal-in) 체인보다 깔끔하고 진단이 쉬운 경우를 위한 *대안* 합성 모드.

설계 결정 — 왜 정수 STEP 이 아니라 **불리언 one-hot 스텝 벡터**인가:
  app/simulator.py 와 app/boolexpr.py 는 불리언식(AND/OR/NOT/Var/Const)만
  평가한다 — 정수 비교(`STEP = 2`)·산술 대입을 파싱·실행할 수 없다. 따라서
  정수 STEP 레지스터를 그대로 ST 로 내면 시뮬레이터가 가동하지 못한다. 대신
  스텝마다 BOOL 플래그 1개(``S0, S1, ...``)를 두고, *구조적으로 one-hot* 이
  보장되도록 합성한다 → 출력은 ``OUT := S2 OR S5;`` 같은 단일 대입(이중코일 0).

스캔 순서 독립성 — 시뮬레이터는 대입을 위→아래 1패스로 평가하므로, 스텝식이
서로의 *직전* 값을 봐야 한다. 그래서 스캔 머리에서 모든 스텝 플래그를 스냅샷
(``_PREV_Sx``)으로 떠 두고, 스텝식은 스냅샷만 참조한다. 이렇게 하면 평가 순서가
출력에 영향을 주지 않고(시뮬레이터의 permutation-invariant 검사와 일치), one-hot
이 매 스캔 보존된다.

초기 스텝 부팅 — 시뮬레이터는 구동 심볼을 첫 스캔에 모두 False 로 둔다. 전원투입
래치 ``_BOOT`` 를 스냅샷으로 떠, 첫 스캔(``_PREV_BOOT`` 가 False)에서만 초기
스텝을 강제 ON 한다.
"""

from __future__ import annotations

from app.boolexpr import parse
from app.models import IODirection, StateMachineSpec

# on_entry 의 `OUT := TRUE;` 매칭은 synth.py 와 동일 규약을 따른다(중복 정의 회피).
from app.synth import _SET_TRUE_RE


def _state_names(spec: StateMachineSpec) -> list[str]:
    """명세 정의 순서의 상태 이름(중복 제거)."""
    seen: set[str] = set()
    names: list[str] = []
    for s in spec.states:
        if s.name not in seen:
            seen.add(s.name)
            names.append(s.name)
    return names


def _initial_state(spec: StateMachineSpec) -> str | None:
    """초기 상태 이름. is_initial=True 가 있으면 그것, 없으면 첫 상태."""
    for s in spec.states:
        if s.is_initial:
            return s.name
    names = _state_names(spec)
    return names[0] if names else None


def _step_flag(index: int) -> str:
    """스텝 인덱스 → one-hot BOOL 플래그 심볼(M 릴레이 성격)."""
    return f"STEP_S{index}"


def _outputs_on(spec: StateMachineSpec, state_name: str) -> list[str]:
    """state_name 의 on_entry 가 `OUT := TRUE;` 로 켜는 출력들(등장 순서)."""
    outs: list[str] = []
    for s in spec.states:
        if s.name != state_name:
            continue
        for stmt in s.on_entry:
            m = _SET_TRUE_RE.match(stmt)
            if m and m.group(1) not in outs:
                outs.append(m.group(1))
    return outs


def _output_symbols(spec: StateMachineSpec) -> list[str]:
    """OUTPUT 방향 IO 심볼(정의 순서, 중복 제거)."""
    seen: set[str] = set()
    out: list[str] = []
    for io in spec.io_points:
        if io.direction == IODirection.OUTPUT and io.symbol not in seen:
            seen.add(io.symbol)
            out.append(io.symbol)
    return out


def is_sequential(spec: StateMachineSpec) -> bool:
    """이 명세가 스텝-시퀀서로 합성하기에 적합한가(선형 체인 판정).

    적합 기준(보수적):
      - 상태가 2개 이상 존재한다.
      - 각 상태에서 *나가는* 전이가 최대 1개(분기 없음 — 결정적 진행).
      - 모든 전이 조건이 불리언식으로 파싱된다.
      - 모든 전이의 from/to 가 실재 상태다.
    분기(같은 from 에서 2개 이상 출구)나 비파싱 조건이 있으면 False —
    그 경우 기존 seal-in 합성(synth.synthesize_st)을 쓰는 편이 안전하다.
    """
    names = set(_state_names(spec))
    if len(names) < 2:
        return False
    out_degree: dict[str, int] = {}
    for tr in spec.transitions:
        if tr.from_state not in names or tr.to_state not in names:
            return False
        try:
            parse(tr.condition)
        except ValueError:
            return False
        out_degree[tr.from_state] = out_degree.get(tr.from_state, 0) + 1
        if out_degree[tr.from_state] > 1:
            return False
    return True


# 합성 보조 심볼(M 릴레이 성격). 출력·입력 심볼과 충돌하지 않도록 접두사 규약 사용.
_BOOT = "STEP_BOOT"


def _prev(sym: str) -> str:
    return f"STEP_PREV_{sym}"


def synthesize_step_st(spec: StateMachineSpec) -> str:
    """명세를 정수 스텝-레지스터(불리언 one-hot 벡터) ST 로 결정론 합성한다.

    구조(스캔 순서 독립·이중코일 0):
      1) 스냅샷:   _PREV_Si := Si;  _PREV_BOOT := BOOT;
      2) 부팅래치: BOOT := TRUE;
      3) 스텝식:   Si := <부팅(초기스텝만)> OR <유지> OR <진입>;  (스냅샷만 참조)
      4) 타이머/카운터 FB 호출(있으면)
      5) 출력:     OUT := <OUT 을 켜는 스텝 플래그들의 OR>;
    """
    names = _state_names(spec)
    if not names:
        raise ValueError("상태가 없는 명세는 스텝-시퀀서로 합성할 수 없습니다.")
    index = {name: i for i, name in enumerate(names)}
    initial = _initial_state(spec)
    if initial is None:  # pragma: no cover - names 비어있지 않으면 항상 존재
        raise ValueError("초기 상태를 결정할 수 없습니다.")

    # 전이 조건 조기 검증(다운스트림 크래시 방지) — synth.py 와 동일 정책.
    for tr in spec.transitions:
        parse(tr.condition)

    # ── 1) 스냅샷 블록 ────────────────────────────────────────────────
    snap_lines: list[str] = ["// 스텝 스냅샷(스캔 순서 독립)"]
    for i in range(len(names)):
        s = _step_flag(i)
        snap_lines.append(f"{_prev(s)} := {s};")
    snap_lines.append(f"{_prev(_BOOT)} := {_BOOT};")

    # ── 2) 부팅 래치 ──────────────────────────────────────────────────
    boot_lines = ["// 전원투입 래치", f"{_BOOT} := TRUE;"]

    # ── 3) 스텝식 블록(스냅샷만 참조 → one-hot 보존) ──────────────────
    step_lines: list[str] = ["// one-hot 스텝 벡터"]
    for i, name in enumerate(names):
        flag = _step_flag(i)
        prev_flag = _prev(flag)
        # 이 스텝에서 나가는 전이 조건(OR) = 유지 해제 조건
        exits = [tr.condition for tr in spec.transitions if tr.from_state == name]
        # 이 스텝으로 들어오는 전이 = 진입(소스 스냅샷 AND 조건)
        enters = [
            f"({_prev(_step_flag(index[tr.from_state]))} AND ({tr.condition}))"
            for tr in spec.transitions
            if tr.to_state == name
        ]
        terms: list[str] = []
        if name == initial:
            # 첫 스캔(직전 BOOT=False)에만 초기 스텝 강제 ON.
            terms.append(f"(NOT {_prev(_BOOT)})")
        # 유지: 직전 활성 AND 나가는 조건 없음
        hold = prev_flag
        if exits:
            off = " OR ".join(f"({c})" for c in exits)
            hold = f"({prev_flag} AND NOT ({off}))"
        terms.append(hold)
        terms.extend(enters)
        rhs = " OR ".join(terms)
        step_lines.append(f"{flag} := {rhs};")

    # ── 4) FB 호출(타이머/카운터) — synth 와 동일 포맷 재사용 ─────────
    from app.synth import synthesize_fb_calls

    fb_lines = synthesize_fb_calls(spec)

    # ── 5) 출력 블록(상태구동 출력만, 단일 대입) ──────────────────────
    out_lines: list[str] = []
    for out in _output_symbols(spec):
        active = [
            _step_flag(index[name])
            for name in names
            if out in _outputs_on(spec, name)
        ]
        if not active:
            continue  # 상태구동 아님(조합 출력) → 이 모드는 덮지 않음
        if not out_lines:
            out_lines.append("// 출력(활성 스텝의 OR)")
        out_lines.append(f"{out} := {' OR '.join(active)};")

    blocks: list[str] = [
        "\n".join(snap_lines),
        "\n".join(boot_lines),
        "\n".join(step_lines),
    ]
    if fb_lines:
        blocks.append("\n".join(fb_lines))
    if out_lines:
        blocks.append("\n".join(out_lines))
    return "\n\n".join(blocks)


def step_driven_outputs(spec: StateMachineSpec) -> set[str]:
    """스텝-시퀀서 모드가 덮는(상태 on_entry 구동) 출력 집합."""
    names = _state_names(spec)
    out: set[str] = set()
    for o in _output_symbols(spec):
        if any(o in _outputs_on(spec, name) for name in names):
            out.add(o)
    return out
