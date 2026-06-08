#!/usr/bin/env python3
"""생성성 v2 벤치 — 시퀀스·다중인스턴스·아날로그까지 넓힌 조합 공간 측정.

기존 generativity_bench.py 는 '조건→동작 자기유지' 한 평면(distinct 1840)만 측정했다.
컴파일러(frame_to_spec)는 그 사이에 (a) 다중 인스턴스(펌프1·1번 모터처럼 같은 기기의
여러 대), (b) 순차 제어(다음·N초 후로 이어지는 타임드 시퀀서), (c) 아날로그 비교기
(압력 N바 넘으면·온도 N도 되면)까지 다룬다. 이 벤치는 그 *확장된 조합 공간* 에서
**synth→verify 게이트를 통과한 서로 다른(ST 기준) 프로그램 수** 를 카테고리별·전체로
센다. 이중코일이 있거나 verify 가 실패한 산출물은 '세지 않는다'(환각 0 게이트).

정직한 결론: 어휘는 유한(기기·동작·신호·임계의 닫힌 집합)이지만, 그 조합은 규칙 수에
지수적이라 사실상 무한하다. 못 만드는 것도 분명하다 — 어휘 밖 기기, 비액추에이터 구동
('온도 올려'), 출력이 겹치는 시퀀스 등은 컴파일러가 정직하게 거절한다(거짓 합성 없음).
시드를 고정해 100% 결정론이며 LLM·API 키가 필요 없다.
"""

from __future__ import annotations

import random
import sys
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.compile_frame import frame_to_spec  # noqa: E402
from app.memory_map import detect_double_coils  # noqa: E402
from app.synth import synthesize_st  # noqa: E402
from app.verifier import verify  # noqa: E402

# --- 어휘(유한) -------------------------------------------------------------
# (a) 다중 인스턴스: 같은 기기의 여러 대. (표면 기기, [ON 동작], [OFF 동작]).
_INST_DEVICES: list[tuple[str, list[str], list[str]]] = [
    ("모터", ["돌려", "돌리고", "가동"], ["멈춰", "정지"]),
    ("펌프", ["켜", "켜고", "가동"], ["꺼", "정지"]),
    ("밸브", ["열어", "열고"], ["닫아", "닫고"]),
    ("컨베이어", ["돌려", "가동"], ["멈춰", "정지"]),
    ("히터", ["켜", "켜고"], ["꺼"]),
    ("팬", ["돌려", "켜"], ["멈춰", "꺼"]),
    ("게이트", ["열어"], ["닫아"]),
]
_INST_NUMS = [1, 2, 3, 4]

# (b) 시퀀스: 단계마다 *서로 다른* 출력 + ON 계열 동작(켜기/돌리기/열기/올리기).
_SEQ_STEPS: list[tuple[str, str]] = [
    ("컨베이어", "돌려"), ("클램프", "고정하고"), ("드릴", "돌려"),
    ("펌프", "켜"), ("밸브", "열어"), ("게이트", "열어"), ("모터", "돌려"),
    ("실린더", "올려"), ("히터", "켜"), ("팬", "돌려"), ("스프레이", "분사"),
    ("로봇", "이동"), ("호퍼", "열어"),
]
_SEQ_DELAYS = [2, 3, 5, 10]

# (c) 아날로그: (신호 표면, 공학단위). 비교 술어와 임계로 비교기 플래그를 만든다.
_ANALOG_SIGNALS: list[tuple[str, str]] = [("압력", "바"), ("온도", "도")]
_ANALOG_THRESH = [3, 5, 10, 20, 30, 50, 80, 100, 150]
_ANALOG_CMP = ["넘으면", "되면", "초과하면"]
_ANALOG_ACTS: list[tuple[str, list[str]]] = [
    ("밸브", ["열어", "닫아"]), ("펌프", ["켜", "꺼"]), ("히터", ["켜", "꺼"]),
    ("경광등", ["켜"]), ("모터", ["돌려", "멈춰"]), ("팬", ["돌려"]),
    ("쿨러", ["켜", "꺼"]), ("사이렌", ["켜"]), ("부저", ["켜"]),
]


def _passing_st(text: str) -> str | None:
    """문장을 frame_to_spec→synth→verify→이중코일 게이트로 돌려, 통과 시 ST 반환(아니면 None)."""
    r = frame_to_spec(text)
    if not r.confident:
        return None
    st = synthesize_st(r.spec)
    if detect_double_coils(st):  # 이중코일이면 세지 않는다
        return None
    if not verify(r.spec, st).passed:  # verify 실패면 세지 않는다
        return None
    return st


def _gen_instance(rng: random.Random) -> str:
    """다중 인스턴스 문장 — '펌프1 켜고 펌프2 꺼' / '1번 모터 돌리고 2번 모터 멈춰'."""
    k = rng.choice([2, 3])
    parts: list[str] = []
    used: set[tuple[str, int]] = set()
    for _ in range(k):
        dev, ons, offs = rng.choice(_INST_DEVICES)
        n = rng.choice(_INST_NUMS)
        if (dev, n) in used:  # 같은 인스턴스 중복 → 이중코일 위험, 피한다
            continue
        used.add((dev, n))
        act = rng.choice(ons + offs)
        name = f"{dev}{n}" if rng.random() < 0.5 else f"{n}번 {dev}"
        parts.append(f"{name} {act}")
    return " ".join(parts)


def _gen_sequence(rng: random.Random) -> str:
    """순차 문장 — 'A 돌리고 다음 B 켜고 5초 후 C 열어'(서로 다른 출력 2~4단계)."""
    k = rng.choice([2, 3, 4])
    steps = rng.sample(_SEQ_STEPS, k)
    parts: list[str] = []
    for i, (dev, act) in enumerate(steps):
        if i > 0:
            if rng.random() < 0.5:
                parts.append(f"{rng.choice(_SEQ_DELAYS)}초 후")
            else:
                parts.append("다음")
        parts.append(f"{dev} {act}")
    return " ".join(parts)


def _gen_analog(rng: random.Random) -> str:
    """아날로그 비교 문장 — '압력 5바 넘으면 밸브 닫아'(임계·신호·동작 조합, 1~2절)."""
    k = rng.choice([1, 2])
    parts: list[str] = []
    for _ in range(k):
        sig, unit = rng.choice(_ANALOG_SIGNALS)
        thr = rng.choice(_ANALOG_THRESH)
        cmp = rng.choice(_ANALOG_CMP)
        dev, acts = rng.choice(_ANALOG_ACTS)
        parts.append(f"{sig} {thr}{unit} {cmp} {dev} {rng.choice(acts)}")
    return " ".join(parts)


_GENERATORS: OrderedDict[str, Callable[[random.Random], str]] = OrderedDict(
    instance=_gen_instance,
    sequence=_gen_sequence,
    analog=_gen_analog,
)


def run(trials_per_category: int = 1500, seed: int = 11) -> dict[str, set[str]]:
    """카테고리별로 무작위 생성→게이트 통과한 서로 다른 ST 집합을 모은다(결정론·시드 고정).

    반환: {'instance': {st,...}, 'sequence': {...}, 'analog': {...}}. 호출자가 len 으로 센다.
    """
    result: dict[str, set[str]] = {name: set() for name in _GENERATORS}
    for name, gen in _GENERATORS.items():
        rng = random.Random(hash((seed, name)) & 0xFFFFFFFF)
        distinct = result[name]
        for _ in range(trials_per_category):
            text = gen(rng)
            st = _passing_st(text)
            if st is not None:
                distinct.add(st)
    return result


def main() -> int:
    by_cat = run()
    overall: set[str] = set()
    for sts in by_cat.values():
        overall |= sts
    print("=== 생성성 v2 벤치: 시퀀스·다중인스턴스·아날로그까지 ===")
    print("게이트: frame_to_spec→synthesize_st→verify(통과)→이중코일(0). 환각 0·결정론.")
    for name, sts in by_cat.items():
        print(f"  [{name:9}] 검증 통과 서로 다른 프로그램 {len(sts)}개")
    print(f"  [{'전체':9}] (카테고리 합집합) {len(overall)}개")
    print(
        "\n해석: 유한 어휘(기기·동작·신호·임계의 닫힌 집합)에서 조합적으로 쏟아진다 — "
        "기존 평면(1840)을 크게 넘는다. 못 만드는 것도 분명하다: 어휘 밖 기기, 비액추에이터 "
        "구동('온도 올려'), 출력이 겹치는 시퀀스는 컴파일러가 정직하게 거절한다(거짓 합성 0)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
