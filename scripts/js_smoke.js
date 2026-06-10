/* js_smoke.js — 프론트 JS 헤드리스 스모크 (node, 브라우저 불필요).
 *
 * 실제 회귀를 잡은 부류: THREE r160 의 position 은 재할당 불가라
 * Object.assign(obj,{position}) 이 TypeError → Plant3D.create 전체가 죽어
 * 3D 가 통째로 안 나오던 버그. 여기서는 WebGL/캔버스만 스텁하고 씬 그래프
 * 구성(빌더·환경·배관·케이블·카메라)·스캔 update 까지 *전부 실제로 실행*해
 * 생성 시 예외 0 을 보증한다. blueprint/panel/ladder 는 SVG 문자열을 만들어
 * XML 정형까지 검사한다(파이썬 테스트가 이 스크립트를 구동).
 *
 * 사용: node scripts/js_smoke.js <plant.json 경로>
 * 출력: 마지막 줄 "JS_SMOKE_OK" (실패 시 비-0 종료 + 에러).
 */
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");

const res = JSON.parse(fs.readFileSync(process.argv[2] || "/tmp/plantres2.json", "utf8"));

// ── 브라우저 셈 — window/document 최소 스텁 ────────────────────────────────
const noop = () => {};
function fakeCanvasCtx() {
  return {
    font: "", fillStyle: "", strokeStyle: "", textBaseline: "", lineWidth: 1,
    measureText: (t) => ({ width: 10 * String(t).length }),
    beginPath: noop, roundRect: noop, rect: noop, fill: noop, stroke: noop,
    fillText: noop, fillRect: noop, strokeRect: noop,
    save: noop, restore: noop, translate: noop, rotate: noop,
    moveTo: noop, lineTo: noop, closePath: noop,
  };
}
global.document = {
  createElement(tag) {
    if (tag === "canvas") {
      return { width: 0, height: 0, getContext: fakeCanvasCtx };
    }
    return { style: {} };
  },
};
global.window = {
  devicePixelRatio: 1,
  addEventListener: noop,
};
global.requestAnimationFrame = noop; // frame() 1회 실행 후 정지

// ── THREE 로드(CommonJS 분기) + WebGLRenderer 만 스텁 ───────────────────────
const T = require(path.join(ROOT, "frontend/vendor/three.min.js"));
class FakeRenderer {
  constructor() {
    this.domElement = {
      style: {},
      addEventListener: noop, setPointerCapture: noop,
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 500 }),
      parentNode: null,
    };
    this.shadowMap = {};
  }
  setPixelRatio() {} setSize() {} render() {} dispose() {}
}
T.WebGLRenderer = FakeRenderer;
window.THREE = T;

// ── 대상 모듈 로드 ──────────────────────────────────────────────────────────
for (const f of ["plant3d.js", "blueprint.js", "panel.js", "ladder-render.js", "sim-engine.js"]) {
  eval(fs.readFileSync(path.join(ROOT, "frontend", f), "utf8"));
}

// ── 1) Plant3D — 전체 씬 구성 + 스캔 update + destroy (생성 예외 0) ─────────
const container3d = {
  clientWidth: 800, clientHeight: 500,
  appendChild: noop, removeChild: noop,
};
const p3d = window.Plant3D.create(container3d, res.plant, { onToggle: noop });
const eng = window.SimEngine.create(res.structured_text);
const forced = {}; eng.inputs.forEach((s) => { forced[s] = true; });
p3d.update(eng.step(forced, 100));
p3d.resize();
p3d.destroy();
console.log("plant3d: scene OK (devices=" + res.plant.devices.length + ")");

// ── 2) SVG 렌더러 3종 — 생성 + (간이) 정형 검사 ─────────────────────────────
const fakeSvg = {
  addEventListener: noop, removeAttribute: noop, setAttribute: noop, style: {},
  querySelector: () => null, querySelectorAll: () => [],
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 1, height: 1 }),
  setPointerCapture: noop,
};
function cont() {
  return {
    set innerHTML(v) { this._h = v; }, get innerHTML() { return this._h; },
    querySelector: () => fakeSvg,
  };
}
const outs = {};
const c1 = cont(); window.Blueprint.render(c1, res.plant, { title: "t", verified: true });
outs["bp.svg"] = c1._h;
const c2 = cont(); window.Panel.render(c2, res.plant, {});
outs["panel.svg"] = c2._h;
outs["ladder.svg"] = window.LadderRender.svg(res.ladder);
for (const k in outs) {
  if (!outs[k] || outs[k].indexOf("<svg") < 0) throw new Error(k + " 비정상");
  fs.writeFileSync("/tmp/smoke_" + k, outs[k]);
}
console.log("svg renderers: OK (bytes:",
  Object.values(outs).map((s) => s.length).join("/"), ")");

console.log("JS_SMOKE_OK");
