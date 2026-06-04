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

// ---- 실행취소/다시실행 스택 (Undo/Redo) ------------------------------------
const MAX_HISTORY = 200;
let undoStack = [];   // {text, selStart, selEnd}[]
let redoStack = [];
let _suppressSnapshot = false;

function snapshot() {
  if (_suppressSnapshot) return;
  const cur = st.value;
  const top = undoStack[undoStack.length - 1];
  if (top && top.text === cur) return; // 중복 방지
  undoStack.push({ text: cur, selStart: st.selectionStart, selEnd: st.selectionEnd });
  if (undoStack.length > MAX_HISTORY) undoStack.shift();
  redoStack = []; // 새 입력이 오면 redo 초기화
}

function applySnapshot(snap) {
  _suppressSnapshot = true;
  st.value = snap.text;
  try { st.setSelectionRange(snap.selStart, snap.selEnd); } catch (_) {}
  _suppressSnapshot = false;
}

function undo() {
  if (undoStack.length <= 1) return; // 최초 상태는 유지
  const cur = undoStack.pop();
  redoStack.push(cur);
  const snap = undoStack[undoStack.length - 1];
  applySnapshot(snap);
  runTranspile();
}

function redo() {
  if (redoStack.length === 0) return;
  const snap = redoStack.pop();
  undoStack.push(snap);
  applySnapshot(snap);
  runTranspile();
}

// ---- 라이브 변환 (디바운스) ------------------------------------------------
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

function renderIssues(issues, extra) {
  let html = "";
  if (extra) html += extra;
  if (!issues || issues.length === 0) {
    html += '<div class="issue"><span style="color:var(--muted)">문제 없음 ✓</span></div>';
  } else {
    html += issues
      .map((i) => {
        const cx = i.counterexample ? `<span class="fix">반례: ${esc(i.counterexample)}</span>` : "";
        return `<div class="issue ${i.severity}"><span class="tag">${esc(i.code)}</span>
          <span>${esc(i.message)}${cx}</span></div>`;
      })
      .join("");
  }
  issuesEl.innerHTML = html;
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// ---- SVG 래더 렌더러 -------------------------------------------------------
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
      snapshot(); // 토글 전 상태 저장
      toggleContact(ri, sym, neg);
    });
  });

  // 라벨 클릭 → 심볼 이름 변경
  preview.querySelectorAll("[data-rename]").forEach((el) => {
    el.style.cursor = "text";
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      const sym = el.getAttribute("data-rename");
      openRenamePrompt(sym, el);
    });
  });
}

function drawRung(rung, ri, y0, h, busR, coilX, rightRail) {
  const top = y0 + PAD_TOP;
  const p = [];
  // 렁 인덱스 + 주석
  const rungLabel = `[${ri + 1}] ${rung.comment || ""}`;
  p.push(`<text x="${BUS_L}" y="${y0 + 17}" fill="#7f8a9a" font-size="11">${esc(rungLabel)}</text>`);
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
  // 접점 몸체 (토글 가능)
  g.push(`<g data-toggle="1" data-rung="${ri}" data-sym="${esc(el.symbol)}" data-neg="${nc ? 1 : 0}">`);
  g.push(`<rect x="${cx - 22}" y="${cy - 22}" width="44" height="44" fill="transparent"/>`);
  g.push(line(cx - 6, cy - 11, cx - 6, cy + 11, "#cdd6e3", 2));
  g.push(line(cx + 6, cy - 11, cx + 6, cy + 11, "#cdd6e3", 2));
  if (nc) g.push(line(cx - 9, cy + 11, cx + 9, cy - 11, "#cdd6e3", 2));
  g.push(`</g>`);
  // 라벨 (이름 변경 가능) — 별도 그룹
  g.push(`<text data-rename="${esc(el.symbol)}" x="${cx}" y="${cy - 16}" fill="#dce4f0" font-size="11" text-anchor="middle" style="cursor:text">${esc(el.symbol)}</text>`);
  if (el.address)
    g.push(`<text x="${cx}" y="${cy + 26}" fill="#6f7a8a" font-size="10" text-anchor="middle">${esc(el.address)}</text>`);
  return g.join("");
}

function coil(cx, cy, out) {
  const g = [];
  // 코일 라벨 (이름 변경 가능)
  g.push(`<text data-rename="${esc(out.symbol)}" x="${cx + 35}" y="${cy - 16}" fill="#9fe0b0" font-size="11" text-anchor="middle" style="cursor:text">${esc(out.symbol)}</text>`);
  g.push(`<path d="M ${cx} ${cy - 12} Q ${cx + 14} ${cy} ${cx} ${cy + 12}" fill="none" stroke="#46c46a" stroke-width="2"/>`);
  g.push(`<path d="M ${cx + 70} ${cy - 12} Q ${cx + 56} ${cy} ${cx + 70} ${cy + 12}" fill="none" stroke="#46c46a" stroke-width="2"/>`);
  if (out.address)
    g.push(`<text x="${cx + 35}" y="${cy + 26}" fill="#6f7a8a" font-size="10" text-anchor="middle">${esc(out.address)}</text>`);
  return g.join("");
}

// ---- 래더 → ST 역편집 (접점 토글) -----------------------------------------
function toggleContact(ri, sym, currentlyNegated) {
  if (!lastLadder) return;
  const out = lastLadder.rungs[ri].outputs[0];
  if (!out) return;
  const lines = st.value.split("\n");
  const re = new RegExp("^(\\s*" + escapeRe(out.symbol) + "\\s*:=\\s*)(.+?)(;\\s*)$");
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(re);
    if (!m) continue;
    let expr = m[2];
    const wb = "\\b" + escapeRe(sym) + "\\b";
    if (currentlyNegated) {
      expr = expr.replace(new RegExp("\\bNOT\\s+" + escapeRe(sym) + "\\b", "g"), sym);
    } else {
      expr = expr.replace(new RegExp("(?<!NOT\\s)" + wb, "g"), "NOT " + sym);
    }
    lines[i] = m[1] + expr + m[3];
    _suppressSnapshot = true;
    st.value = lines.join("\n");
    _suppressSnapshot = false;
    snapshot(); // 토글 후 상태 저장
    runTranspile();
    return;
  }
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// ---- 심볼 이름 변경 (인라인 프롬프트) -------------------------------------
function openRenamePrompt(oldSym, anchorEl) {
  // 기존 프롬프트 제거
  const existing = document.getElementById("rename-popup");
  if (existing) existing.remove();

  const popup = document.createElement("div");
  popup.id = "rename-popup";
  popup.style.cssText =
    "position:fixed;background:#1e2530;border:1px solid #3a4555;border-radius:8px;" +
    "padding:10px 12px;z-index:1000;box-shadow:0 4px 20px rgba(0,0,0,.5);display:flex;gap:8px;align-items:center;";

  const rect = anchorEl.getBoundingClientRect();
  popup.style.top = (rect.bottom + 6) + "px";
  popup.style.left = Math.max(4, rect.left - 40) + "px";

  const input = document.createElement("input");
  input.value = oldSym;
  input.style.cssText =
    "background:#0f1115;border:1px solid #3a4555;border-radius:4px;color:#e6e9ef;" +
    "padding:4px 8px;font-size:12px;font-family:ui-monospace,monospace;width:140px;outline:none;";

  const btn = document.createElement("button");
  btn.textContent = "변경";
  btn.style.cssText =
    "background:#2a5db0;color:#fff;border:none;border-radius:4px;padding:4px 10px;" +
    "font-size:12px;cursor:pointer;";

  const cancel = document.createElement("button");
  cancel.textContent = "취소";
  cancel.style.cssText =
    "background:transparent;color:#8b94a3;border:1px solid #3a4555;border-radius:4px;" +
    "padding:4px 8px;font-size:12px;cursor:pointer;";

  popup.appendChild(input);
  popup.appendChild(btn);
  popup.appendChild(cancel);
  document.body.appendChild(popup);
  input.focus();
  input.select();

  function doRename() {
    const newSym = input.value.trim();
    popup.remove();
    if (!newSym || newSym === oldSym) return;
    snapshot();
    // 전체 단어 치환 (ST 소스에서)
    const re = new RegExp("\\b" + escapeRe(oldSym) + "\\b", "g");
    st.value = st.value.replace(re, newSym);
    snapshot();
    runTranspile();
  }

  btn.addEventListener("click", doRename);
  cancel.addEventListener("click", () => popup.remove());
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doRename();
    if (e.key === "Escape") popup.remove();
  });

  // 바깥 클릭 시 닫기
  setTimeout(() => {
    document.addEventListener("click", function handler(e) {
      if (!popup.contains(e.target)) {
        popup.remove();
        document.removeEventListener("click", handler);
      }
    });
  }, 0);
}

// ---- 자연어 입력 (NL 패널) ------------------------------------------------
const nlInput = document.getElementById("nl-input");
const nlBtn = document.getElementById("nl-btn");
const nlInfo = document.getElementById("nl-info");

nlBtn.addEventListener("click", runGenerate);
nlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) runGenerate();
});

async function runGenerate() {
  const req = nlInput.value.trim();
  if (!req) return;
  nlBtn.disabled = true;
  nlBtn.textContent = "생성 중…";
  nlInfo.style.display = "block";
  nlInfo.textContent = "요청 처리 중…";
  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: req }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      const msg = (errData && errData.detail) || (errData && errData.error) || `HTTP ${res.status}`;
      nlInfo.textContent = "⚠ " + msg;
      renderIssues([], `<div class="issue warning"><span class="tag">NL</span><span>자연어 생성 실패: ${esc(msg)}</span></div>`);
      return;
    }
    const data = await res.json();
    if (data.error) {
      nlInfo.textContent = "⚠ " + data.error;
      renderIssues([], `<div class="issue warning"><span class="tag">NL</span><span>${esc(data.error)}</span></div>`);
      return;
    }
    if (data.structured_text) {
      snapshot();
      st.value = data.structured_text;
      snapshot();
      runTranspile();
    }
    if (data.logic_analysis) {
      nlInfo.textContent = data.logic_analysis;
    } else {
      nlInfo.style.display = "none";
    }
  } catch (e) {
    nlInfo.textContent = "⚠ 서버 연결 실패 또는 엔드포인트 미구현";
    renderIssues([], `<div class="issue warning"><span class="tag">NL</span><span>자연어 API 접속 실패 (엔드포인트 미구현일 수 있음)</span></div>`);
  } finally {
    nlBtn.disabled = false;
    nlBtn.textContent = "생성";
  }
}

// NL 패널 토글
document.getElementById("nl-toggle").addEventListener("click", () => {
  const body = document.getElementById("nl-body");
  const btn = document.getElementById("nl-toggle");
  const collapsed = body.style.display === "none";
  body.style.display = collapsed ? "flex" : "none";
  btn.textContent = collapsed ? "▲" : "▼";
});

// ---- 에러코드 조회 패널 ---------------------------------------------------
const ecVendor = document.getElementById("ec-vendor");
const ecSearch = document.getElementById("ec-search");
const ecResults = document.getElementById("ec-results");

let ecTimer = null;
function scheduleEcSearch() {
  clearTimeout(ecTimer);
  ecTimer = setTimeout(runEcSearch, 300);
}

ecSearch.addEventListener("input", scheduleEcSearch);
ecVendor.addEventListener("change", scheduleEcSearch);

async function runEcSearch() {
  const q = ecSearch.value.trim();
  if (!q) {
    ecResults.innerHTML = '<div style="color:var(--muted);font-size:12px;padding:6px 0">검색어를 입력하세요.</div>';
    return;
  }
  const vendor = ecVendor.value;
  ecResults.innerHTML = '<div style="color:var(--muted);font-size:12px;padding:6px 0">검색 중…</div>';
  try {
    const res = await fetch(`/api/errorcodes?vendor=${encodeURIComponent(vendor)}&q=${encodeURIComponent(q)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const items = await res.json();
    renderEcResults(items);
  } catch (e) {
    ecResults.innerHTML = '<div style="color:var(--muted);font-size:12px;padding:6px 0">에러코드 DB 준비중</div>';
  }
}

function renderEcResults(items) {
  if (!items || items.length === 0) {
    ecResults.innerHTML = '<div style="color:var(--muted);font-size:12px;padding:6px 0">결과 없음</div>';
    return;
  }
  ecResults.innerHTML = items.map((item, idx) => {
    const id = `ec-card-${idx}`;
    const hasDetail = item.likely_cause || item.suggested_action;
    const sourceLink = item.source_url
      ? `<a href="${esc(item.source_url)}" target="_blank" rel="noopener" style="color:var(--accent);font-size:10px;margin-left:6px">문서 링크</a>`
      : "";
    const licenseBadge = item.license
      ? `<span style="background:#2a3445;color:var(--muted);font-size:10px;padding:1px 5px;border-radius:3px;margin-left:4px">${esc(item.license)}</span>`
      : "";
    const detail = hasDetail ? `
      <div id="${id}-detail" style="display:none;margin-top:6px;font-size:11px;color:#b0bac8;border-top:1px solid var(--border);padding-top:6px">
        ${item.likely_cause ? `<div><b>원인:</b> ${esc(item.likely_cause)}</div>` : ""}
        ${item.suggested_action ? `<div style="margin-top:3px"><b>조치:</b> ${esc(item.suggested_action)}</div>` : ""}
        ${sourceLink}
      </div>` : "";
    const expandBtn = hasDetail
      ? `<button onclick="toggleEcDetail('${id}')" style="background:transparent;border:none;color:var(--accent);font-size:10px;cursor:pointer;padding:0;margin-left:auto">상세 ▼</button>`
      : "";
    return `<div class="ec-card" style="background:#1a2030;border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin-bottom:6px">
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
        <span style="font-family:ui-monospace,monospace;font-size:12px;color:#e6e9ef;font-weight:600">${esc(item.code || "")}</span>
        <span style="font-size:12px;color:#c5cdd8">${esc(item.title || "")}</span>
        <span style="font-size:10px;color:var(--muted);background:#242b38;padding:1px 5px;border-radius:3px">${esc(item.category || "")}</span>
        ${licenseBadge}
        ${expandBtn}
      </div>
      ${detail}
    </div>`;
  }).join("");
}

function toggleEcDetail(id) {
  const el = document.getElementById(id + "-detail");
  if (!el) return;
  const visible = el.style.display !== "none";
  el.style.display = visible ? "none" : "block";
  // 버튼 텍스트 갱신
  const card = el.closest(".ec-card");
  if (card) {
    const btn = card.querySelector("button");
    if (btn) btn.textContent = visible ? "상세 ▼" : "상세 ▲";
  }
}

// 에러코드 패널 토글
document.getElementById("ec-toggle").addEventListener("click", () => {
  const body = document.getElementById("ec-body");
  const btn = document.getElementById("ec-toggle");
  const collapsed = body.style.display === "none";
  body.style.display = collapsed ? "block" : "none";
  btn.textContent = collapsed ? "▲" : "▼";
});

// ---- 이벤트 ----------------------------------------------------------------
st.addEventListener("input", () => {
  snapshot();
  scheduleTranspile();
});

document.addEventListener("keydown", (e) => {
  const mod = e.ctrlKey || e.metaKey;
  if (!mod) return;
  if (e.key === "z" || e.key === "Z") {
    if (e.shiftKey) {
      e.preventDefault();
      redo();
    } else {
      e.preventDefault();
      undo();
    }
  }
});

document.getElementById("examples").addEventListener("change", (e) => {
  if (EXAMPLES[e.target.value]) {
    snapshot();
    st.value = EXAMPLES[e.target.value];
    snapshot();
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
snapshot(); // 초기 스냅샷
runTranspile();
