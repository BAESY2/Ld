"""프론트 JS 헤드리스 스모크 (node 구동) — 3D 씬·SVG 렌더러 생성 예외 0 보증.

실제 회귀: THREE r160 의 ``position`` 은 재할당 불가(읽기전용)라
``Object.assign(obj, {position})`` 이 TypeError 를 던져 Plant3D.create 전체가
죽고 *3D 가 통째로 안 나오던* 버그. scripts/js_smoke.js 가 WebGL 만 스텁한 채
씬 구성·스캔 update·SVG 3종 생성을 실제 실행해 그런 부류를 커밋 전에 잡는다.
node 가 없으면 스킵(파이썬 게이트는 영향 없음).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.compile_frame import frame_to_spec
from app.explain import explain_all
from app.plant import plant_from_spec
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.verifier import verify

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


def _payload(tmp_path: Path, text: str) -> Path:
    r = frame_to_spec(text)
    assert r.confident
    st = synthesize_st(r.spec)
    ladder = transpile_st(st, title=r.spec.title)
    rep = verify(r.spec, st)
    p = tmp_path / "plant.json"
    p.write_text(json.dumps({
        "structured_text": st,
        "ladder": ladder.model_dump(),
        "plant": plant_from_spec(r.spec).model_dump(),
        "explanation": explain_all(r.spec, ladder, rep),
    }, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.mark.parametrize("text", [
    "저수위 되면 펌프 켜고 고수위 되면 펌프 꺼",          # 탱크·배관·수위
    "모터 돌리고 다음 펌프 켜고 다음 밸브 열어",          # 시퀀서·타이머
    "부품 10개 차면 배출하고 고장 나면 경광등 켜",        # 카운터·경광등·실린더
    "컨베이어 돌리고 다음 충전기 켜고 다음 캡핑기 켜고 다음 배출해",  # 보틀링 라인
    "불량 나면 로봇 켜고 배출해",                          # 다관절 로봇·비전
    "5.5킬로와트 모터 스타델타로 기동해",                  # Y-Δ 기동·MC·산식
])
def test_js_smoke_scene_and_svg(tmp_path: Path, text: str) -> None:
    payload = _payload(tmp_path, text)
    proc = subprocess.run(
        ["node", str(ROOT / "scripts" / "js_smoke.js"), str(payload)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"js_smoke 실패:\n{proc.stdout}\n{proc.stderr}"
    assert "JS_SMOKE_OK" in proc.stdout
