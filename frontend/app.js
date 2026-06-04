"use strict";

const EXAMPLES = {
  conveyor:
    "// 정방향 (역방향과 상호배타)\n" +
    "MOTOR_FWD := FWD_PB AND NOT REV_PB AND NOT MOTOR_REV;\n" +
    "// 역방향\n" +
    "MOTOR_REV := REV_PB AND NOT FWD_PB AND NOT MOTOR_FWD;\n",
  selfhold:
    "// 자기유지(래치) 회로\n" +
    "MOTOR := (START_PB OR MOTOR) AND NOT STOP_PB;\n",
  parallel:
    "// 병렬 OR: 수동 또는 자동 기동\n" +
    "PUMP := MANUAL_RUN OR (AUTO_MODE AND LEVEL_LOW);\n",
  double:
    "// 이중코일(에러) — verifier 가 검출\n" +
    "LAMP := SWITCH_A;\n" +
    "LAMP := SWITCH_B;\n",
};

const st = document.getElementById("st");
const preview = document.getElementById("preview");
const issuesEl = document.getElementById("issues");
const statusEl = document.getElementById("status");
const rungCountEl = document.getElementById("rungcount");

let lastLadder = null;

// ---- 라이브 변환 (디바운스) ----------------------------------------------
let timer = null;
function scheduleTranspile() {
  clearTimeout(timer);
  timer = setTimeout(runTranspile, 180);
}

async function runTranspile() {
  const code = st.value;
  try {
    const res = await fetch("/api/transpile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ st_code: code }),
    });
    const data = await res.json();
    lastLadder = data.ladder;
    renderLadder(data.ladder);
    renderIssues(data.issues);
    setStatus(data.ok);
  } catch (e) {
    statusEl.innerHTML = '<span class="dot err"></span>서버 연결 실패';
  }
}

function setStatus(ok) {
  statusEl.innerHTML = ok
    ? '<span class="dot ok"></span>검증 통과'
    : '<span class="dot err"></span>에러 있음';
}

function renderIssues(issues) {
  if (!issues || issues.length === 0) {
    issuesEl.innerHTML = '<div class="issue"><span style="color:var(--muted)">문제 없음 ✓</span></div>';
    return;
  }
  issuesEl.innerHTML = issues
    .map((i) => {
      const cx = i.counterexample ? `<span class="fix">반례: ${esc(i.counterexample)}</span>` : "";
      return `<div class="issue ${i.severity}"><span class="tag">${esc(i.code)}</span>
        <span>${esc(i.message)}${cx}</span></div>`;
    })
    .join("");
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// ---- SVG 래더 렌더러 ------------------------------------------------------
const LEFT_RAIL = 24, BUS_L = 64, SLOT = 100, ROW_H = 56, PAD_TOP = 26, COIL_W = 70;

function renderLadder(ladder) {
  const rungs = (ladder && ladder.rungs) || [];
  rungCountEl.textContent = rungs.length ? `${rungs.length}개 렁` : "";
  if (rungs.length === 0) {
    preview.innerHTML = '<div class="empty">왼쪽에 ST를 입력하면 즉시 래더가 그려집니다.</div>';
    return;
  }

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
  const totalH = y + 10;

  preview.innerHTML =
    `<svg width="${width}" height="${totalH}" xmlns="http://www.w3.org/2000/svg">` +
    parts.join("") +
    `</svg>`;

  // 접점 클릭 → NO/NC 토글 (ST 편집)
  preview.querySelectorAll("[data-toggle]").forEach((el) => {
    el.style.cursor = "pointer";
    el.addEventListener("click", () => {
      const ri = +el.getAttribute("data-rung");
      const sym = el.getAttribute("data-sym");
      const neg = el.getAttribute("data-neg") === "1";
      toggleContact(ri, sym, neg);
    });
  });
}

function drawRung(rung, ri, y0, h, busR, coilX, rightRail) {
  const top = y0 + PAD_TOP;
  const p = [];
  // 렁 주석
  p.push(`<text x="${BUS_L}" y="${y0 + 17}" fill="#7f8a9a" font-size="11">${esc(rung.comment || "렁 " + (ri + 1))}</text>`);
  // 좌/우 전원 레일
  p.push(line(LEFT_RAIL, y0, LEFT_RAIL, y0 + h, "var(--rail)", 3));
  p.push(line(rightRail, y0, rightRail, y0 + h, "var(--rail)", 3));

  const branches = rung.input_branches.length ? rung.input_branches : [{ elements: [] }];
  const rowYs = branches.map((_, i) => top + i * ROW_H + ROW_H / 2);

  // OR 버스 (분기 2개 이상)
  if (branches.length > 1) {
    p.push(line(BUS_L, rowYs[0], BUS_L, rowYs[rowYs.length - 1], "var(--wire)", 2));
    p.push(line(busR, rowYs[0], busR, rowYs[rowYs.length - 1], "var(--wire)", 2));
  }
  // 좌 레일 → 좌 버스
  p.push(line(LEFT_RAIL, rowYs[0], BUS_L, rowYs[0], "var(--wire)", 2));

  branches.forEach((b, bi) => {
    const yc = rowYs[bi];
    let x = BUS_L;
    if (b.elements.length === 0) {
      p.push(line(BUS_L, yc, busR, yc, "var(--wire)", 2)); // 항상 ON 와이어
    } else {
      b.elements.forEach((el, ci) => {
        const cx = BUS_L + ci * SLOT + SLOT / 2;
        p.push(line(x, yc, cx - 16, yc, "var(--wire)", 2));
        p.push(contact(cx, yc, el, ri));
        x = cx + 16;
      });
      p.push(line(x, yc, busR, yc, "var(--wire)", 2));
    }
  });

  // 우 버스 → 코일 → 우 레일
  const midY = rowYs[0];
  p.push(line(busR, midY, coilX - 16, midY, "var(--wire)", 2));
  (rung.outputs || []).forEach((out, oi) => {
    const yc = midY + oi * ROW_H;
    p.push(coil(coilX, yc, out));
    p.push(line(coilX + COIL_W - 16, yc, rightRail, yc, "var(--wire)", 2));
  });
  return `<g>${p.join("")}</g>`;
}

function line(x1, y1, x2, y2, color, w) {
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${w}"/>`;
}

function contact(cx, cy, el, ri) {
  const nc = el.element_type === "CONTACT_NC";
  const g = [];
  g.push(`<g data-toggle="1" data-rung="${ri}" data-sym="${esc(el.symbol)}" data-neg="${nc ? 1 : 0}">`);
  // 투명 히트박스
  g.push(`<rect x="${cx - 22}" y="${cy - 22}" width="44" height="44" fill="transparent"/>`);
  g.push(line(cx - 6, cy - 11, cx - 6, cy + 11, "#cdd6e3", 2));
  g.push(line(cx + 6, cy - 11, cx + 6, cy + 11, "#cdd6e3", 2));
  if (nc) g.push(line(cx - 9, cy + 11, cx + 9, cy - 11, "#cdd6e3", 2)); // NC 사선
  g.push(`<text x="${cx}" y="${cy - 16}" fill="#dce4f0" font-size="11" text-anchor="middle">${esc(el.symbol)}</text>`);
  if (el.address)
    g.push(`<text x="${cx}" y="${cy + 26}" fill="#6f7a8a" font-size="10" text-anchor="middle">${esc(el.address)}</text>`);
  g.push(`</g>`);
  return g.join("");
}

function coil(cx, cy, out) {
  const g = [];
  g.push(`<text x="${cx + 35}" y="${cy - 16}" fill="#9fe0b0" font-size="11" text-anchor="middle">${esc(out.symbol)}</text>`);
  g.push(`<path d="M ${cx} ${cy - 12} Q ${cx + 14} ${cy} ${cx} ${cy + 12}" fill="none" stroke="#46c46a" stroke-width="2"/>`);
  g.push(`<path d="M ${cx + 70} ${cy - 12} Q ${cx + 56} ${cy} ${cx + 70} ${cy + 12}" fill="none" stroke="#46c46a" stroke-width="2"/>`);
  if (out.address)
    g.push(`<text x="${cx + 35}" y="${cy + 26}" fill="#6f7a8a" font-size="10" text-anchor="middle">${esc(out.address)}</text>`);
  return g.join("");
}

// ---- 래더 → ST 역편집 (접점 토글) ----------------------------------------
function toggleContact(ri, sym, currentlyNegated) {
  if (!lastLadder) return;
  const out = lastLadder.rungs[ri].outputs[0];
  if (!out) return;
  const lines = st.value.split("\n");
  // 해당 출력의 대입문 찾기
  const re = new RegExp("^(\\s*" + escapeRe(out.symbol) + "\\s*:=\\s*)(.+?)(;\\s*)$");
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(re);
    if (!m) continue;
    let expr = m[2];
    const wb = "\\b" + escapeRe(sym) + "\\b";
    if (currentlyNegated) {
      // NOT SYM -> SYM
      expr = expr.replace(new RegExp("\\bNOT\\s+" + escapeRe(sym) + "\\b", "g"), sym);
    } else {
      // SYM -> NOT SYM (이미 NOT 붙은 건 제외)
      expr = expr.replace(new RegExp("(?<!NOT\\s)" + wb, "g"), "NOT " + sym);
    }
    lines[i] = m[1] + expr + m[3];
    st.value = lines.join("\n");
    runTranspile();
    return;
  }
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// ---- 이벤트 --------------------------------------------------------------
st.addEventListener("input", scheduleTranspile);
document.getElementById("examples").addEventListener("change", (e) => {
  if (EXAMPLES[e.target.value]) {
    st.value = EXAMPLES[e.target.value];
    runTranspile();
  }
  e.target.value = "";
});
document.getElementById("download").addEventListener("click", () => {
  if (!lastLadder) return;
  const blob = new Blob([JSON.stringify(lastLadder, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ladder.json";
  a.click();
});

// 초기 예제
st.value = EXAMPLES.selfhold;
runTranspile();
