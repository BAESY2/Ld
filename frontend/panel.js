/* panel.js — 제어반 배선 판넬(동력 단선도) 렌더러 (SVG, PlantLayout.BOM 기반).
 *
 * 실제 MCC/제어반 문법으로 그린다: 인입(3Φ AC380V) → 메인 MCCB → 부스바 →
 * 기기별 분기 회로(분기 MCCB → 인버터(VFD) → 전자접촉기(MC) → EOCR → 단자) →
 * 부하. 제어 회로(PLC→MC 코일, 조작 입력→PLC)는 파선으로 결선한다. 어떤 부품이
 * 들어가는지는 서버가 컴파일한 기기 BOM(plant.devices[].parts)이 단일 원천이다.
 * 가동 시: 통전 경로 녹색, MC 가동편 닫힘, 인버터 Hz 램프, EOCR 정상등.
 *
 * window.Panel.render(container, plant, opts{onSelect}) -> {update(r), select(sym), el}
 */
(function () {
  "use strict";
  var INK = "#9fb3c8", DIM = "#5b6b7d", ON = "#46e07c", RED = "#ff5d5d",
      AMBER = "#d29922", BG = "#0c1118", STEEL = "#2c3947", BUS = "#caa55a",
      WHITE = "#e6edf6", BLUE = "#58a6ff";
  var COL_W = 150, LEFT = 120, BUS_Y = 120;

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function line(x1, y1, x2, y2, c, w, extra) {
    return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 +
      '" stroke="' + c + '" stroke-width="' + w + '" ' + (extra || "") + "/>";
  }
  function txt(x, y, s, size, fill, anchor, weight) {
    return '<text x="' + x + '" y="' + y + '" font-size="' + size + '" fill="' + fill +
      '" text-anchor="' + (anchor || "middle") + '"' +
      (weight ? ' font-weight="' + weight + '"' : "") + ">" + esc(s) + "</text>";
  }
  function has(d, word) {
    return (d.parts || []).some(function (p) { return p.indexOf(word) >= 0; });
  }
  function cssesc(s) { return String(s).replace(/["\\]/g, "\\$&"); }

  // ── 부품 심볼(중심 x, 상단 y 기준 — 세로 회로) ──────────────────────────────
  function symBreaker(x, y, label) {
    return '<g class="wire">' + line(x, y, x, y + 10, "currentColor", 2) +
      '<rect x="' + (x - 13) + '" y="' + (y + 10) + '" width="26" height="30" rx="3" ' +
      'fill="#121a26" stroke="currentColor" stroke-width="1.6"/>' +
      line(x - 6, y + 34, x + 7, y + 16, "currentColor", 2.2) +
      '<circle cx="' + x + '" cy="' + (y + 15) + '" r="2" fill="currentColor"/>' +
      txt(x + 19, y + 29, label, 8.5, "currentColor", "start") +
      line(x, y + 40, x, y + 50, "currentColor", 2) + "</g>";
  }
  function symVFD(x, y) {
    return '<g class="wire">' +
      '<rect x="' + (x - 22) + '" y="' + y + '" width="44" height="34" rx="4" ' +
      'fill="#101a2a" stroke="currentColor" stroke-width="1.6"/>' +
      txt(x, y + 13, "INV", 9, "currentColor", "middle", 700) +
      '<rect x="' + (x - 16) + '" y="' + (y + 18) + '" width="32" height="11" rx="2" fill="#06121f"/>' +
      '<text class="hz" x="' + x + '" y="' + (y + 27) + '" font-size="8.5" fill="#2f81f7" ' +
      'text-anchor="middle">0.0Hz</text>' +
      line(x, y + 34, x, y + 44, "currentColor", 2) + "</g>";
  }
  function symMC(x, y) {
    // 전자접촉기 — 가동편(.arm)이 ON 에서 닫힌다 + 코일 박스
    return '<g class="wire">' +
      line(x, y, x, y + 8, "currentColor", 2) +
      '<circle cx="' + x + '" cy="' + (y + 10) + '" r="2.2" fill="currentColor"/>' +
      '<line class="arm" x1="' + x + '" y1="' + (y + 10) + '" x2="' + (x + 13) + '" y2="' + (y + 26) +
      '" stroke="currentColor" stroke-width="2.4"/>' +
      '<circle cx="' + x + '" cy="' + (y + 30) + '" r="2.2" fill="currentColor"/>' +
      '<rect class="coil" x="' + (x + 16) + '" y="' + (y + 8) + '" width="26" height="22" rx="3" ' +
      'fill="#121a26" stroke="currentColor" stroke-width="1.4"/>' +
      txt(x + 29, y + 22, "MC", 9, "currentColor", "middle", 700) +
      line(x, y + 30, x, y + 40, "currentColor", 2) + "</g>";
  }
  function symEOCR(x, y) {
    return '<g class="wire">' +
      '<ellipse cx="' + x + '" cy="' + (y + 14) + '" rx="17" ry="13" ' +
      'fill="#121a26" stroke="currentColor" stroke-width="1.6"/>' +
      txt(x, y + 17.5, "EOCR", 8, "currentColor", "middle", 700) +
      line(x, y + 27, x, y + 37, "currentColor", 2) + "</g>";
  }
  function symRelay(x, y) {
    return '<g class="wire">' +
      '<rect x="' + (x - 15) + '" y="' + y + '" width="30" height="22" rx="3" ' +
      'fill="#121a26" stroke="currentColor" stroke-width="1.5"/>' +
      txt(x, y + 14, "RY", 9, "currentColor", "middle", 700) +
      line(x, y + 22, x, y + 32, "currentColor", 2) + "</g>";
  }
  function symTerminal(x, y) {
    return '<g class="wire"><rect x="' + (x - 6) + '" y="' + y + '" width="12" height="12" ' +
      'fill="none" stroke="currentColor" stroke-width="1.4"/>' +
      '<circle cx="' + x + '" cy="' + (y + 6) + '" r="2" fill="currentColor"/></g>';
  }

  function render(container, plant, opts) {
    opts = opts || {};
    var devs = plant.devices || [];
    var outs = devs.filter(function (d) { return d.role === "output"; });
    var ctrls = devs.filter(function (d) { return d.role === "input"; });
    var W = Math.max(LEFT + outs.length * COL_W + 260, 760);
    var H = 560;
    var plcX = W - 180, plcY = 150;

    var s = [];
    s.push('<rect width="' + W + '" height="' + H + '" fill="' + BG + '"/>');
    // 외함(캐비닛) 프레임 + 마운팅 레일
    s.push('<rect x="12" y="12" width="' + (W - 24) + '" height="' + (H - 24) +
      '" rx="6" fill="none" stroke="' + STEEL + '" stroke-width="3"/>');
    [[26, 26], [W - 38, 26], [26, H - 38], [W - 38, H - 38]].forEach(function (p2) {
      s.push('<circle cx="' + (p2[0] + 6) + '" cy="' + (p2[1] + 6) + '" r="4" fill="none" stroke="' +
        STEEL + '" stroke-width="1.6"/>');
    });
    s.push(txt(30, 42, "MAIN PANEL — 동력 제어반 단선도 · 3Φ AC380V", 12, WHITE, "start", 800));
    s.push(txt(30, 58, "부품 구성 = 컴파일된 BOM (MCCB·INV·MC·EOCR…)", 9.5, DIM, "start"));

    // 인입 + 메인 차단기 + 부스바
    var inX = 60;
    s.push('<g class="wire" data-w="MAIN">' + line(inX, 66, inX, 70, "currentColor", 2) + "</g>");
    s.push(txt(inX, 64, "3Φ IN", 9, AMBER, "middle", 700));
    s.push('<g class="wire on" data-w="MAIN">' + symBreaker(inX, 70, "MCCB(M)") + "</g>");
    s.push('<g class="wire on" data-w="MAIN">' + line(inX, BUS_Y, LEFT + outs.length * COL_W - 60, BUS_Y, "currentColor", 0) + "</g>");
    // 부스바(3선 표현 — 굵은 동색 1선 + 빗금 3Φ 표기)
    var busEnd = Math.max(LEFT + outs.length * COL_W - 60, inX + 120);
    s.push(line(inX, BUS_Y, busEnd, BUS_Y, BUS, 5));
    s.push(line(inX + 26, BUS_Y - 7, inX + 36, BUS_Y + 7, BUS, 1.6));
    s.push(line(inX + 31, BUS_Y - 7, inX + 41, BUS_Y + 7, BUS, 1.6));
    s.push(line(inX + 36, BUS_Y - 7, inX + 46, BUS_Y + 7, BUS, 1.6));
    s.push(txt(busEnd - 4, BUS_Y - 10, "BUSBAR 380V", 8.5, BUS, "end"));

    // 기기별 분기 회로
    var colX = {};
    outs.forEach(function (d, i) {
      var x = LEFT + i * COL_W;
      colX[d.symbol] = x;
      var y = BUS_Y;
      var g = ['<g class="branch" data-sym="' + esc(d.symbol) + '">'];
      g.push('<rect class="hitbox" x="' + (x - 56) + '" y="' + (BUS_Y + 4) +
        '" width="118" height="' + (H - BUS_Y - 60) + '" rx="6" fill="transparent"/>');
      g.push('<g class="wire" data-w="' + esc(d.symbol) + '">');
      g.push('<circle cx="' + x + '" cy="' + y + '" r="3" fill="' + BUS + '"/>');
      var hasVfd = has(d, "인버터");
      var hasMC = has(d, "전자접촉기");
      var hasEocr = has(d, "열동계전기");
      var hasBrk = has(d, "MCCB") || has(d, "MCB");
      var cy = y + 6;
      if (hasBrk) { g.push(symBreaker(x, cy, has(d, "MCCB") ? "MCCB" : "MCB")); cy += 56; }
      else { g.push(line(x, cy, x, cy + 18, "currentColor", 2)); cy += 18; }
      if (hasVfd) { g.push(symVFD(x, cy)); cy += 50; }
      if (hasMC) { g.push(symMC(x, cy)); cy += 46; }
      else { g.push(symRelay(x, cy)); cy += 38; }
      if (hasEocr) { g.push(symEOCR(x, cy)); cy += 43; }
      g.push(symTerminal(x, cy)); cy += 18;
      g.push(line(x, cy, x, cy + 12, "currentColor", 2));
      g.push("</g>");
      // 부하 명판
      g.push('<rect x="' + (x - 46) + '" y="' + (cy + 12) + '" width="92" height="34" rx="4" ' +
        'fill="#10161f" stroke="#2c3e57" stroke-width="1.2"/>');
      g.push(txt(x, cy + 26, d.tag || d.symbol, 10, WHITE, "middle", 800));
      g.push(txt(x, cy + 39, d.symbol + (d.address ? " · " + d.address : ""), 8, DIM));
      g.push("</g>");
      s.push(g.join(""));
    });

    // PLC 슬라이스 + 제어 결선(PLC→MC 코일 파선)
    s.push('<rect x="' + plcX + '" y="' + plcY + '" width="120" height="240" rx="5" ' +
      'fill="#0f1722" stroke="' + INK + '" stroke-width="1.6"/>');
    s.push(txt(plcX + 60, plcY + 22, "PLC", 12, WHITE, "middle", 800));
    s.push(txt(plcX + 60, plcY + 37, "Z3 검증 로직", 8.5, DIM));
    s.push(line(plcX, plcY + 46, plcX + 120, plcY + 46, DIM, .8));
    outs.forEach(function (d, i) {
      var ty = plcY + 64 + i * 20;
      s.push('<circle cx="' + plcX + '" cy="' + ty + '" r="2.4" fill="' + BG +
        '" stroke="' + INK + '" stroke-width="1.1"/>');
      s.push(txt(plcX + 8, ty + 3, (d.address || d.symbol), 7.5, DIM, "start"));
      // PLC 단자 → MC 코일(파선 제어선)
      var bx = colX[d.symbol] + 42;
      s.push('<path class="ctl" data-c="' + esc(d.symbol) + '" d="M ' + plcX + " " + ty +
        " H " + (bx + 18) + " V " + (BUS_Y + (has(d, "인버터") ? 130 : 80)) + " H " + bx +
        '" fill="none"/>');
    });
    // 조작 입력 단자대(하단) → PLC
    var tY = H - 70;
    s.push(txt(34, tY - 10, "조작·검출 단자대", 9, DIM, "start"));
    ctrls.forEach(function (d, i) {
      var x = 50 + i * 96;
      s.push('<g class="branch" data-sym="' + esc(d.symbol) + '">' +
        '<g class="wire" data-w="' + esc(d.symbol) + '">' +
        '<rect x="' + (x - 8) + '" y="' + tY + '" width="16" height="16" fill="none" ' +
        'stroke="currentColor" stroke-width="1.4"/>' +
        '<circle cx="' + x + '" cy="' + (tY + 8) + '" r="2.4" fill="currentColor"/></g>' +
        txt(x, tY + 30, d.symbol, 8.5, INK) +
        txt(x, tY + 41, d.address || "", 7.5, DIM) +
        '<path class="ctl" data-c="' + esc(d.symbol) + '" d="M ' + x + " " + tY +
        " V " + (tY - 22) + " H " + plcX + '" fill="none"/></g>');
    });

    container.innerHTML =
      '<svg viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H +
      '" xmlns="http://www.w3.org/2000/svg" class="pnl" ' +
      'font-family="ui-monospace,Menlo,monospace">' +
      "<style>" +
      ".pnl .wire{color:" + INK + "}" +
      ".pnl .wire.on{color:" + ON + "}" +
      ".pnl .wire.on line,.pnl .wire.on rect,.pnl .wire.on ellipse{filter:drop-shadow(0 0 3px rgba(70,224,124,.6))}" +
      ".pnl .arm{transform-box:fill-box;transform-origin:top left;transition:transform .25s}" +
      ".pnl .wire.on .arm{transform:rotate(-39deg)}" +
      ".pnl .wire.on .coil{stroke:" + ON + ";fill:rgba(70,224,124,.1)}" +
      ".pnl .ctl{stroke:" + DIM + ";stroke-width:1;stroke-dasharray:5 4}" +
      ".pnl .ctl.hot{stroke:" + BLUE + "}" +
      ".pnl .branch{cursor:pointer}" +
      ".pnl .branch.sel .hitbox{stroke:" + WHITE + ";stroke-dasharray:5 4;stroke-width:1.2}" +
      "</style>" + s.join("") + "</svg>";

    var svg = container.querySelector("svg");
    var selSym = null;
    svg.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest(".branch") : null;
      if (b && opts.onSelect) opts.onSelect(b.getAttribute("data-sym"));
    });

    var hz = {};
    function update(r) {
      devs.forEach(function (d) {
        var on = false;
        if (r) {
          on = d.role === "output" ? !!r.outputs[d.symbol]
            : d.role === "input" ? !!r.inputs[d.symbol] : false;
        }
        svg.querySelectorAll('[data-w="' + cssesc(d.symbol) + '"]').forEach(function (w) {
          w.classList.toggle("on", on);
        });
        svg.querySelectorAll('[data-c="' + cssesc(d.symbol) + '"]').forEach(function (c) {
          c.classList.toggle("hot", on);
        });
        // 인버터 Hz 램프(부드러운 가감속)
        var hzEl = svg.querySelector('.branch[data-sym="' + cssesc(d.symbol) + '"] .hz');
        if (hzEl) {
          var cur = hz[d.symbol] || 0;
          cur += ((on ? 60 : 0) - cur) * .12;
          hz[d.symbol] = cur;
          hzEl.textContent = cur.toFixed(1) + "Hz";
          hzEl.setAttribute("fill", cur > 1 ? "#46e07c" : "#2f81f7");
        }
      });
    }
    function select(symbol) {
      if (selSym) {
        var prev = svg.querySelector('.branch[data-sym="' + cssesc(selSym) + '"]');
        if (prev) prev.classList.remove("sel");
      }
      selSym = symbol;
      if (symbol) {
        var cur = svg.querySelector('.branch[data-sym="' + cssesc(symbol) + '"]');
        if (cur) cur.classList.add("sel");
      }
    }
    return { update: update, select: select, el: svg };
  }

  window.Panel = { render: render };
})();
