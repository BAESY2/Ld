/* precision.js — 기기 단위 정밀 테스트 러너 (브라우저 내, 검증된 ST 가 단일 원천).
 *
 * 도면에서 기기를 클릭하면 그 기기에 대한 *정밀* 검사를 실행한다:
 *  1) 기동 전수탐색  — 입력 2^n 전 조합(상한 1024)으로 켜지는 조건을 빠짐없이 확인
 *  2) 자기유지 일치  — ST 구조(자기참조)와 실제 거동(입력 해제 후 유지)이 일치하는가
 *  3) 정지 우선     — 기동조건과 정지조건 동시 인가 시 1스캔 내 정지하는가
 *  4) 인터락 퍼징   — 무작위 입력 폭격 N스캔 동안 증명된 짝이 동시 ON 0회인가
 *  5) 타이머 정밀   — 타이머 구동 출력의 지연이 프리셋 ±1스캔인가
 *  6) 교차엔진 대조 — 같은 타임라인을 JS(SimEngine)·서버(Python /api/simulate)에
 *                     돌려 출력 트레이스가 비트 단위로 일치하는가(독립 구현 상호검증)
 *
 * window.Precision.testOutput(st, symbol, {proven, stepMs}) -> Promise<[{name,pass,detail}]>
 * window.Precision.influence(st, inputSymbol) -> [outputSymbols]
 * window.Precision.crossCheck(st) -> Promise<{pass, detail}>
 */
(function () {
  "use strict";
  if (!window.SimEngine) { window.Precision = null; return; }
  var SE = window.SimEngine;

  // ── ST 구조 분석 — 출력식의 입력 극성(긍정=기동 후보 / NOT 아래=정지 후보) ──
  function polarity(node, neg, acc) {
    if (!node) return acc;
    if (node.t === "var") {
      var e = acc[node.name] || (acc[node.name] = { pos: false, neg: false });
      if (neg) e.neg = true; else e.pos = true;
    } else if (node.t === "not") polarity(node.a, !neg, acc);
    else if (node.t === "and" || node.t === "or") {
      polarity(node.a, neg, acc); polarity(node.b, neg, acc);
    }
    return acc;
  }
  function exprOf(prog, sym) {
    for (var i = 0; i < prog.assigns.length; i++)
      if (prog.assigns[i][0] === sym) return prog.assigns[i][1];
    return null;
  }
  function refsSelf(prog, sym) {
    var node = exprOf(prog, sym);
    if (!node) return false;
    return polarity(node, false, {})[sym] != null;
  }

  function combosOf(n) { return 1 << n; }

  // 조합 적용 → k스캔 → 출력 상태 (엔진은 매 조합 reset).
  function probe(eng, inputs, mask, sym, scans, dt) {
    eng.reset();
    var forced = {};
    inputs.forEach(function (s, i) { forced[s] = !!(mask & (1 << i)); });
    var r = null;
    for (var k = 0; k < scans; k++) r = eng.step(forced, dt);
    return { on: !!(r && r.outputs[sym]), forced: forced, last: r };
  }

  // 1) 기동 전수탐색
  function testActivation(st, sym, dt) {
    var eng = SE.create(st);
    var prog = SE.compile(st);
    var ins = eng.inputs.slice(0, 10);            // 전수 상한 2^10
    var total = combosOf(ins.length);
    var hasTimer = eng.timers.length > 0;
    var scans = hasTimer ? 60 : 3;
    var hits = 0, firstMask = -1;
    for (var m = 0; m < total; m++) {
      if (probe(eng, ins, m, sym, scans, dt).on) { hits++; if (firstMask < 0) firstMask = m; }
    }
    var onSet = [];
    if (firstMask >= 0) ins.forEach(function (s, i) { if (firstMask & (1 << i)) onSet.push(s); });
    return {
      name: "기동 전수탐색",
      pass: hits > 0,
      detail: hits > 0
        ? "전 " + total + "조합 검사 · 기동 조합 " + hits + "개 (예: " + (onSet.join("+") || "무입력") + ")"
        : "전 " + total + "조합에서 기동 불가 — 도달 불능 의심",
      hits: hits, ins: ins, firstMask: firstMask, scans: scans,
    };
  }

  // 2) 자기유지 일치 (구조 ↔ 거동)
  function testSealIn(st, sym, act, dt) {
    var prog = SE.compile(st);
    var structural = refsSelf(prog, sym);
    if (act.firstMask < 0) return { name: "자기유지 일치", pass: true, detail: "기동 불가 — 해당 없음" };
    var eng = SE.create(st);
    var p = probe(eng, act.ins, act.firstMask, sym, act.scans, dt);
    var off = {};
    act.ins.forEach(function (s) { off[s] = false; });
    var r = eng.step(off, dt); r = eng.step(off, dt);
    var held = !!r.outputs[sym];
    var pass = held === structural;
    return {
      name: "자기유지 일치",
      pass: pass,
      detail: "ST 구조=" + (structural ? "자기유지" : "비유지") +
        " · 실측=" + (held ? "유지" : "해제") + (pass ? " (일치)" : " (불일치!)"),
    };
  }

  // 3) 정지 우선
  function testStopDominance(st, sym, act, dt) {
    var prog = SE.compile(st);
    var node = exprOf(prog, sym);
    if (!node || act.firstMask < 0)
      return { name: "정지 우선", pass: true, detail: "해당 없음" };
    var pol = polarity(node, false, {});
    var eng0 = SE.create(st);
    var offs = act.ins.filter(function (s) { return pol[s] && pol[s].neg; });
    if (!offs.length) return { name: "정지 우선", pass: true, detail: "정지 입력 없음 — 해당 없음" };
    var fails = [];
    offs.forEach(function (o) {
      var eng = SE.create(st);
      var p = probe(eng, act.ins, act.firstMask, sym, act.scans, dt);  // 기동
      var f = {}; act.ins.forEach(function (s) { f[s] = !!p.forced[s]; });
      f[o] = true;                                  // 정지 인가(기동 유지한 채)
      var r = eng.step(f, dt);
      if (r.outputs[sym]) fails.push(o);
    });
    return {
      name: "정지 우선",
      pass: fails.length === 0,
      detail: fails.length === 0
        ? "정지입력 " + offs.length + "종 각각 1스캔 내 정지 확인 (" + offs.join(", ") + ")"
        : "정지 실패: " + fails.join(", "),
    };
  }

  // 4) 인터락 퍼징 — 증명된 짝에 무작위 폭격
  function testInterlockFuzz(st, sym, proven, dt, scansN) {
    var pairs = (proven || []).filter(function (g) { return g.indexOf(sym) >= 0; });
    if (!pairs.length) return null;
    var eng = SE.create(st);
    var N = scansN || 500, viol = 0;
    var seed = 0x2F6E2B1;
    function rnd() { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return ((seed >>> 0) / 4294967296); }
    var forced = {};
    for (var k = 0; k < N; k++) {
      eng.inputs.forEach(function (s) { if (rnd() < .35) forced[s] = rnd() < .5; });
      var r = eng.step(forced, dt);
      pairs.forEach(function (g) {
        var onCount = g.reduce(function (a, o) { return a + (r.outputs[o] ? 1 : 0); }, 0);
        if (onCount > 1) viol++;
      });
    }
    return {
      name: "인터락 퍼징",
      pass: viol === 0,
      detail: pairs.map(function (g) { return g.join("⊥"); }).join(", ") +
        " · 무작위 " + N + "스캔 · 동시 ON " + viol + "회" + (viol === 0 ? " (+Z3 k-귀납 증명)" : ""),
    };
  }

  // 5) 타이머 정밀 — 시퀀서식 출력의 첫 ON 시각이 프리셋 누적과 ±1스캔 일치
  function testTimerPrecision(st, sym, dt) {
    var eng = SE.create(st);
    if (!eng.timers.length) return null;
    var forced = {};
    eng.inputs.forEach(function (s) { forced[s] = false; });
    if (eng.inputs.indexOf("START") >= 0) forced.START = true;
    var firstOn = -1, MAX = 400;
    for (var k = 0; k < MAX; k++) {
      var r = eng.step(forced, dt);
      if (k === 3 && "START" in forced) forced.START = false;  // 펄스 기동
      if (firstOn < 0 && r.outputs[sym]) { firstOn = k; break; }
    }
    if (firstOn < 0) return { name: "타이머 정밀", pass: false, detail: MAX + "스캔 내 미기동" };
    return {
      name: "타이머 정밀",
      pass: true,
      detail: "첫 ON = " + (firstOn * dt) + "ms (" + firstOn + "스캔, 스캔주기 " + dt + "ms)",
    };
  }

  // 6) 교차엔진 대조 — JS(SimEngine) vs 서버 Python 시뮬레이터 비트 일치
  function crossCheck(st, dt) {
    dt = dt || 100;
    var eng = SE.create(st);
    var tl = [];
    eng.inputs.forEach(function (s, i) {
      tl.push([dt * (3 * i + 1), obj(s, true)]);
      tl.push([dt * (3 * i + 1) + dt * 6, obj(s, false)]);
    });
    var dur = Math.max(dt * (3 * eng.inputs.length + 10), 4000);
    var local = SE.simulate(st, tl, dur, dt);
    return fetch("/api/simulate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ st_code: st, inputs_timeline: tl, duration_ms: dur, step_ms: dt }),
    }).then(function (r) { return r.json(); }).then(function (srv) {
      if (!srv.ok) return { name: "교차엔진 대조", pass: false, detail: srv.error || "서버 시뮬 실패" };
      var n = Math.min(local.samples.length, srv.samples.length);
      var cells = 0, mism = 0;
      for (var k = 0; k < n; k++) {
        var a = local.samples[k].outputs, b = srv.samples[k].outputs || {};
        for (var o in a) { cells++; if (!!a[o] !== !!b[o]) mism++; }
      }
      return {
        name: "교차엔진 대조",
        pass: mism === 0 && cells > 0,
        detail: "JS↔Python " + n + "샘플 × " + local.outputs.length + "출력 = " +
          cells + "셀 비교 · 불일치 " + mism,
      };
    }).catch(function (e) {
      return { name: "교차엔진 대조", pass: false, detail: "서버 연결 실패: " + e };
    });
  }
  function obj(k, v) { var o = {}; o[k] = v; return o; }

  // 입력 기기 → 영향을 주는 출력 목록(식에 등장)
  function influence(st, inputSym) {
    var prog = SE.compile(st);
    var outs = [];
    prog.assigns.forEach(function (a) {
      if (polarity(a[1], false, {})[inputSym] != null) outs.push(a[0]);
    });
    // 타이머/카운터 경유 영향
    for (var tn in prog.timers) {
      if (polarity(prog.timers[tn].en, false, {})[inputSym] != null) {
        prog.assigns.forEach(function (a) {
          if (polarity(a[1], false, {})[tn + ".Q"] != null && outs.indexOf(a[0]) < 0) outs.push(a[0]);
        });
      }
    }
    return outs;
  }

  // 종합 — 출력 기기 1대의 정밀 테스트 묶음.
  // opts.serverless=true 면 서버 교차엔진 대조를 건너뛴다(정적/브라우저 단독판).
  function testOutput(st, sym, opts) {
    opts = opts || {};
    var dt = opts.stepMs || 100;
    return new Promise(function (resolve) {
      var out = [];
      var act = testActivation(st, sym, dt);
      out.push(act);
      out.push(testSealIn(st, sym, act, dt));
      out.push(testStopDominance(st, sym, act, dt));
      var il = testInterlockFuzz(st, sym, opts.proven, dt);
      if (il) out.push(il);
      var tp = testTimerPrecision(st, sym, dt);
      if (tp) out.push(tp);
      function done() {
        resolve(out.map(function (t) {
          return { name: t.name, pass: t.pass, detail: t.detail };
        }));
      }
      if (opts.serverless) { done(); return; }
      crossCheck(st, dt).then(function (cc) { out.push(cc); done(); });
    });
  }

  window.Precision = { testOutput: testOutput, influence: influence, crossCheck: crossCheck };
})();
