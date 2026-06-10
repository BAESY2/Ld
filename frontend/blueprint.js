/* blueprint.js — 공장 CAD 도면(P&ID 풍) 렌더러 (SVG, 서버 PlantLayout 기반).
 *
 * 실제 공정 도면 문법으로 그린다: 도면 프레임·격자·좌표 눈금·표제란(도면번호/검증
 * 스탬프), ISA 계기 버블(PT/TT/HS/LSH…), KS풍 기기 심볼(펌프/밸브/모터/탱크/히터…),
 * 배관(흐름 화살표)·제어 신호선(파선)·PLC 랙 결선(디바이스 주소 단자). 검증된 ST
 * 스캔 상태(SimEngine)와 동기해 통전(녹색)·흐름·수위·점멸을 라이브 표시하고,
 * 기기 클릭 → onSelect(symbol) 로 상세/정밀테스트 패널을 연다.
 *
 * window.Blueprint.render(container, plant, opts{title, verified, dcFree, onSelect})
 *   -> { update(simResult), select(symbol|null), el }
 */
(function () {
  "use strict";

  var INK = "#9fb3c8", DIM = "#5b6b7d", ON = "#3fb950", WARN = "#d29922",
      RED = "#ff5d5d", PAPER = "#0c1118", GRID1 = "#121a24", GRID2 = "#1a2533",
      WHITE = "#dce6f2", PIPE = "#7e93ab";
  var BAND_GAUGE = 130, BAND_EQ = 285, BAND_CTRL = 455;
  var STEP_X = 150, LEFT = 90, PLC_W = 150;

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function el(tag, attrs, children) {
    var parts = ["<" + tag];
    for (var k in attrs) parts.push(" " + k + '="' + attrs[k] + '"');
    parts.push(">");
    if (children) parts.push(children);
    parts.push("</" + tag + ">");
    return parts.join("");
  }
  function line(x1, y1, x2, y2, stroke, w, extra) {
    return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 +
      '" stroke="' + (stroke || INK) + '" stroke-width="' + (w || 1.2) + '" ' + (extra || "") + "/>";
  }
  function txt(x, y, s, size, fill, anchor, extra) {
    return '<text x="' + x + '" y="' + y + '" font-size="' + (size || 11) +
      '" fill="' + (fill || INK) + '" text-anchor="' + (anchor || "middle") +
      '" font-family="ui-monospace,Menlo,monospace" ' + (extra || "") + ">" + esc(s) + "</text>";
  }

  // ── 기기 심볼 (각각 중심 0,0 기준 — <g transform> 으로 배치) ────────────────
  function symPump() {
    return '<circle r="17" class="body"/>' +
      '<path d="M -7 -10 L 14 0 L -7 10 Z" class="body" fill="none"/>';
  }
  function symMotor() {
    return '<circle r="17" class="body"/>' + txt(0, 5, "M", 14, "currentColor");
  }
  function symValve() {
    return '<path d="M -16 -9 L 0 0 L -16 9 Z M 16 -9 L 0 0 L 16 9 Z" class="body" fill="none"/>' +
      line(0, 0, 0, -14, "currentColor", 1.4) +
      '<rect x="-7" y="-26" width="14" height="12" class="body"/>' +
      txt(0, -17, "S", 9, "currentColor");
  }
  function symHeater() {
    return '<rect x="-18" y="-13" width="36" height="26" class="body"/>' +
      '<path d="M -12 0 L -8 -7 L -4 7 L 0 -7 L 4 7 L 8 -7 L 12 0" class="body" fill="none"/>';
  }
  function symFan() {
    return '<circle r="17" class="body"/>' +
      '<path d="M 0 -3 C 8 -14 14 -8 5 -1 Z M 3 2 C 14 6 10 14 1 6 Z M -4 1 C -14 4 -14 -6 -2 -5 Z" class="body"/>';
  }
  function symConveyor() {
    return '<rect x="-26" y="-7" width="52" height="11" rx="5" class="body" fill="none"/>' +
      '<circle cx="-19" cy="-1" r="4" class="body"/><circle cx="19" cy="-1" r="4" class="body"/>' +
      '<path class="cargo" d="M -8 -12 h7 v6 h-7 Z M 4 -12 h7 v6 h-7 Z"/>';
  }
  function symBeacon() {
    return line(0, 16, 0, 2, "currentColor", 1.6) +
      '<circle cy="-5" r="8" class="body lamp"/>' +
      '<path class="rays" d="M -14 -16 L -10 -12 M 14 -16 L 10 -12 M 0 -20 L 0 -15" stroke="currentColor" fill="none"/>';
  }
  function symEjector() {
    return '<rect x="-16" y="-9" width="22" height="18" class="body"/>' +
      '<g class="rod">' + line(6, 0, 20, 0, "currentColor", 2.2) +
      '<rect x="18" y="-6" width="5" height="12" class="body"/></g>';
  }
  function symGate() {
    return line(-13, 14, -13, -14, "currentColor", 1.8) + line(13, 14, 13, -14, "currentColor", 1.8) +
      '<rect class="panel" x="-11" y="-12" width="22" height="20" fill="none"/>';
  }
  function symMixer() {
    return '<path d="M -14 -12 h28 v16 q0 8 -14 8 q-14 0 -14 -8 Z" class="body" fill="none"/>' +
      line(0, -18, 0, 4, "currentColor", 1.4) +
      '<path class="paddle" d="M -8 4 h16" stroke="currentColor"/>';
  }
  function symActuator() {
    return '<rect x="-14" y="-14" width="28" height="28" class="body"/>' +
      line(-14, 14, 14, -14, "currentColor", 1);
  }
  function symTank(dev) {
    var marks = "";
    marks += line(-26, 18, 26, 18, WARN, 1, 'stroke-dasharray="4 3"') + txt(34, 21, "LO", 8, WARN, "start");
    marks += line(-26, -22, 26, -22, WARN, 1, 'stroke-dasharray="4 3"') + txt(34, -19, "HI", 8, WARN, "start");
    return '<path d="M -26 -34 q26 -12 52 0 V 34 q -26 12 -52 0 Z" class="body" fill="none"/>' +
      '<clipPath id="tkclip"><path d="M -25 -33 q25 -11 50 0 V 33 q -25 11 -50 0 Z"/></clipPath>' +
      '<rect class="water" x="-25" y="10" width="50" height="24" clip-path="url(#tkclip)"/>' + marks;
  }
  // ISA 계기/조작 버블 — 원 + 횡선 + 문자(태그 머리).
  function symBubble(letters, square) {
    var core = '<circle r="14" class="body"/>' + line(-14, 0, 14, 0, "currentColor", 1) +
      txt(0, -3.5, letters, 9.5, "currentColor");
    if (square) core = '<rect x="-18" y="-18" width="36" height="36" class="body" fill="none"/>' + core;
    return core;
  }

  var SYM = {
    pump: symPump, motor: symMotor, valve: symValve, heater: symHeater,
    cooler: symFan, fan: symFan, conveyor: symConveyor, beacon: symBeacon,
    ejector: symEjector, gate: symGate, mixer: symMixer, actuator: symActuator,
  };
  var BUBBLE_LETTERS = { button: "HS", estop: "ES", level: "LSH", fault: "XA", sensor: "XS" };

  function gaugeLetters(sym) {
    var s = String(sym).toUpperCase();
    if (s.indexOf("PRESSURE") === 0) return "PT";
    if (s.indexOf("TEMP") === 0) return "TT";
    if (s.indexOf("LEVEL") === 0) return "LT";
    return "AT";
  }
  function gaugeUnit(sym) {
    var s = String(sym).toUpperCase();
    if (s.indexOf("PRESSURE") === 0) return "bar";
    if (s.indexOf("TEMP") === 0) return "°C";
    return "";
  }

  // 직교 배선 경로(수직→수평) — 도면식 결선.
  function route(x1, y1, x2, y2, midY) {
    var my = midY != null ? midY : (y1 + y2) / 2;
    return "M " + x1 + " " + y1 + " V " + my + " H " + x2 + " V " + y2;
  }

  function render(container, plant, opts) {
    opts = opts || {};
    var devs = plant.devices || [];
    var gauges = devs.filter(function (d) { return d.role === "gauge"; });
    var tanks = devs.filter(function (d) { return d.role === "tank"; });
    var outs = devs.filter(function (d) { return d.role === "output"; });
    var ctrls = devs.filter(function (d) { return d.role === "input"; });

    var eqRow = tanks.concat(outs);              // 장비 밴드: 탱크 먼저(좌측)
    var nCols = Math.max(eqRow.length, gauges.length, ctrls.length, 1);
    var W = LEFT + nCols * STEP_X + 60 + PLC_W + 70;
    var H = 600;
    var plcX = W - PLC_W - 40, plcY = 150, plcH = 320;

    var pos = {};                                 // symbol -> {x, y}
    function place(list, y) {
      list.forEach(function (d, i) { pos[d.symbol] = { x: LEFT + 40 + i * STEP_X, y: y, d: d }; });
    }
    place(gauges, BAND_GAUGE); place(eqRow, BAND_EQ); place(ctrls, BAND_CTRL);

    var s = [];
    // ── 종이·격자·프레임·눈금 ──────────────────────────────────────────────
    s.push('<rect width="' + W + '" height="' + H + '" fill="' + PAPER + '"/>');
    var g = [];
    for (var gx = 0; gx <= W; gx += 10) g.push(line(gx, 0, gx, H, gx % 50 ? GRID1 : GRID2, 0.5));
    for (var gy = 0; gy <= H; gy += 10) g.push(line(0, gy, W, gy, gy % 50 ? GRID1 : GRID2, 0.5));
    s.push("<g>" + g.join("") + "</g>");
    s.push('<rect x="14" y="14" width="' + (W - 28) + '" height="' + (H - 28) +
      '" fill="none" stroke="' + INK + '" stroke-width="1.6"/>');
    s.push('<rect x="20" y="20" width="' + (W - 40) + '" height="' + (H - 40) +
      '" fill="none" stroke="' + DIM + '" stroke-width="0.7"/>');
    var zones = "12345678", zi;
    for (zi = 0; zi < 8; zi++) {
      s.push(txt(20 + (W - 40) * (zi + .5) / 8, 13, zones[zi], 9, DIM));
      s.push(txt(20 + (W - 40) * (zi + .5) / 8, H - 5, zones[zi], 9, DIM));
    }
    var rows = "ABCDEF";
    for (zi = 0; zi < 6; zi++) {
      s.push(txt(9, 20 + (H - 40) * (zi + .55) / 6, rows[zi], 9, DIM));
      s.push(txt(W - 9, 20 + (H - 40) * (zi + .55) / 6, rows[zi], 9, DIM));
    }
    // 밴드 라벨
    s.push(txt(34, BAND_GAUGE - 52, "계기 (INSTRUMENTS)", 9, DIM, "start"));
    s.push(txt(34, BAND_EQ - 64, "공정 설비 (PROCESS EQUIPMENT)", 9, DIM, "start"));
    s.push(txt(34, BAND_CTRL - 40, "조작·검출 (CONTROL & DETECTION)", 9, DIM, "start"));

    // ── PLC 랙 ────────────────────────────────────────────────────────────
    s.push('<rect x="' + plcX + '" y="' + plcY + '" width="' + PLC_W + '" height="' + plcH +
      '" fill="#0f1722" stroke="' + INK + '" stroke-width="1.4"/>');
    s.push(txt(plcX + PLC_W / 2, plcY + 20, "PLC", 13, WHITE));
    s.push(txt(plcX + PLC_W / 2, plcY + 35, "LS XGK · Z3 검증로직", 8.5, DIM));
    s.push(line(plcX, plcY + 44, plcX + PLC_W, plcY + 44, DIM, 0.8));
    var ioDevs = devs.filter(function (d) { return d.role !== "tank"; });
    var termY = {};
    ioDevs.forEach(function (d, i) {
      var ty = plcY + 58 + i * Math.min(22, (plcH - 70) / Math.max(ioDevs.length, 1));
      termY[d.symbol] = ty;
      var isOut = d.role === "output";
      var tx = isOut ? plcX : plcX + PLC_W;
      s.push('<circle cx="' + tx + '" cy="' + ty + '" r="2.6" fill="' + PAPER +
        '" stroke="' + INK + '" stroke-width="1.1" data-term="' + esc(d.symbol) + '"/>');
      s.push(txt(isOut ? plcX + 8 : plcX + PLC_W - 8, ty + 3,
        (d.address || d.symbol), 7.5, DIM, isOut ? "start" : "end"));
    });

    // ── 주공정 라인 — 설비들이 배관 위에 인라인으로 앉는다(P&ID 의 척추) ──────
    var procParts = [];
    if (eqRow.length >= 1) {
      var pl = pos[eqRow[0].symbol], pr = pos[eqRow[eqRow.length - 1].symbol];
      var px0 = pl.x - 64, px1 = pr.x + 64, py0 = pl.y;
      procParts.push('<path class="pipe" d="M ' + px0 + " " + py0 + " H " + px1 + '"/>');
      // 흐름 화살표(설비 사이마다)
      for (var ei = 0; ei < eqRow.length - 1; ei++) {
        var ax = (pos[eqRow[ei].symbol].x + pos[eqRow[ei + 1].symbol].x) / 2;
        procParts.push('<path d="M ' + (ax - 6) + " " + (py0 - 5) + " L " + (ax + 6) + " " + py0 +
          " L " + (ax - 6) + " " + (py0 + 5) + ' Z" fill="' + PIPE + '"/>');
      }
      procParts.push(txt(px0 + 2, py0 - 12, "공정 흐름 →", 8.5, DIM, "start"));
    }
    s.push("<g>" + procParts.join("") + "</g>");

    // 계기 리더선 — 계기/탱크 버블에서 주공정 라인까지 파선 인하(검출점 표기)
    gauges.forEach(function (d) {
      var p = pos[d.symbol];
      s.push('<path class="lead" d="M ' + p.x + " " + (p.y + 16) + " V " + (BAND_EQ - 26) +
        '" fill="none"/>');
      s.push('<circle cx="' + p.x + '" cy="' + (BAND_EQ - 22) + '" r="3.4" fill="none" stroke="' +
        INK + '" stroke-width="1.3"/>');
    });

    // ── 연결 — 배관(탱크) · 신호선(PLC) ───────────────────────────────────
    var wires = [];
    var laneIdx = 0;
    (plant.connections || []).forEach(function (c) {
      if (c.kind === "pipe" && pos[c.src] && pos[c.dst]) {
        var a = pos[c.src], b = pos[c.dst];
        var py = BAND_EQ - 78;
        wires.push('<path class="pipe" data-flow="' + esc(c.src) + '" d="' +
          route(a.x, a.y - 24, b.x, b.y - 40, py) + '"/>');
        wires.push('<path class="flowdash" data-flow="' + esc(c.src) + '" d="' +
          route(a.x, a.y - 24, b.x, b.y - 40, py) + '"/>');
      } else if (c.kind === "signal") {
        var dev = c.src === "PLC" ? c.dst : c.src;
        var p = pos[dev]; if (!p || termY[dev] == null) return;
        var isOut = c.src === "PLC";
        // 기기 → (자기 전용 레인으로 수직) → 단자 높이 → (수평) → PLC 단자.
        // 레인을 기기별로 어긋나게 배선해 선 겹침을 없앤다(트레이식 정렬).
        var lane = p.x + 30 + (laneIdx % 7) * 7;
        laneIdx++;
        wires.push('<path class="sig' + (isOut ? " sigout" : "") + '" data-sig="' + esc(dev) +
          '" d="M ' + (p.x + 18) + " " + p.y +
          " H " + lane + " V " + termY[dev] + " H " + plcX + '"/>');
      }
    });
    s.push("<g>" + wires.join("") + "</g>");

    // ── 기기 심볼 배치 ──────────────────────────────────────────────────────
    devs.forEach(function (d) {
      var p = pos[d.symbol]; if (!p) return;
      var body;
      if (d.role === "gauge") body = symBubble(gaugeLetters(d.symbol));
      else if (d.role === "input") body = symBubble(BUBBLE_LETTERS[d.kind] || "XS", d.kind === "estop");
      else if (d.role === "tank") body = symTank(d);
      else body = (SYM[d.kind] || symActuator)();
      var tagY = d.role === "tank" ? -56 : -34;
      var nameY = d.role === "tank" ? 60 : 38;
      var setp = "";
      if (d.role === "gauge" && (d.thresholds || []).length) {
        setp = txt(0, 30, "SP " + d.thresholds.join("/") + gaugeUnit(d.symbol), 8, WARN);
      }
      s.push('<g class="dev ' + esc(d.kind) + " r-" + esc(d.role) + '" data-sym="' + esc(d.symbol) +
        '" transform="translate(' + p.x + "," + p.y + ')">' +
        '<circle class="hit" r="34" fill="transparent"/>' +
        body +
        txt(0, tagY, d.tag || d.symbol, 9.5, WHITE) +
        txt(0, nameY, d.label || d.symbol, 8.5, DIM) +
        (d.address ? txt(0, nameY + 11, d.address, 7.5, DIM) : "") +
        setp + "</g>");
    });

    // ── 표제란(타이틀 블록) ────────────────────────────────────────────────
    var tbW = 280, tbH = 74, tbX = W - tbW - 22, tbY = H - tbH - 22;
    var dwgNo = "LD-" + Math.abs(hash(plant.title || "")).toString(16).slice(0, 4).toUpperCase();
    s.push('<g font-family="ui-monospace,Menlo,monospace">');
    s.push('<rect x="' + tbX + '" y="' + tbY + '" width="' + tbW + '" height="' + tbH +
      '" fill="#0f1722" stroke="' + INK + '" stroke-width="1.3"/>');
    s.push(line(tbX, tbY + 24, tbX + tbW, tbY + 24, DIM, 0.8));
    s.push(line(tbX + 150, tbY + 24, tbX + 150, tbY + tbH, DIM, 0.8));
    s.push(line(tbX, tbY + 49, tbX + tbW, tbY + 49, DIM, 0.8));
    s.push(txt(tbX + 8, tbY + 16, (opts.title || plant.title || "자연어 설계").slice(0, 30),
      9.5, WHITE, "start"));
    s.push(txt(tbX + 8, tbY + 40, "DWG NO. " + dwgNo + "  REV A", 8.5, INK, "start"));
    s.push(txt(tbX + 158, tbY + 40, "SCALE NTS", 8.5, INK, "start"));
    var ver = opts.verified ? "Z3 VERIFIED" : "UNVERIFIED";
    var verCol = opts.verified ? ON : RED;
    s.push('<rect x="' + (tbX + 6) + '" y="' + (tbY + 55) + '" width="138" height="14" rx="2" ' +
      'fill="none" stroke="' + verCol + '" stroke-width="1"/>');
    s.push(txt(tbX + 75, tbY + 65.5, "✓ " + ver + " · 이중코일 0", 8, verCol));
    s.push(txt(tbX + 158, tbY + 65.5, "자연어→래더 컴파일러", 8, DIM, "start"));
    s.push("</g>");

    // ── DOM 구성 + 스타일 ────────────────────────────────────────────────
    container.innerHTML =
      '<svg viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H +
      '" xmlns="http://www.w3.org/2000/svg" class="bp">' +
      "<style>" +
      ".bp{font-family:ui-monospace,Menlo,monospace}" +
      ".bp .dev{cursor:pointer;color:" + INK + "}" +
      ".bp .dev .body{fill:none;stroke:currentColor;stroke-width:2.1}" +
      ".bp .dev.r-gauge .body,.bp .dev.r-input .body{stroke-width:1.4}" +
      ".bp .dev.on{color:" + ON + "}" +
      ".bp .dev.on .body{filter:drop-shadow(0 0 4px rgba(63,185,80,.7))}" +
      ".bp .dev.sel .hit{stroke:" + WHITE + ";stroke-dasharray:5 4;stroke-width:1.2}" +
      ".bp .dev.alarm{color:" + RED + "}" +
      ".bp .pipe{fill:none;stroke:" + PIPE + ";stroke-width:3.5}" +
      ".bp .flowdash{fill:none;stroke:" + ON + ";stroke-width:2;stroke-dasharray:7 9;opacity:0}" +
      ".bp .flowdash.go{opacity:1;animation:bpflow 1s linear infinite}" +
      "@keyframes bpflow{to{stroke-dashoffset:-32}}" +
      ".bp .sig{fill:none;stroke:" + DIM + ";stroke-width:1;stroke-dasharray:5 4}" +
      ".bp .lead{stroke:" + DIM + ";stroke-width:1;stroke-dasharray:3 4}" +
      ".bp .sig.hot{stroke:" + ON + "}" +
      ".bp .water{fill:rgba(47,129,247,.55)}" +
      ".bp .dev.on .rays{animation:bpblink .5s steps(2) infinite}" +
      "@keyframes bpblink{50%{opacity:.1}}" +
      ".bp .dev.on .rod{transform:translateX(8px);transition:transform .3s}" +
      ".bp .dev.on .panel{transform:translateY(-9px);transition:transform .3s}" +
      ".bp .dev.on .cargo{animation:bpcargo 1.2s linear infinite}" +
      "@keyframes bpcargo{to{transform:translateX(12px)}}" +
      "</style>" + s.join("") + "</svg>";

    var svg = container.querySelector("svg");
    var selSym = null;

    // ── 팬/줌(휠·드래그·핀치 — 모바일 특화) — viewBox 변환 ────────────────────
    var vb = { x: 0, y: 0, w: W, h: H };
    function applyVB() {
      svg.setAttribute("viewBox", vb.x + " " + vb.y + " " + vb.w + " " + vb.h);
    }
    svg.removeAttribute("width"); svg.removeAttribute("height");
    svg.style.width = "100%"; svg.style.height = "100%";
    svg.style.touchAction = "none"; svg.style.cursor = "grab";
    applyVB();
    function zoomAt(cx, cy, f) {
      var nw = Math.max(W * .25, Math.min(W * 2.5, vb.w * f));
      var k = nw / vb.w;
      vb.x = cx - (cx - vb.x) * k; vb.y = cy - (cy - vb.y) * k;
      vb.w = nw; vb.h = vb.h * k; applyVB();
    }
    function toLocal(e) {
      var r = svg.getBoundingClientRect();
      return { x: vb.x + (e.clientX - r.left) / r.width * vb.w,
               y: vb.y + (e.clientY - r.top) / r.height * vb.h };
    }
    var ptrs = {}, moved = 0, pinD = 0;
    svg.addEventListener("pointerdown", function (e) {
      ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
      moved = 0; svg.setPointerCapture(e.pointerId);
      var ids = Object.keys(ptrs);
      if (ids.length === 2) {
        var a = ptrs[ids[0]], b = ptrs[ids[1]];
        pinD = Math.hypot(a.x - b.x, a.y - b.y);
      }
    });
    svg.addEventListener("pointermove", function (e) {
      var p = ptrs[e.pointerId]; if (!p) return;
      var ids = Object.keys(ptrs);
      var r = svg.getBoundingClientRect();
      if (ids.length === 2) {                       // 핀치 줌
        ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
        var a = ptrs[ids[0]], b = ptrs[ids[1]];
        var nd = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinD > 0 && nd > 0) {
          var mid = { clientX: (a.x + b.x) / 2, clientY: (a.y + b.y) / 2 };
          var lm = toLocal(mid);
          zoomAt(lm.x, lm.y, pinD / nd);
        }
        pinD = nd; moved += 10; return;
      }
      var dx = e.clientX - p.x, dy = e.clientY - p.y;
      moved += Math.abs(dx) + Math.abs(dy);
      vb.x -= dx / r.width * vb.w; vb.y -= dy / r.height * vb.h;
      ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
      applyVB();
    });
    function upPtr(e) {
      delete ptrs[e.pointerId]; pinD = 0;
      if (moved < 6) {                               // 클릭 = 기기 선택
        var gEl = e.target.closest ? e.target.closest(".dev") : null;
        if (gEl && opts.onSelect) opts.onSelect(gEl.getAttribute("data-sym"));
      }
    }
    svg.addEventListener("pointerup", upPtr);
    svg.addEventListener("pointercancel", upPtr);
    svg.addEventListener("wheel", function (e) {
      e.preventDefault();
      var lm = toLocal(e);
      zoomAt(lm.x, lm.y, e.deltaY > 0 ? 1.12 : .9);
    }, { passive: false });

    // 탱크 수위(연출) 상태
    var level = .35;
    var lastT = Date.now();

    function update(r) {
      var now = Date.now(), dt = Math.min((now - lastT) / 1000, .25); lastT = now;
      devs.forEach(function (d) {
        var gn = svg.querySelector('.dev[data-sym="' + cssesc(d.symbol) + '"]');
        if (!gn) return;
        var on = false, alarm = false;
        if (!r) { gn.classList.remove("on", "alarm"); return; }
        if (d.role === "output") on = !!r.outputs[d.symbol];
        else if (d.role === "input") { on = !!r.inputs[d.symbol]; alarm = on && (d.kind === "estop" || d.kind === "fault"); }
        else if (d.role === "tank") {
          var feeding = (d.fed_by || []).some(function (f) { return r.outputs[f]; });
          level = Math.max(.05, Math.min(.95, level + (feeding ? .1 : -.045) * dt));
          var w = gn.querySelector(".water");
          if (w) { var h = 64 * level; w.setAttribute("y", String(33 - h)); w.setAttribute("height", String(h)); }
          on = feeding;
        } else if (d.role === "gauge") {
          for (var k in r.inputs) {
            if (k.indexOf(d.symbol + "_") === 0 && r.inputs[k]) { alarm = true; break; }
          }
        }
        gn.classList.toggle("on", on);
        gn.classList.toggle("alarm", alarm);
        // 신호선 활성
        svg.querySelectorAll('[data-sig="' + cssesc(d.symbol) + '"]').forEach(function (w2) {
          w2.classList.toggle("hot", on || alarm);
        });
        if (d.role === "output") {
          svg.querySelectorAll('[data-flow="' + cssesc(d.symbol) + '"]').forEach(function (f) {
            if (f.classList.contains("flowdash")) f.classList.toggle("go", on);
          });
        }
      });
    }
    function select(symbol) {
      if (selSym) {
        var prev = svg.querySelector('.dev[data-sym="' + cssesc(selSym) + '"]');
        if (prev) prev.classList.remove("sel");
      }
      selSym = symbol;
      if (symbol) {
        var cur = svg.querySelector('.dev[data-sym="' + cssesc(symbol) + '"]');
        if (cur) cur.classList.add("sel");
      }
    }
    return { update: update, select: select, el: svg };
  }

  function cssesc(s) { return String(s).replace(/["\\]/g, "\\$&"); }
  function hash(s) {
    var h = 0;
    for (var i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) | 0; }
    return h || 1;
  }

  window.Blueprint = { render: render };
})();
