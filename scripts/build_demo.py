#!/usr/bin/env python3
"""실제 파이프라인으로 자기완결 데모 페이지(docs/demo.html)를 굽는다 — 백엔드 불필요.

한국어 문장을 진짜로(korean→intent→compile/recipe→synth→verify→simulate) 돌린 결과
(이해 내용·검증 ST·형식 안전증명·시뮬 트레이스)를 JSON 으로 박아, 브라우저만으로 재생되는
단일 HTML 을 만든다. *시뮬레이션*임을 명시(실물 모터 아님). GitHub 렌더 링크로 공유 가능.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.compile_frame import frame_to_spec  # noqa: E402
from app.intent import extract  # noqa: E402
from app.models import StateMachineSpec  # noqa: E402
from app.simulator import simulate  # noqa: E402
from app.synth import synthesize_st  # noqa: E402
from app.verifier import proven_safe_pairs, verify  # noqa: E402
from app.wizard import build_spec  # noqa: E402

Event = tuple[int, dict[str, bool]]


def _case(title: str, korean: str, spec: StateMachineSpec,
          timeline: list[Event], dur: int, step: int) -> dict[str, object]:
    st = synthesize_st(spec)
    rep = verify(spec, st)
    res = simulate(st, timeline, duration_ms=dur, step_ms=step)
    proven = sorted({tuple(sorted(p)) for p in proven_safe_pairs(spec, st)})
    outs = [p.symbol for p in spec.io_points if p.direction.value == "OUTPUT"]
    steps = [
        {"in": {k: bool(v) for k, v in s.inputs.items()},
         "out": {k: bool(v) for k, v in s.outputs.items()}}
        for s in res.samples
    ]
    return {
        "title": title, "korean": korean,
        "understood": extract(korean).explain(),
        "st": st, "verified": rep.passed,
        "proven": [" ⊥ ".join(p) for p in proven],
        "inputs": res.inputs, "outputs": outs, "steps": steps,
    }


def _f(text: str) -> StateMachineSpec:
    return frame_to_spec(text).spec


def build() -> list[dict[str, object]]:
    return [
        _case("모터 기동/정지", "버튼 누르면 모터 돌고 정지 누르면 멈춰",
              build_spec("motor_start_stop"),
              [(100, {"START": True}), (200, {"START": False}),
               (600, {"STOP": True}), (700, {"STOP": False})], 900, 100),
        _case("수위 히스테리시스(펌프)", "저수위 되면 펌프 켜고 고수위 되면 펌프 꺼",
              _f("저수위 되면 펌프 켜고 고수위 되면 펌프 꺼"),
              [(100, {"LO_LS": True}), (200, {"LO_LS": False}),
               (600, {"HI_LS": True}), (700, {"HI_LS": False})], 900, 100),
        _case("순차 시퀀서(다음·N초)", "모터 돌리고 다음 펌프 켜고 다음 밸브 열어",
              _f("모터 돌리고 다음 펌프 켜고 다음 밸브 열어"),
              [(100, {"START": True}), (300, {"START": False})], 7000, 250),
    ]


_HTML = """<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>한국어 → 검증된 PLC 제어 (데모)</title><style>
*{box-sizing:border-box}body{margin:0;background:#0a0a0b;color:#cfd2d6;
font-family:ui-monospace,Menlo,Consolas,monospace;font-size:15px;line-height:1.6}
.wrap{max-width:760px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:20px;color:#fff;margin:0 0 4px}.sub{color:#6a6e76;font-size:13px;margin-bottom:18px}
.warn{background:#16120a;border:1px solid #3a2f12;color:#e3b341;border-radius:8px;
padding:8px 12px;font-size:12.5px;margin-bottom:18px}
select,button{font-family:inherit;font-size:14px;background:#15171b;color:#cfd2d6;
border:1px solid #2a2d33;border-radius:8px;padding:8px 12px;cursor:pointer}
button.play{background:#82aaff;color:#06101e;border:none;font-weight:700}
.row{display:flex;gap:10px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.card{background:#0f1011;border:1px solid #1e2024;border-radius:12px;
padding:16px;margin-bottom:14px}
.lab{color:#6a6e76;font-size:11.5px;letter-spacing:.04em;margin-bottom:6px;text-transform:uppercase}
.understood{color:#82aaff;font-size:15px}
pre{white-space:pre-wrap;color:#aeb4bd;font-size:13px;margin:0}
.badge{display:inline-block;background:#0c2018;border:1px solid #1d4a36;color:#7ee787;
border-radius:6px;padding:3px 10px;font-size:12px;margin:2px 6px 2px 0}
.dev{display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px dotted #181a1e}
.dev:last-child{border:none}.dev .nm{width:110px;color:#aeb4bd;font-size:13px}
.gear{font-size:30px;transition:color .15s;color:#2a2d33;display:inline-block}
.gear.on{color:#7ee787}.spin{animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.io{display:flex;gap:6px;flex-wrap:wrap}.pin{font-size:11px;padding:2px 7px;border-radius:5px;
background:#15171b;border:1px solid #2a2d33;color:#565a62}
.pin.on{background:#1d3a5e;color:#82aaff;border-color:#82aaff}
.t{color:#6a6e76;font-size:12px;margin-left:auto}
</style></head><body><div class=wrap>
<h1>한국어 한 줄 → 형식 검증된 PLC 제어</h1>
<div class=sub>AI 없이 결정론으로 이해·합성·검증.
실제 파이프라인이 만든 결과를 재생합니다.</div>
<div class=warn>⚠ 이것은 <b>디지털 트윈 시뮬레이션</b>입니다(실물 모터 아님). 생성·검증은 진짜이며,
화면 속 장치가 검증된 로직대로 동작합니다.</div>
<div class=row><select id=sel></select><button class=play id=play>▶ 재생</button>
<span class=t id=tstep></span></div>
<div class=card><div class=lab>입력(한국어)</div>
<div id=ko style="color:#fff;font-size:16px"></div></div>
<div class=card><div class=lab>이해 내용 (결정론 파싱)</div>
<div class=understood id=und></div></div>
<div class=card><div class=lab>형식 검증</div><div id=badges></div></div>
<div class=card><div class=lab>장치 (시뮬레이션)</div><div id=devs></div>
<div class=io id=ins style="margin-top:10px"></div></div>
<div class=card><div class=lab>합성된 검증 래더 로직 (ST)</div><pre id=st></pre></div>
</div><script>
const DATA=__DATA__;let cur=0,timer=null,k=0;
const sel=document.getElementById('sel');
DATA.forEach((d,i)=>{const o=document.createElement('option');
o.value=i;o.textContent=d.title;sel.appendChild(o)});
const SPINNERS=['MOTOR','PUMP','FAN','CONVEYOR','BLOWER','VACUUM','COMPRESSOR','DRILL'];
function isSpin(s){return SPINNERS.some(x=>s.startsWith(x))}
function render(d){
 document.getElementById('ko').textContent='"'+d.korean+'"';
 document.getElementById('und').textContent=d.understood;
 document.getElementById('st').textContent=d.st;
 let b='<span class=badge>'+(d.verified?'✓ 검증 통과':'⚠ 미검증')+'</span>';
 b+='<span class=badge>이중코일 0</span>';
 d.proven.forEach(p=>b+='<span class=badge>증명: '+p+' 동시금지</span>');
 document.getElementById('badges').innerHTML=b;
 const devs=document.getElementById('devs');devs.innerHTML='';
 d.outputs.forEach(o=>{devs.innerHTML+='<div class=dev><span class=nm>'+o+'</span>'+
  '<span class="gear" data-o="'+o+'">'+(isSpin(o)?'⚙':'⬤')+'</span></div>'});
 paint(d,0);
}
function paint(d,i){
 const s=d.steps[i]||d.steps[d.steps.length-1];
 document.getElementById('tstep').textContent='스텝 '+(i+1)+'/'+d.steps.length;
 d.outputs.forEach(o=>{const el=document.querySelector('.gear[data-o="'+o+'"]');
  const on=s.out[o];el.classList.toggle('on',on);el.classList.toggle('spin',on&&isSpin(o))});
 const ins=document.getElementById('ins');ins.innerHTML='';
 d.inputs.forEach(x=>{ins.innerHTML+='<span class="pin'+(s.in[x]?' on':'')+'">'+x+'</span>'})
}
function play(){const d=DATA[cur];clearInterval(timer);k=0;
 timer=setInterval(()=>{paint(d,k);k++;if(k>=d.steps.length){clearInterval(timer)}},420)}
sel.onchange=()=>{cur=+sel.value;clearInterval(timer);render(DATA[cur])};
document.getElementById('play').onclick=play;
render(DATA[0]);
</script></body></html>"""


def main() -> int:
    data = build()
    html = _HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    out = Path(__file__).resolve().parent.parent / "docs" / "demo.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html)} bytes, {len(data)} examples)")
    for d in data:
        print(f"  · {d['title']}: verified={d['verified']} outs={d['outputs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
