#!/usr/bin/env python3
"""end-to-end 증거 데모 — 한국어 한 문장이 *전 파이프라인*을 통과해 검증된 래더가 된다.

"AI 없이 한국어 이해 → 정형검증된 제어" 를 사람이 읽는 재현 가능한 전사(transcript)로
보여준다. 각 문장마다 6단계를 차례로 출력한다(전부 결정론·키 불필요):

  (a) 형태소 분석   : korean.analyze — 인식 형태소·coverage
  (b) 의도 프레임   : intent.extract — explain() '이해 내용' + 확신도(certainty)
  (c) 레시피 매핑   : intent.match_by_frame — 구조 특징 기반 레시피 선택
  (d) 합성 ST       : synth.synthesize_st + detect_double_coils(=0 이어야 함)
  (e) 정형검증      : verifier.verify — passed + proven_safe_pairs(k-귀납 증명 쌍)
  (f) 래더          : transpiler.transpile_st — 렁/접점 요약

정직 규율: 확신 미달(certainty<0.8)이거나 도메인 밖(레시피 매핑 실패) 문장은 거짓
래더를 만들지 않고 **'보류(HELD)'** 로 표시한다 — 환각 0.

이 스크립트는 app/ 모듈을 *호출만* 한다(읽기·실행 전용, 수정 없음).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.intent import IntentFrame, extract, match_by_frame
from app.korean import Pos, analyze
from app.memory_map import DeviceAllocator, detect_double_coils
from app.models import ElementType, LadderProgram, StateMachineSpec
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.verifier import proven_safe_pairs, verify
from app.wizard import RECIPES, build_spec

# 확신 임계값 — IntentFrame.confident 와 동일 기준(certainty>=0.8 + 동작 존재).
CONFIDENCE_THRESHOLD = 0.8

# 현장형 데모 문장(정상 + 띄어쓰기 없는 변형 + 비확신/도메인 밖 보류).
DEMO_SENTENCES: tuple[str, ...] = (
    "모터를 돌려",                              # 기본: 기동(자기유지)
    "컨베이어를 멈춰",                          # 정지
    "부품10개세면배출해",                       # 띄어쓰기 없는 run-on (현장 메모/STT)
    "저수위가 되면 펌프를 켜고 고수위가 되면 꺼라",  # 다절 조건→동작(수위 히스테리시스)
    "압력이 5바 넘으면 펌프 켜",                 # 아날로그 비교(압력 밴드)
    "셔터 열고 닫아",                           # 인터락(개·폐 동시금지) → 증명 쌍
    "펌프 켜고 3초 후 모터 돌리고 다음 밸브 열어",  # 시퀀스/타이밍 → 타임드 시퀀서
    "1번 모터 돌리고 2번 모터 멈춰",             # 다중 인스턴스 → MOTOR1/MOTOR2
    "오늘 점심 뭐 먹지",                        # 도메인 밖 → 보류
)


@dataclass(frozen=True)
class DemoResult:
    """한 문장의 파이프라인 결과(테스트가 단정에 쓰는 기계판독 요약)."""

    text: str
    coverage: float
    certainty: float
    confident: bool
    recipe_id: str | None
    recipe_score: float
    held: bool                      # 보류(거짓 생성 금지) 여부
    hold_reason: str = ""
    double_coils: int = 0
    verify_passed: bool = False
    proven_pairs: tuple[tuple[str, str], ...] = ()
    rung_count: int = 0
    contact_count: int = 0


def _known_morphemes(text: str) -> list[str]:
    """인식된(UNKNOWN 아님) 형태소 표면형 목록 — 설명가능성의 근거."""
    return [m.surface for m in analyze(text).morphemes if m.pos != Pos.UNKNOWN]


def _count_contacts(program: LadderProgram) -> int:
    """래더 전체의 접점(NO/NC) 수 — 렁 요약용."""
    contacts = (ElementType.CONTACT_NO, ElementType.CONTACT_NC)
    return sum(
        1
        for rung in program.rungs
        for branch in rung.input_branches
        for el in branch.elements
        if el.element_type in contacts
    )


def _synthesize(spec: StateMachineSpec) -> tuple[str, LadderProgram]:
    """명세 → 합성 ST + 디바이스 맵 적용 래더(결정론)."""
    st = synthesize_st(spec)
    allocator = DeviceAllocator().build_from_spec(spec)
    program = transpile_st(st, allocator, title=spec.title)
    return st, program


def run_one(text: str) -> DemoResult:
    """한 문장을 전 파이프라인에 통과시켜 결과를 만든다(전사 출력은 print_transcript)."""
    frame: IntentFrame = extract(text)
    recipe_id, score = match_by_frame(frame)

    # 정직 규율: 비확신 또는 매핑 실패 → 보류(거짓 래더 생성 금지).
    if not frame.confident:
        reason = (
            f"확신 미달(certainty<{CONFIDENCE_THRESHOLD:.1f}) — "
            "인식 못 한 형태소가 있어 거짓 이해를 막음"
        )
        return DemoResult(
            text=text, coverage=frame.coverage, certainty=frame.certainty,
            confident=False, recipe_id=recipe_id, recipe_score=score,
            held=True, hold_reason=reason,
        )
    if recipe_id is None or recipe_id not in RECIPES:
        return DemoResult(
            text=text, coverage=frame.coverage, certainty=frame.certainty,
            confident=frame.confident, recipe_id=recipe_id, recipe_score=score,
            held=True, hold_reason="도메인 밖 — 매핑되는 검증된 레시피 없음",
        )

    # 합성 → 검증 → 래더 (확신 문장만).
    spec = build_spec(recipe_id)
    st, program = _synthesize(spec)
    dups = detect_double_coils(st)
    report = verify(spec, st)
    proven = proven_safe_pairs(spec, st)
    return DemoResult(
        text=text, coverage=frame.coverage, certainty=frame.certainty,
        confident=True, recipe_id=recipe_id, recipe_score=score, held=False,
        double_coils=len(dups), verify_passed=report.passed,
        proven_pairs=tuple(sorted(proven)),
        rung_count=len(program.rungs), contact_count=_count_contacts(program),
    )


def _transcript_lines(text: str, result: DemoResult) -> list[str]:
    """한 문장의 사람 읽는 단계별 전사를 줄 리스트로 만든다."""
    frame = extract(text)
    lines: list[str] = []
    lines.append("-" * 72)
    lines.append(f"입력(한국어): {text!r}")
    # (a) 형태소 분석
    known = _known_morphemes(text)
    lines.append(
        f"  (a) 형태소 분석 : 인식 {known} | coverage={result.coverage:.2f}"
    )
    # (b) 의도 프레임 + 확신도
    lines.append(
        f"  (b) 의도 프레임 : {frame.explain()} "
        f"| 확신도={result.certainty:.2f} (confident={result.confident})"
    )
    # 보류면 정직하게 멈춘다.
    if result.held:
        lines.append(f"  [보류 HELD] {result.hold_reason}")
        lines.append("     -> 거짓 래더를 생성하지 않습니다(환각 0).")
        return lines
    # (c) 레시피 매핑
    recipe = RECIPES[result.recipe_id] if result.recipe_id else None
    title = recipe.title if recipe else "?"
    lines.append(
        f"  (c) 레시피 매핑 : {result.recipe_id} ('{title}') | 점수={result.recipe_score:.1f}"
    )
    # (d) 합성 ST + 이중코일
    spec = build_spec(result.recipe_id) if result.recipe_id else None
    st = synthesize_st(spec) if spec else ""
    coil_lines = [
        ln.strip()
        for ln in st.splitlines()
        if ":=" in ln and not ln.lstrip().startswith("//")
    ]
    lines.append(
        f"  (d) 합성 ST    : 대입문 {len(coil_lines)}개 | 이중코일={result.double_coils}"
    )
    for cl in coil_lines:
        lines.append(f"        {cl}")
    # (e) 정형검증
    pairs = (
        ", ".join(f"{a}!={b}" for a, b in result.proven_pairs) or "(인터락 없음)"
    )
    lines.append(
        f"  (e) 정형검증    : passed={result.verify_passed} "
        f"| k-귀납 증명 인터락 쌍={pairs}"
    )
    # (f) 래더
    lines.append(
        f"  (f) 래더        : 렁 {result.rung_count}개, 접점 {result.contact_count}개 "
        f"(ST 대입문->Sum-of-Products 렁)"
    )
    return lines


def print_transcript(sentences: tuple[str, ...] = DEMO_SENTENCES) -> list[DemoResult]:
    """문장 리스트를 받아 각 문장의 전사를 출력하고 결과 목록을 반환한다."""
    print("=" * 72)
    print("end-to-end 데모: 한국어 -> 이해 -> 합성 -> 정형검증 -> 래더 (결정론·키 불필요)")
    print("=" * 72)
    results: list[DemoResult] = []
    for text in sentences:
        result = run_one(text)
        results.append(result)
        for line in _transcript_lines(text, result):
            print(line)
    # 요약(정직 단서 포함).
    confident = [r for r in results if not r.held]
    held = [r for r in results if r.held]
    print("-" * 72)
    print(
        f"요약: 총 {len(results)}문장 | 확신·검증 {len(confident)}건 "
        f"(전원 이중코일0·verify passed) | 보류 {len(held)}건"
    )
    bad = [r for r in confident if r.double_coils != 0 or not r.verify_passed]
    if bad:  # 불변식 위반은 즉시 드러낸다(측정 없는 주장 금지).
        print(f"[경고] 불변식 위반 {len(bad)}건: {[r.text for r in bad]}")
    return results


if __name__ == "__main__":
    print_transcript()
