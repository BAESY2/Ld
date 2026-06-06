// 공유 래더 SVG 렌더러 (읽기 전용) — 에디터/생성기/스튜디오 공용.
//   window.LadderRender.svg(ladder)         -> 정적 SVG(기존 동작 보존).
//   window.LadderRender.svg(ladder, state)  -> state(심볼→bool)로 파워플로우 하이라이트.
// state 가 주어지면 도통 접점/도통 직렬경로/점등 코일을 초록으로 라이브 표시한다
// (sim-engine 의 매 스캔 table 과 동기화 → "살아 움직이는 래더").
(function () {
  const LEFT_RAIL = 24, BUS_L = 70, SLOT = 104, ROW_H = 58, PAD_TOP = 28, COIL_W = 90;
  const C_IDLE = "#cdd6e3", C_LIVE = "#5ff08a", C_OFF = "#454c57";
  const W_STATIC = "#3a7", W_LIVE = "#5ff08a", W_DIM = "#33414f";

  function esc(s) {
    return String(s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
  function line(x1, y1, x2, y2, color, w) {
    return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${w}"/>`;
  }
  // 접점 도통 여부: NO 는 값 그대로, NC 는 반전. state 없으면 null(무상태).
  function conducts(el, state) {
    if (!state) return null;
    const v = !!state[el.symbol];
    return el.element_type === "CONTACT_NC" ? !v : v;
  }
  // 전선 색: 무상태면 기존 초록, 상태 있으면 라이브=밝은초록 / 비도통=흐림.
  function wire(live) { return live === null ? W_STATIC : (live ? W_LIVE : W_DIM); }

  function contact(cx, cy, el, state) {
    const cond = conducts(el, state);
    const col = cond === null ? C_IDLE : (cond ? C_LIVE : C_OFF);
    const nc = el.element_type === "CONTACT_NC";
    const g = [];
    g.push(line(cx - 6, cy - 11, cx - 6, cy + 11, col, 2));
    g.push(line(cx + 6, cy - 11, cx + 6, cy + 11, col, 2));
    if (nc) g.push(line(cx - 9, cy + 11, cx + 9, cy - 11, col, 2));
    const txt = cond ? C_LIVE : "#dce4f0";
    g.push(`<text x="${cx}" y="${cy - 16}" fill="${txt}" font-size="11" text-anchor="middle">${esc(el.symbol)}</text>`);
    if (el.address)
      g.push(`<text x="${cx}" y="${cy + 26}" fill="#6f7a8a" font-size="10" text-anchor="middle">${esc(el.address)}</text>`);
    return g.join("");
  }

  function output(cx, cy, out, state) {
    const t = out.element_type;
    const lit = state ? (t === "TIMER" || t === "COUNTER"
      ? !!state[out.symbol + ".Q"] : !!state[out.symbol]) : null;
    const g = [];
    if (t === "TIMER" || t === "COUNTER") {
      const label = t === "TIMER" ? "TON" : "CTU";
      const stroke = lit ? C_LIVE : "#4f9dff";
      g.push(`<rect x="${cx}" y="${cy - 18}" width="${COIL_W}" height="36" rx="4" fill="#1d2733" stroke="${stroke}" stroke-width="1.5"/>`);
      g.push(`<text x="${cx + COIL_W / 2}" y="${cy - 3}" fill="#8ec9ff" font-size="10" text-anchor="middle">${label} ${esc(out.symbol)}</text>`);
      g.push(`<text x="${cx + COIL_W / 2}" y="${cy + 12}" fill="#9fb3c8" font-size="10" text-anchor="middle">${esc(out.description || "")}</text>`);
      return g.join("");
    }
    const base = t === "COIL_SET" ? "#f5b14c" : t === "COIL_RESET" ? "#ff7a7a" : "#46c46a";
    const color = lit ? C_LIVE : base;
    const tag = t === "COIL_SET" ? "(S)" : t === "COIL_RESET" ? "(R)" : "";
    const txt = lit ? C_LIVE : "#9fe0b0";
    g.push(`<text x="${cx + 35}" y="${cy - 16}" fill="${txt}" font-size="11" text-anchor="middle">${esc(out.symbol)} ${tag}</text>`);
    const sw = lit ? 2.5 : 2;
    g.push(`<path d="M ${cx} ${cy - 12} Q ${cx + 14} ${cy} ${cx} ${cy + 12}" fill="none" stroke="${color}" stroke-width="${sw}"/>`);
    g.push(`<path d="M ${cx + 70} ${cy - 12} Q ${cx + 56} ${cy} ${cx + 70} ${cy + 12}" fill="none" stroke="${color}" stroke-width="${sw}"/>`);
    if (out.address)
      g.push(`<text x="${cx + 35}" y="${cy + 26}" fill="#6f7a8a" font-size="10" text-anchor="middle">${esc(out.address)}</text>`);
    return g.join("");
  }

  function drawRung(rung, ri, y0, h, busR, coilX, rightRail, state) {
    const top = y0 + PAD_TOP;
    const p = [];
    p.push(`<text x="${BUS_L}" y="${y0 + 17}" fill="#7f8a9a" font-size="11">${esc(`[${ri + 1}] ${rung.comment || ""}`)}</text>`);
    p.push(line(LEFT_RAIL, y0, LEFT_RAIL, y0 + h, "#d14b4b", 3));
    p.push(line(rightRail, y0, rightRail, y0 + h, "#d14b4b", 3));
    const branches = rung.input_branches.length ? rung.input_branches : [{ elements: [] }];
    const rowYs = branches.map((_, i) => top + i * ROW_H + ROW_H / 2);
    // 각 브랜치의 끝단 도통(직렬 AND) → rung 도통(OR)
    const branchLive = branches.map((b) =>
      state ? (b.elements || []).every((el) => conducts(el, state)) : null);
    const rungLive = state ? branchLive.some((x) => x) : null;
    if (branches.length > 1) {
      p.push(line(BUS_L, rowYs[0], BUS_L, rowYs[rowYs.length - 1], wire(state ? true : null), 2));
      p.push(line(busR, rowYs[0], busR, rowYs[rowYs.length - 1], wire(rungLive), 2));
    }
    p.push(line(LEFT_RAIL, rowYs[0], BUS_L, rowYs[0], wire(state ? true : null), 2));
    branches.forEach((b, bi) => {
      const yc = rowYs[bi];
      let x = BUS_L, live = state ? true : null; // 좌측 버스는 항상 통전
      if (b.elements.length === 0) {
        p.push(line(BUS_L, yc, busR, yc, wire(live), 2));
      } else {
        b.elements.forEach((el, ci) => {
          const cx = BUS_L + ci * SLOT + SLOT / 2;
          p.push(line(x, yc, cx - 16, yc, wire(live), 2));   // 접점 앞 구간: 누적 통전
          p.push(contact(cx, yc, el, state));
          if (state) live = live && conducts(el, state);     // 접점 통과 후 누적 갱신
          x = cx + 16;
        });
        p.push(line(x, yc, busR, yc, wire(live), 2));
      }
    });
    const midY = rowYs[0];
    p.push(line(busR, midY, coilX - 16, midY, wire(rungLive), 2));
    (rung.outputs || []).forEach((out, oi) => {
      const yc = midY + oi * ROW_H;
      p.push(output(coilX, yc, out, state));
      const olit = state ? !!state[out.symbol] : null;
      p.push(line(coilX + COIL_W - 16, yc, rightRail, yc, wire(olit), 2));
    });
    return `<g>${p.join("")}</g>`;
  }

  function svg(ladder, state) {
    const rungs = (ladder && ladder.rungs) || [];
    if (rungs.length === 0) return '<div class="empty" style="padding:20px;color:#8b94a3">래더가 비어 있습니다.</div>';
    const st = state || null;
    let maxCols = 1;
    for (const r of rungs)
      for (const b of r.input_branches) maxCols = Math.max(maxCols, b.elements.length, 1);
    const busR = BUS_L + maxCols * SLOT + 10;
    const coilX = busR + 40;
    const rightRail = coilX + COIL_W + 30;
    const width = rightRail + 20;
    let y = 0;
    const parts = [];
    rungs.forEach((rung, ri) => {
      const nb = Math.max(rung.input_branches.length, 1);
      const h = nb * ROW_H + PAD_TOP;
      parts.push(drawRung(rung, ri, y, h, busR, coilX, rightRail, st));
      y += h;
    });
    return `<svg width="${width}" height="${y + 10}" xmlns="http://www.w3.org/2000/svg">${parts.join("")}</svg>`;
  }

  window.LadderRender = { svg };
})();
