"""프로젝트 합성 — 서브시스템 N개를 하나의 결정론 명세로 조립한다.

대규모 설계의 핵심 격차 해소: 기존 ``build_spec(recipe)`` 는 서브시스템 1개만
만든다. 이 모듈은 여러 모듈 인스턴스(컨베이어3 + 펌프2 + 알람1 …)를

  1. **네임스페이스 분리**(모듈마다 심볼·타이머·카운터·상태 이름에 프리픽스) 로
     충돌 없이 나란히 놓고,
  2. **공유 심볼**(shared 매핑) 으로 공통 입력(예: 마스터 비상정지)을 묶고,
  3. **교차 인터락**(CrossInterlock) 으로 모듈 사이 상호배타를 선언

해 하나의 ``StateMachineSpec`` 으로 합친다. 합쳐진 명세는 기존 파이프라인
(synth → verify → 래더 → 에미터)을 그대로 탄다.

설계 원칙(CLAUDE.md): 합성은 100% 결정론·테스트가능. LLM 은 자연어→프로젝트
구조(모듈 선택+바인딩)만 담당하고, 조립 자체에는 환각이 끼어들 수 없다. 전역
이중코일 0 은 네임스페이스로 *구조적으로* 보장되며, 공유 출력 오용은 검증기가 잡는다.
"""

from __future__ import annotations

import re

from app.models import (
    CounterSpec,
    DerivedOutput,
    Interlock,
    IOPoint,
    ModuleInstance,
    Project,
    SfcState,
    StateMachineSpec,
    TimerSpec,
    Transition,
)
from app.wizard import WizardError, build_spec

_NAME_RE = re.compile(r"^[A-Za-z_]\w*$")


class ProjectError(ValueError):
    """프로젝트 합성 단계의 친절한 오류(비전문가 노출용)."""


def _owned_names(spec: StateMachineSpec) -> list[str]:
    """모듈이 소유한(=네임스페이스 대상) 식별자 목록. 길이 내림차순(부분일치 방지)."""
    names: set[str] = set()
    for io in spec.io_points:
        names.add(io.symbol)
    for t in spec.timers:
        names.add(t.name)
    for c in spec.counters:
        names.add(c.name)
    for s in spec.states:
        names.add(s.name)
    # 긴 이름부터 치환해야 안전(정규식 \b 가 _ 를 단어문자로 보므로 부분일치는 없지만,
    # 결정론적 순서 보장 차원에서 정렬).
    return sorted(names, key=lambda n: (-len(n), n))


def _build_mapping(module: ModuleInstance, owned: list[str]) -> dict[str, str]:
    """로컬 식별자 → 렌더 식별자. shared 에 있으면 전역 이름, 아니면 ``name__local``."""
    mapping: dict[str, str] = {}
    for local in owned:
        if local in module.shared:
            mapping[local] = module.shared[local]
        else:
            mapping[local] = f"{module.name}__{local}"
    return mapping


def _rename_expr(expr: str, mapping: dict[str, str]) -> str:
    """불리언/ST 식 안의 *소유 식별자* 토큰만 통째로(whole-word) 치환한다.

    ``T1.Q`` 의 ``T1`` 처럼 ``.`` 앞 토큰도 \\b 경계로 잡힌다. 매핑에 없는 토큰
    (AND/OR/NOT/TRUE/FALSE·공유 안 된 심볼)은 그대로 둔다.
    """
    if not expr or not mapping:
        return expr
    keys = sorted(mapping, key=lambda n: (-len(n), n))
    pattern = re.compile(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b")
    return pattern.sub(lambda m: mapping[m.group(1)], expr)


def _rename_spec(spec: StateMachineSpec, mapping: dict[str, str]) -> StateMachineSpec:
    """매핑대로 명세 전체를 새 인스턴스로 리네임(원본 불변)."""

    def mp(name: str) -> str:
        return mapping.get(name, name)

    return StateMachineSpec(
        title=spec.title,
        io_points=[
            IOPoint(
                symbol=mp(io.symbol),
                direction=io.direction,
                data_type=io.data_type,
                device_class=io.device_class,
                description=io.description,
                fixed_address=io.fixed_address,
            )
            for io in spec.io_points
        ],
        timers=[
            TimerSpec(
                name=mp(t.name),
                timer_type=t.timer_type,
                preset_ms=t.preset_ms,
                enable_condition=_rename_expr(t.enable_condition, mapping),
                description=t.description,
            )
            for t in spec.timers
        ],
        counters=[
            CounterSpec(
                name=mp(c.name),
                counter_type=c.counter_type,
                preset=c.preset,
                count_condition=_rename_expr(c.count_condition, mapping),
                reset_condition=_rename_expr(c.reset_condition, mapping),
                description=c.description,
            )
            for c in spec.counters
        ],
        states=[
            SfcState(
                name=mp(s.name),
                is_initial=s.is_initial,
                on_entry=[_rename_expr(stmt, mapping) for stmt in s.on_entry],
                description=s.description,
            )
            for s in spec.states
        ],
        transitions=[
            Transition(
                from_state=mp(tr.from_state),
                to_state=mp(tr.to_state),
                condition=_rename_expr(tr.condition, mapping),
                description=tr.description,
            )
            for tr in spec.transitions
        ],
        interlocks=[
            Interlock(output_a=mp(il.output_a), output_b=mp(il.output_b), reason=il.reason)
            for il in spec.interlocks
        ],
        derived_outputs=[
            DerivedOutput(
                output=mp(d.output),
                expression=_rename_expr(d.expression, mapping),
                description=d.description,
            )
            for d in spec.derived_outputs
        ],
    )


def _resolve_ref(ref: str, mappings: dict[str, dict[str, str]]) -> str:
    """교차 인터락의 ``"모듈.심볼"`` 또는 공유 심볼을 렌더 심볼로 해석한다."""
    ref = ref.strip()
    if "." in ref:
        mod, _, local = ref.partition(".")
        if mod not in mappings:
            raise ProjectError(
                f"교차 인터락이 모르는 모듈 '{mod}' 을(를) 가리킵니다. "
                f"정의된 모듈: {', '.join(sorted(mappings)) or '(없음)'}"
            )
        mapping = mappings[mod]
        if local not in mapping:
            raise ProjectError(
                f"모듈 '{mod}' 에 심볼 '{local}' 이(가) 없습니다. "
                f"있는 심볼: {', '.join(sorted(mapping)) or '(없음)'}"
            )
        return mapping[local]
    # 점이 없으면 공유 전역 심볼로 간주(그대로 사용).
    return ref


def compose(project: Project) -> StateMachineSpec:
    """프로젝트(모듈 N개 + 교차 인터락)를 하나의 StateMachineSpec 으로 합성한다.

    각 모듈을 ``build_spec`` 으로 만든 뒤 네임스페이스로 리네임해 이어붙이고,
    교차 인터락을 실제 렌더 심볼로 해석해 interlocks 에 합친다. 반환 명세는
    그대로 synth/verify/래더 파이프라인에 넣을 수 있다.
    """
    if not project.modules:
        raise ProjectError("프로젝트에 모듈이 하나도 없습니다.")

    seen: set[str] = set()
    merged = StateMachineSpec(title=project.title)
    mappings: dict[str, dict[str, str]] = {}

    for module in project.modules:
        if not _NAME_RE.match(module.name):
            raise ProjectError(
                f"모듈 이름 '{module.name}' 은(는) 쓸 수 없어요. 영문으로 시작하고 "
                "영문·숫자·밑줄(_)만 쓰세요(예: conv1, tankA)."
            )
        if module.name in seen:
            raise ProjectError(f"모듈 이름 '{module.name}' 이(가) 중복됩니다.")
        seen.add(module.name)

        if module.spec is not None:
            # 인라인 명세(LLM 설계 산출물 등) — 템플릿을 거치지 않는 일반 IR 경로.
            # 깊은 복사로 원본 보호(이후 리네임이 새 인스턴스에만 적용되도록).
            sub = module.spec.model_copy(deep=True)
        else:
            try:
                sub = build_spec(module.recipe, module.answers)
            except KeyError as exc:
                raise ProjectError(
                    f"모듈 '{module.name}' 의 레시피 '{module.recipe}' 를 찾을 수 없습니다."
                ) from exc
            except WizardError as exc:
                raise ProjectError(f"모듈 '{module.name}' 입력 오류: {exc}") from exc

        mapping = _build_mapping(module, _owned_names(sub))
        mappings[module.name] = mapping
        renamed = _rename_spec(sub, mapping)

        merged.io_points.extend(renamed.io_points)
        merged.timers.extend(renamed.timers)
        merged.counters.extend(renamed.counters)
        merged.states.extend(renamed.states)
        merged.transitions.extend(renamed.transitions)
        merged.interlocks.extend(renamed.interlocks)
        merged.derived_outputs.extend(renamed.derived_outputs)

    for ci in project.cross_interlocks:
        a = _resolve_ref(ci.output_a, mappings)
        b = _resolve_ref(ci.output_b, mappings)
        if a == b:
            raise ProjectError(
                f"교차 인터락 두 출력이 같은 심볼({a})로 해석됩니다. 서로 달라야 합니다."
            )
        merged.interlocks.append(
            Interlock(output_a=a, output_b=b, reason=ci.reason or "교차 인터락")
        )

    return merged
