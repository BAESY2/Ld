// 공유 래더 SVG 렌더러 (읽기 전용) — 에디터/생성기 공용.
// window.LadderRender.svg(ladder) -> SVG 문자열.
(function () {
  const LEFT_RAIL = 24, BUS_L = 70, SLOT = 104, ROW_H = 58, PAD_TOP = 28, COIL_W = 90;

  function esc(s) {
    return String(s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
  function line(x1, y1, x2, y2, color, w) {
    return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${w}"/>`;
  }

  function contact(cx, cy, el) {
    const nc = el.element_type === "CONTACT_NC";
    const g = [];
    g.push(line(cx - 6, cy - 11, cx - 6, cy + 11, "#cdd6e3", 2));
    g.push(line(cx + 6, cy - 11, cx + 6, cy + 11, "#cdd6e3", 2));
    if (nc) g.push(line(cx - 9, cy + 11, cx + 9, cy - 11, "#cdd6e3", 2));
    g.push(`<text x="${cx}" y="${cy - 16}" fill="#dce4f0" font-size="11" text-anchor="middle">${esc(el.symbol)}</text>`);
    if (el.address)
      g.push(`<text x="${cx}" y="${cy + 26}" fill="#6f7a8a" font-size="10" text-anchor="middle">${esc(el.address)}</text>`);
    return g.join("");
  }

  function output(cx, cy, out) {
    const t = out.element_type;
    const g = [];
    if (t === "TIMER" || t === "COUNTER") {
      const label = t === "TIMER" ? "TON" : "CTU";
      g.push(`<rect x="${cx}" y="${cy - 18}" width="${COIL_W}" height="36" rx="4" fill="#1d2733" stroke="#4f9dff" stroke-width="1.5"/>`);
      g.push(`<text x="${cx + COIL_W / 2}" y="${cy - 3}" fill="#8ec9ff" font-size="10" text-anchor="middle">${label} ${esc(out.symbol)}</text>`);
      g.push(`<text x="${cx + COIL_W / 2}" y="${cy + 12}" fill="#9fb3c8" font-size="10" text-anchor="middle">${esc(out.description || "")}</text>`);
      return g.join("");
    }
    const color = t === "COIL_SET" ? "#f5b14c" : t === "COIL_RESET" ? "#ff7a7a" : "#46c46a";
    const tag = t === "COIL_SET" ? "(S)" : t === "COIL_RESET" ? "(R)" : "";
    g.push(`<text x="${cx + 35}" y="${cy - 16}" fill="#9fe0b0" font-size="11" text-anchor="middle">${esc(out.symbol)} ${tag}</text>`);
    g.push(`<path d="M ${cx} ${cy - 12} Q ${cx + 14} ${cy} ${cx} ${cy + 12}" fill="none" stroke="${color}" stroke-width="2"/>`);
    g.push(`<path d="M ${cx + 70} ${cy - 12} Q ${cx + 56} ${cy} ${cx + 70} ${cy + 12}" fill="none" stroke="${color}" stroke-width="2"/>`);
    if (out.address)
      g.push(`<text x="${cx + 35}" y="${cy + 26}" fill="#6f7a8a" font-size="10" text-anchor="middle">${esc(out.address)}</text>`);
    return g.join("");
  }

  function drawRung(rung, ri, y0, h, busR, coilX, rightRail) {
    const top = y0 + PAD_TOP;
    const p = [];
    p.push(`<text x="${BUS_L}" y="${y0 + 17}" fill="#7f8a9a" font-size="11">${esc(`[${ri + 1}] ${rung.comment || ""}`)}</text>`);
    p.push(line(LEFT_RAIL, y0, LEFT_RAIL, y0 + h, "#d14b4b", 3));
    p.push(line(rightRail, y0, rightRail, y0 + h, "#d14b4b", 3));
    const branches = rung.input_branches.length ? rung.input_branches : [{ elements: [] }];
    const rowYs = branches.map((_, i) => top + i * ROW_H + ROW_H / 2);
    if (branches.length > 1) {
      p.push(line(BUS_L, rowYs[0], BUS_L, rowYs[rowYs.length - 1], "#3a7", 2));
      p.push(line(busR, rowYs[0], busR, rowYs[rowYs.length - 1], "#3a7", 2));
    }
    p.push(line(LEFT_RAIL, rowYs[0], BUS_L, rowYs[0], "#3a7", 2));
    branches.forEach((b, bi) => {
      const yc = rowYs[bi];
      let x = BUS_L;
      if (b.elements.length === 0) {
        p.push(line(BUS_L, yc, busR, yc, "#3a7", 2));
      } else {
        b.elements.forEach((el, ci) => {
          const cx = BUS_L + ci * SLOT + SLOT / 2;
          p.push(line(x, yc, cx - 16, yc, "#3a7", 2));
          p.push(contact(cx, yc, el));
          x = cx + 16;
        });
        p.push(line(x, yc, busR, yc, "#3a7", 2));
      }
    });
    const midY = rowYs[0];
    p.push(line(busR, midY, coilX - 16, midY, "#3a7", 2));
    (rung.outputs || []).forEach((out, oi) => {
      const yc = midY + oi * ROW_H;
      p.push(output(coilX, yc, out));
      p.push(line(coilX + COIL_W - 16, yc, rightRail, yc, "#3a7", 2));
    });
    return `<g>${p.join("")}</g>`;
  }

  function svg(ladder) {
    const rungs = (ladder && ladder.rungs) || [];
    if (rungs.length === 0) return '<div class="empty" style="padding:20px;color:#8b94a3">래더가 비어 있습니다.</div>';
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
      parts.push(drawRung(rung, ri, y, h, busR, coilX, rightRail));
      y += h;
    });
    return `<svg width="${width}" height="${y + 10}" xmlns="http://www.w3.org/2000/svg">${parts.join("")}</svg>`;
  }

  window.LadderRender = { svg };
})();
