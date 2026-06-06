/* sim-engine.js — 브라우저 내 결정론 PLC 스캔 인터프리터.
 *
 * 서버 app/simulator.py 와 동일한 스캔 의미론을 JS 로 1:1 포팅한다:
 *   매 스캔 = 입력 읽기 → 타이머/카운터(FB) 갱신(.Q) → 코일 대입(top-to-bottom,
 *   seal-in 은 직전값 참조). TON/TOF/TP·CTU/CTD 상태를 엔진에 유지한다.
 * 합성 ST 의 코일식(`SYM := boolexpr;`)과 FB 호출(`T1(IN:=..,PT:=T#..);`)을 그대로
 * 해석하므로, 래더 기하가 아니라 *검증된 ST* 가 단일 진실원천이다(서버와 동일).
 *
 * window.SimEngine.create(stCode) -> engine{ step(forced, dt), reset(), inputs, outputs }
 * window.SimEngine.simulate(stCode, timeline, duration, step) -> {inputs, outputs, samples}
 */
(function () {
  "use strict";

  // ── 불리언식 파서 (NOT > AND > OR, 괄호, TRUE/FALSE, 점표기 심볼 T1.Q) ──────
  function tokenize(expr) {
    const re = /\s*(\(|\)|[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)/g;
    const toks = []; let m; let pos = 0;
    while (pos < expr.length) {
      re.lastIndex = pos;
      m = re.exec(expr);
      if (!m || m.index !== pos) {
        if (/\s/.test(expr[pos])) { pos++; continue; }
        throw new Error("토큰 인식 불가: " + expr.slice(pos));
      }
      toks.push(m[1]); pos = re.lastIndex;
    }
    return toks;
  }
  function parse(expr) {
    const toks = tokenize(expr); let i = 0;
    const peek = () => (i < toks.length ? toks[i] : null);
    const next = () => toks[i++];
    function pOr() {
      let n = pAnd();
      while (peek() && peek().toUpperCase() === "OR") { next(); n = { t: "or", a: n, b: pAnd() }; }
      return n;
    }
    function pAnd() {
      let n = pNot();
      while (peek() && peek().toUpperCase() === "AND") { next(); n = { t: "and", a: n, b: pNot() }; }
      return n;
    }
    function pNot() {
      const tk = peek();
      if (tk === null) throw new Error("식이 갑자기 끝남: " + expr);
      if (tk.toUpperCase() === "NOT") { next(); return { t: "not", a: pNot() }; }
      if (tk === "(") { next(); const n = pOr(); if (peek() !== ")") throw new Error("괄호 누락"); next(); return n; }
      const sym = next(); const u = sym.toUpperCase();
      if (u === "TRUE") return { t: "const", v: true };
      if (u === "FALSE") return { t: "const", v: false };
      return { t: "var", name: sym };
    }
    const node = pOr();
    if (i !== toks.length) throw new Error("잔여 토큰: " + toks.slice(i).join(" "));
    return node;
  }
  function evalNode(n, tbl) {
    switch (n.t) {
      case "var": return !!tbl[n.name];
      case "const": return n.v;
      case "not": return !evalNode(n.a, tbl);
      case "and": return evalNode(n.a, tbl) && evalNode(n.b, tbl);
      case "or": return evalNode(n.a, tbl) || evalNode(n.b, tbl);
    }
    throw new Error("알 수 없는 노드");
  }
  function nodeVars(n, out) {
    out = out || new Set();
    if (n.t === "var") out.add(n.name);
    else if (n.t === "not") nodeVars(n.a, out);
    else if (n.t === "and" || n.t === "or") { nodeVars(n.a, out); nodeVars(n.b, out); }
    return out;
  }

  function parseTimeMs(text) {
    const m = /T#\s*(?:(\d+)s)?(?:(\d+)ms)?/i.exec(text || "");
    if (!m) return 0;
    return (m[1] ? +m[1] : 0) * 1000 + (m[2] ? +m[2] : 0);
  }

  // ── 프로그램 파싱 (simulator._Program 미러) ───────────────────────────────
  const ASSIGN = /^\s*([A-Za-z_]\w*)\s*:=\s*([^;]+?)\s*;\s*$/;
  const FBCALL = /^\s*([A-Za-z_]\w*)\s*\((.*)\)\s*;\s*$/;
  const FBARG = /^\s*([A-Za-z_]\w*)\s*:=\s*(.+?)\s*$/;
  const KIND = /타이머\s+([A-Za-z_]\w*)\s*\(\s*(TON|TOF|TP)/i;

  function compile(stCode) {
    const assigns = [], driven = [], timers = {}, counters = {}, kinds = {};
    (stCode || "").split("\n").forEach((line) => {
      const km = KIND.exec(line); if (km) kinds[km[1]] = km[2].toUpperCase();
      const code = line.split("//")[0].trim(); if (!code) return;
      const fb = FBCALL.exec(code);
      if (fb && fb[2].includes(":=")) {
        const args = {};
        fb[2].split(",").forEach((p) => { const a = FBARG.exec(p); if (a) args[a[1].toUpperCase()] = a[2]; });
        if ("CU" in args || "CD" in args) {
          counters[fb[1]] = {
            kind: ("CD" in args) ? "CTD" : "CTU",
            preset: +((args.PV || "0").replace(/\D/g, "") || 0),
            count: parse(args.CU || args.CD || "FALSE"),
            reset: parse(args.R || args.RESET || "FALSE"),
            cnt: 0, q: false, prev: false,
          };
        } else if ("IN" in args) {
          timers[fb[1]] = {
            kind: kinds[fb[1]] || "TON",
            preset: parseTimeMs(args.PT || ""),
            en: parse(args.IN),
            acc: 0, q: false, prevIn: false, running: false,
          };
        }
        return;
      }
      const m = ASSIGN.exec(code);
      if (m) { assigns.push([m[1], parse(m[2])]); if (!driven.includes(m[1])) driven.push(m[1]); }
    });
    // 입력 심볼 = 식에 등장하되 구동출력/.Q/점표기 가 아닌 것
    const fbQ = new Set([...Object.keys(timers), ...Object.keys(counters)].map((n) => n + ".Q"));
    const syms = new Set();
    assigns.forEach(([, n]) => nodeVars(n, syms));
    Object.values(timers).forEach((t) => nodeVars(t.en, syms));
    Object.values(counters).forEach((c) => { nodeVars(c.count, syms); nodeVars(c.reset, syms); });
    const inputs = [...syms].filter((s) => !driven.includes(s) && !fbQ.has(s) && !s.includes(".")).sort();
    return { assigns, driven, timers, counters, inputs };
  }

  function scanTimer(t, tbl, dt) {
    const inp = evalNode(t.en, tbl);
    if (t.kind === "TOF") {
      if (inp) { t.acc = 0; t.q = true; }
      else if (t.q) {
        if (t.prevIn) t.acc = 0;
        else { t.acc = Math.min(t.acc + dt, t.preset); if (t.acc >= t.preset) t.q = false; }
      }
    } else if (t.kind === "TP") {
      if (t.running) { t.acc = Math.min(t.acc + dt, t.preset); if (t.acc >= t.preset) { t.q = false; t.running = false; } }
      else if (inp && !t.prevIn) { t.running = true; t.acc = 0; t.q = t.preset > 0; }
    } else { // TON
      if (inp) { t.acc = t.prevIn ? Math.min(t.acc + dt, t.preset) : 0; t.q = t.acc >= t.preset; }
      else { t.acc = 0; t.q = false; }
    }
    t.prevIn = inp;
  }
  function scanCounter(c, tbl) {
    if (evalNode(c.reset, tbl)) c.cnt = 0;
    else {
      const cu = evalNode(c.count, tbl);
      if (cu && !c.prev) c.cnt += (c.kind === "CTD" ? -1 : 1);
      c.prev = cu;
    }
    c.q = (c.kind === "CTD") ? (c.cnt <= 0) : (c.cnt >= c.preset);
  }

  // ── 상태유지 엔진 (라이브 스캔 루프용) ─────────────────────────────────────
  function create(stCode) {
    const prog = compile(stCode);
    const tbl = {};
    prog.driven.forEach((s) => { tbl[s] = false; });
    function reset() {
      prog.driven.forEach((s) => { tbl[s] = false; });
      Object.values(prog.timers).forEach((t) => { t.acc = 0; t.q = false; t.prevIn = false; t.running = false; });
      Object.values(prog.counters).forEach((c) => { c.cnt = 0; c.q = false; c.prev = false; });
    }
    function step(forced, dt) {
      prog.inputs.forEach((s) => { tbl[s] = !!(forced && forced[s]); });
      for (const name in prog.timers) { scanTimer(prog.timers[name], tbl, dt); tbl[name + ".Q"] = prog.timers[name].q; }
      for (const name in prog.counters) { scanCounter(prog.counters[name], tbl); tbl[name + ".Q"] = prog.counters[name].q; }
      prog.assigns.forEach(([lhs, node]) => { tbl[lhs] = evalNode(node, tbl); });
      const inputs = {}; prog.inputs.forEach((s) => { inputs[s] = tbl[s]; });
      const outputs = {}; prog.driven.forEach((s) => { outputs[s] = tbl[s]; });
      // table: 접점/코일/타이머.Q 등 전체 심볼값 — 래더 파워플로우 하이라이트용.
      return { inputs, outputs, table: { ...tbl } };
    }
    return { step, reset, inputs: prog.inputs, outputs: prog.driven, timers: Object.keys(prog.timers) };
  }

  // ── 일괄 시뮬 (서버 simulate 와 동일 계약, 타임라인→트레이스) ────────────────
  function simulate(stCode, timeline, durationMs, stepMs) {
    stepMs = stepMs || 100;
    const eng = create(stCode);
    const tl = (timeline || []).slice().sort((a, b) => a[0] - b[0]);
    const cur = {}; eng.inputs.forEach((s) => { cur[s] = false; });
    const samples = []; let ti = 0;
    for (let t = 0; t <= durationMs; t += stepMs) {
      while (ti < tl.length && tl[ti][0] <= t) { Object.assign(cur, tl[ti][1]); ti++; }
      const r = eng.step(cur, stepMs);
      samples.push({ t_ms: t, inputs: r.inputs, outputs: r.outputs });
    }
    return { inputs: eng.inputs, outputs: eng.outputs, samples };
  }

  window.SimEngine = { create, simulate, compile, parse, evalNode };
})();
