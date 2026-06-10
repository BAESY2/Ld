// 공유 래더 SVG 렌더러 v2 (읽기 전용) — 에디터/생성기/스튜디오/웹 공용.
//   window.LadderRender.svg(ladder)         -> 정적 SVG.
//   window.LadderRender.svg(ladder, state)  -> state(심볼→bool)로 파워플로우 라이브.
// XG5000 풍 전문 도면 문법: 렁 번호 박스·주석 밴드·셀 그리드·정식 접점/코일 심볼·
// 타이머/카운터 펑션블록(PT 표시)·분기 정션 도트·통전 경로 글로우.
(function () {
  var LEFT = 30, BUS_L = 86, SLOT = 112, ROW_H = 66, HEAD_H = 26, COIL_W = 104, PAD_B = 10;
  var C_WIRE = "#5d6b7c", C_LIVE = "#46e07c", C_OFF = "#3a4350", C_IDLE = "#cdd6e3";
  var C_RAIL = "#4f9dff", C_TXT = "#e6edf6", C_DIM = "#76828f", C_BG = "#0d1117";
  var C_CELL = "#161d27", C_BLK = "#8ec9ff";

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function line(x1, y1, x2, y2, color, w, cls) {
    return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 +
      '" stroke="' + color + '" stroke-width="' + w + '"' +
      (cls ? ' class="' + cls + '"' : "") + "/>";
  }
  function txt(x, y, s, size, fill, anchor, weight) {
    return '<text x="' + x + '" y="' + y + '" font-size="' + size + '" fill="' + fill +
      '" text-anchor="' + (anchor || "middle") + '"' +
      (weight ? ' font-weight="' + weight + '"' : "") + ">" + esc(s) + "</text>";
  }
  function wireCol(live) { return live === null ? C_WIRE : (live ? C_LIVE : C_OFF); }
  function wireW(live) { return live ? 2.6 : 1.6; }
  function conducts(el, state) {
    if (!state) return null;
    var v = !!state[el.symbol];
    return el.element_type === "CONTACT_NC" ? !v : v;
  }

  // ── 접점 — 정식 -| |- / -|/|- 심볼 ────────────────────────────────────────
  function contact(cx, cy, el, state) {
    var cond = conducts(el, state);
    var col = cond === null ? C_IDLE : (cond ? C_LIVE : C_OFF);
    var nc = el.element_type === "CONTACT_NC";
    var g = [];
    if (cond) g.push('<rect x="' + (cx - 13) + '" y="' + (cy - 15) +
      '" width="26" height="30" rx="3" fill="rgba(70,224,124,.12)"/>');
    g.push(line(cx - 8, cy - 13, cx - 8, cy + 13, col, 2.6));
    g.push(line(cx + 8, cy - 13, cx + 8, cy + 13, col, 2.6));
    if (nc) g.push(line(cx - 12, cy + 13, cx + 12, cy - 13, col, 2.2));
    g.push(txt(cx, cy - 21, el.symbol, 11.5, cond ? C_LIVE : C_TXT, "middle", 600));
    if (el.address) g.push(txt(cx, cy + 28, el.address, 9, C_DIM));
    return g.join("");
  }

  // ── 출력 — 코일( ) / (S) / (R) / TON·CTU 펑션블록 ─────────────────────────
  function output(cx, cy, out, state) {
    var t = out.element_type;
    var lit = state ? (t === "TIMER" || t === "COUNTER"
      ? !!state[out.symbol + ".Q"] : !!state[out.symbol]) : null;
    var g = [];
    if (t === "TIMER" || t === "COUNTER") {
      var label = t === "TIMER" ? "TON" : "CTU";
      var stroke = lit ? C_LIVE : C_BLK;
      var pt = (out.description || "").trim();
      g.push('<rect x="' + cx + '" y="' + (cy - 22) + '" width="' + COIL_W +
        '" height="44" rx="5" fill="#121a26" stroke="' + stroke + '" stroke-width="1.6"/>');
      g.push(line(cx, cy - 6, cx + COIL_W, cy - 6, "#22304273", 1));
      g.push(txt(cx + COIL_W / 2, cy - 10, label + "  " + out.symbol, 11,
        lit ? C_LIVE : C_BLK, "middle", 700));
      g.push(txt(cx + COIL_W / 2, cy + 11, pt || "—", 9.5, C_DIM));
      // 입출력 핀
      g.push(line(cx - 6, cy, cx, cy, wireCol(lit), 1.6));
      g.push(txt(cx + 5, cy + 3, "IN", 7.5, C_DIM, "start"));
      g.push(txt(cx + COIL_W - 5, cy + 3, "Q", 7.5, lit ? C_LIVE : C_DIM, "end"));
      return g.join("");
    }
    var base = t === "COIL_SET" ? "#f5b14c" : t === "COIL_RESET" ? "#ff7a7a" : "#46c46a";
    var color = lit ? C_LIVE : base;
    var tag = t === "COIL_SET" ? "S" : t === "COIL_RESET" ? "R" : "";
    var ccx = cx + COIL_W / 2;
    if (lit) g.push('<circle cx="' + ccx + '" cy="' + cy +
      '" r="17" fill="rgba(70,224,124,.14)"/>');
    g.push('<circle cx="' + ccx + '" cy="' + cy + '" r="13" fill="none" stroke="' +
      color + '" stroke-width="' + (lit ? 2.6 : 2) + '"/>');
    if (tag) g.push(txt(ccx, cy + 4, tag, 11, color, "middle", 700));
    g.push(txt(ccx, cy - 21, out.symbol, 11.5, lit ? C_LIVE : C_TXT, "middle", 600));
    if (out.address) g.push(txt(ccx, cy + 28, out.address, 9, C_DIM));
    g.push(line(cx, cy, ccx - 13, cy, wireCol(lit), wireW(lit)));
    g.push(line(ccx + 13, cy, cx + COIL_W, cy, wireCol(lit), wireW(lit)));
    return g.join("");
  }

  function junction(x, y, live) {
    return '<circle cx="' + x + '" cy="' + y + '" r="3" fill="' + wireCol(live) + '"/>';
  }

  function drawRung(rung, ri, y0, h, busR, coilX, rightRail, state) {
    var p = [];
    // 렁 헤더 밴드 — 번호 박스 + 주석
    p.push('<rect x="' + LEFT + '" y="' + y0 + '" width="' + (rightRail - LEFT) +
      '" height="' + HEAD_H + '" fill="#10161f"/>');
    p.push('<rect x="' + (LEFT + 4) + '" y="' + (y0 + 4) +
      '" width="44" height="18" rx="3" fill="#1b2738" stroke="#2c3e57" stroke-width="1"/>');
    p.push(txt(LEFT + 26, y0 + 17, String(ri + 1).padStart(4, "0"), 10, C_BLK, "middle", 700));
    if (rung.comment) p.push(txt(LEFT + 56, y0 + 17, rung.comment, 10.5, C_DIM, "start"));

    var top = y0 + HEAD_H;
    var branches = rung.input_branches.length ? rung.input_branches : [{ elements: [] }];
    var rowYs = branches.map(function (_, i) { return top + i * ROW_H + ROW_H / 2 + 4; });
    var branchLive = branches.map(function (b) {
      return state ? (b.elements || []).every(function (el) { return conducts(el, state); }) : null;
    });
    var rungLive = state ? branchLive.some(function (x) { return x; }) : null;

    // 셀 그리드(편집기 느낌의 옅은 격자)
    for (var gx = BUS_L; gx <= busR; gx += SLOT)
      p.push(line(gx, top + 2, gx, y0 + h - 4, C_CELL, 1));

    // 전원 레일
    p.push(line(LEFT, y0, LEFT, y0 + h, C_RAIL, 4));
    p.push(line(rightRail, y0, rightRail, y0 + h, C_RAIL, 4));

    // 분기 수직 묶음 + 정션
    if (branches.length > 1) {
      p.push(line(BUS_L, rowYs[0], BUS_L, rowYs[rowYs.length - 1], wireCol(state ? true : null), 2));
      p.push(line(busR, rowYs[0], busR, rowYs[rowYs.length - 1], wireCol(rungLive), 2));
      rowYs.forEach(function (yc, i) {
        p.push(junction(BUS_L, yc, state ? true : null));
        p.push(junction(busR, yc, branchLive[i]));
      });
    }
    p.push(line(LEFT, rowYs[0], BUS_L, rowYs[0], wireCol(state ? true : null), wireW(state ? true : false)));

    branches.forEach(function (b, bi) {
      var yc = rowYs[bi];
      var x = BUS_L, live = state ? true : null;
      if (!b.elements.length) {
        p.push(line(BUS_L, yc, busR, yc, wireCol(live), wireW(live)));
      } else {
        b.elements.forEach(function (el, ci) {
          var cx = BUS_L + ci * SLOT + SLOT / 2;
          p.push(line(x, yc, cx - 14, yc, wireCol(live), wireW(live)));
          p.push(contact(cx, yc, el, state));
          if (state) live = live && conducts(el, state);
          x = cx + 14;
        });
        p.push(line(x, yc, busR, yc, wireCol(live), wireW(live)));
      }
    });

    var midY = rowYs[0];
    p.push(line(busR, midY, coilX, midY, wireCol(rungLive), wireW(rungLive)));
    (rung.outputs || []).forEach(function (out, oi) {
      var yc = midY + oi * ROW_H;
      if (oi > 0) {
        p.push(line(coilX - 14, midY, coilX - 14, yc, wireCol(rungLive), 2));
        p.push(line(coilX - 14, yc, coilX, yc, wireCol(rungLive), wireW(rungLive)));
        p.push(junction(coilX - 14, midY, rungLive));
      }
      p.push(output(coilX, yc, out, state));
      var olit = state ? !!state[out.symbol] : null;
      p.push(line(coilX + COIL_W, yc, rightRail, yc, wireCol(olit), wireW(olit)));
    });
    return "<g>" + p.join("") + "</g>";
  }

  function svg(ladder, state) {
    var rungs = (ladder && ladder.rungs) || [];
    if (!rungs.length)
      return '<div style="padding:20px;color:#8b94a3;font-size:13px">래더가 비어 있습니다.</div>';
    var st = state || null;
    var maxCols = 1;
    rungs.forEach(function (r) {
      r.input_branches.forEach(function (b) { maxCols = Math.max(maxCols, b.elements.length, 1); });
    });
    var busR = BUS_L + maxCols * SLOT + 14;
    var coilX = busR + 36;
    var rightRail = coilX + COIL_W + 34;
    var width = rightRail + 26;
    var y = 8, parts = [];
    rungs.forEach(function (rung, ri) {
      var rows = Math.max(rung.input_branches.length, 1, (rung.outputs || []).length);
      var h = HEAD_H + rows * ROW_H + PAD_B;
      parts.push(drawRung(rung, ri, y, h, busR, coilX, rightRail, st));
      y += h + 6;
    });
    return '<svg width="' + width + '" height="' + (y + 8) +
      '" xmlns="http://www.w3.org/2000/svg" ' +
      'style="background:' + C_BG + ';border-radius:8px" ' +
      'font-family="ui-monospace,Menlo,Consolas,monospace">' + parts.join("") + "</svg>";
  }

  window.LadderRender = { svg: svg };
})();
