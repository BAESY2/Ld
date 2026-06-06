/* Ladder Studio — 자연어 공장 자동화 설계 워크스페이스.
 *
 * vibe 루프: 한국어 한 문장 → /api/project/nl-add 로 모듈 제안 → 프로젝트에 추가
 *   → /api/project/compose 로 즉시 ST·래더·검증·디바이스맵 갱신 → 우측 라이브 시뮬.
 * 모든 합성·검증·시뮬은 결정론 백엔드(키 불필요)를 쓴다. LLM 자유생성 없음.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pretty = (sym) => esc(String(sym).replace(/__/g, " · "));

  // ── 상태 ────────────────────────────────────────────────────────────────
  const project = { title: "내 라인", modules: [], cross_interlocks: [] };
  let last = null;          // 최근 compose 응답
  const history = [];       // 되돌리기용 프로젝트 스냅샷
  const forced = {};        // 시뮬 강제 입력 {symbol: bool}
  let simRunning = false, simEpoch = 0, simEvents = [];

  async function api(path, body) {
    const r = await fetch(path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return r.json();
  }
  function setStatus(t, cls) {
    const s = $("status"); s.textContent = t || ""; s.style.color =
      cls === "err" ? "var(--err)" : cls === "ok" ? "var(--ok)" : "var(--dim)";
  }
  function snapshot() { history.push(JSON.stringify({ m: project.modules, c: project.cross_interlocks })); }
  function takenNames() { return project.modules.map((m) => m.name); }

  // ── 채팅 ──────────────────────────────────────────────────────────────────
  function addMsg(who, html) {
    const log = $("chat-log");
    const d = document.createElement("div");
    d.className = "msg " + who;
    d.innerHTML = `<span class="b">${html}</span>`;
    log.appendChild(d); log.scrollTop = log.scrollHeight;
    return d;
  }

  async function handleNL(text) {
    addMsg("u", esc(text));
    let res;
    try { res = await api("/api/project/nl-add", { text, existing_names: takenNames() }); }
    catch (e) { addMsg("a", "서버 연결 실패: " + esc(String(e))); return; }
    if (res.safety_warning) addMsg("a", "🛑 " + esc(res.safety_warning));
    if (res.out_of_scope) { addMsg("a", "⚠ " + esc(res.suggestion)); return; }
    if (res.confident) {
      addMsg("a", esc(res.suggestion) + ` <b>(${esc(res.suggested_name)})</b>`);
      addModule(res.recipe, res.suggested_name, res.recipe_title, res.answers || {});
    } else {
      // 확신 못 함 → 후보 칩 제시(클릭해 선택)
      const m = addMsg("a", esc(res.suggestion));
      const chips = document.createElement("div"); chips.className = "chips";
      (res.ranked || []).forEach((c) => {
        const b = document.createElement("span"); b.className = "chip";
        b.textContent = c.title;
        b.onclick = () => { addModule(c.id, suggestName(c.id), c.title, res.answers || {}); chips.remove(); };
        chips.appendChild(b);
      });
      m.appendChild(chips);
    }
  }

  function suggestName(recipeId) {
    const base = (recipeId.split("_")[0] || "mod");
    const taken = new Set(takenNames());
    let i = 1; while (taken.has(base + i)) i++;
    return base + i;
  }

  // ── 프로젝트 편집 ───────────────────────────────────────────────────────────
  function addModule(recipe, name, title, answers) {
    snapshot();
    project.modules.push({ name, recipe, recipe_title: title || recipe, answers: answers || {}, shared: {} });
    recompose();
  }
  function removeModule(idx) {
    snapshot();
    const gone = project.modules.splice(idx, 1)[0];
    // 사라진 모듈을 참조하는 교차 인터락도 제거(렌더 심볼 프리픽스로 식별).
    project.cross_interlocks = project.cross_interlocks.filter(
      (ci) => !ci.output_a.startsWith(gone.name + "__") && !ci.output_b.startsWith(gone.name + "__"));
    recompose();
  }
  function undo() {
    if (!history.length) { setStatus("되돌릴 변경이 없습니다", "dim"); return; }
    const s = JSON.parse(history.pop());
    project.modules = s.m; project.cross_interlocks = s.c;
    recompose();
  }

  function renderProject() {
    const el = $("project-list");
    if (!project.modules.length) {
      el.innerHTML = '<div class="empty">아직 서브시스템이 없습니다.<br>아래 대화창에 한국어로 "버튼 누르면 모터가 돈다" 처럼 입력해 보세요.</div>';
      return;
    }
    const summ = (last && last.modules) || [];
    let html = "";
    project.modules.forEach((m, i) => {
      const s = summ.find((x) => x.name === m.name) || { inputs: [], outputs: [] };
      html += `<div class="module"><div class="row">
        <span class="nm">${esc(m.name)}</span>
        <span class="rc">${esc(m.recipe_title)}</span>
        <button class="x" data-rm="${i}" title="삭제">×</button></div>
        <div class="io">IN ${(s.inputs || []).map(pretty).join(", ") || "—"}</div>
        <div class="io">OUT ${(s.outputs || []).map(pretty).join(", ") || "—"}</div></div>`;
    });
    // 교차 인터락
    html += `<div class="sec-title">교차 인터락 (모듈 간 동시 금지)</div>`;
    project.cross_interlocks.forEach((ci, i) => {
      html += `<div class="module"><div class="row">
        <span class="rc">${pretty(ci.output_a)} ⊥ ${pretty(ci.output_b)}</span>
        <button class="x" data-rmci="${i}" title="삭제">×</button></div></div>`;
    });
    const outs = summ.flatMap((s) => s.outputs || []);
    if (outs.length >= 2) {
      const opt = outs.map((o) => `<option value="${esc(o)}">${pretty(o)}</option>`).join("");
      html += `<div class="module"><div class="row" style="gap:4px">
        <select id="ci-a" style="flex:1;min-width:0;background:var(--panel);color:var(--txt);border:1px solid var(--line);border-radius:6px;padding:4px">${opt}</select>
        <span>⊥</span>
        <select id="ci-b" style="flex:1;min-width:0;background:var(--panel);color:var(--txt);border:1px solid var(--line);border-radius:6px;padding:4px">${opt}</select>
        <button id="ci-add" style="background:var(--accent);color:#06101e;border:none;border-radius:6px;padding:4px 8px;cursor:pointer">+ 추가</button>
      </div></div>`;
    }
    el.innerHTML = html;
    el.querySelectorAll("[data-rm]").forEach((b) =>
      b.onclick = () => removeModule(+b.dataset.rm));
    el.querySelectorAll("[data-rmci]").forEach((b) =>
      b.onclick = () => { snapshot(); project.cross_interlocks.splice(+b.dataset.rmci, 1); recompose(); });
    const add = $("ci-add");
    if (add) add.onclick = () => {
      const a = $("ci-a").value, b = $("ci-b").value;
      if (a === b) { setStatus("서로 다른 출력을 고르세요", "err"); return; }
      snapshot();
      project.cross_interlocks.push({ output_a: a, output_b: b, reason: "동시 가동 금지" });
      recompose();
    };
  }

  // ── 합성 → 래더/ST/맵/검증 ─────────────────────────────────────────────────
  async function recompose() {
    renderProject();
    if (!project.modules.length) { last = null; clearViews(); return; }
    setStatus("합성 중…", "dim");
    let res;
    try { res = await api("/api/project/compose", project); }
    catch (e) { setStatus("합성 실패: " + e, "err"); return; }
    last = res;
    if (res.error) { setStatus(res.error, "err"); }
    renderProject(); // 모듈 IO 요약 채워 다시 그림
    renderLadder(res.ladder);
    $("st").textContent = res.structured_text || "(없음)";
    renderAddr(res.address_map || []);
    renderVerify(res.verification, res.error);
    $("explain").innerHTML = esc(res.explanation || "—").replace(/\n/g, "<br>");
    rebuildSimInputs(res);
    setStatus(res.ok ? "✓ 검증 통과" : "검증 이슈 있음", res.ok ? "ok" : "err");
    if (simRunning) runSim();
  }

  function clearViews() {
    $("ladder").innerHTML = '<div class="empty">서브시스템을 추가하면 래더가 그려집니다.</div>';
    $("st").textContent = "(아직 없음)";
    $("addr").querySelector("tbody").innerHTML = "";
    $("verify").innerHTML = '<div class="empty">검증 결과가 여기 표시됩니다.</div>';
    $("sim-inputs").innerHTML = '<div class="hint">서브시스템을 추가하면 입력 스위치가 생깁니다.</div>';
    $("sim-outputs").innerHTML = '<div class="hint">—</div>';
  }
  function renderLadder(ladder) {
    $("ladder").innerHTML = (window.LadderRender && ladder)
      ? window.LadderRender.svg(ladder)
      : '<div class="empty">래더 없음</div>';
  }
  function renderAddr(map) {
    $("addr").querySelector("tbody").innerHTML =
      map.map((e) => `<tr><td>${pretty(e.symbol)}</td><td>${esc(e.address)}</td></tr>`).join("");
  }
  function renderVerify(v, err) {
    const box = $("verify");
    const items = [];
    if (err) items.push(`<div class="verdict"><span class="ic">⛔</span><div>${esc(err)}</div></div>`);
    if (v) {
      items.push(`<div class="verdict"><span class="ic">${v.passed ? "✅" : "⚠️"}</span>
        <div><b>${v.passed ? "검증 통과" : "검증 이슈"}</b> — 이중코일·인터락·도달성 결정론 검사</div></div>`);
      (v.issues || []).forEach((i) => {
        const ic = i.severity === "error" ? "❌" : "⚠️";
        const ce = i.counterexample ? `<div class="hint">반례: ${esc(i.counterexample)}</div>` : "";
        items.push(`<div class="verdict"><span class="ic">${ic}</span><div>[${esc(i.code)}] ${esc(i.message)}${ce}</div></div>`);
      });
      if (v.suggested_fix) items.push(`<div class="verdict"><span class="ic">💡</span><div>${esc(v.suggested_fix)}</div></div>`);
    }
    box.innerHTML = items.join("") || '<div class="empty">검증 결과가 여기 표시됩니다.</div>';
  }

  // ── 라이브 시뮬 ─────────────────────────────────────────────────────────────
  function rebuildSimInputs(res) {
    const ins = (res.modules || []).flatMap((m) => m.inputs || []);
    const uniq = [...new Set(ins)];
    Object.keys(forced).forEach((k) => { if (!uniq.includes(k)) delete forced[k]; });
    uniq.forEach((s) => { if (!(s in forced)) forced[s] = false; });
    const box = $("sim-inputs");
    box.innerHTML = uniq.length
      ? uniq.map((s) => `<div class="io-item">
          <span class="lamp ${forced[s] ? "on" : ""}" data-il="${esc(s)}"></span>
          <span class="lab">${pretty(s)}</span>
          <span class="sw ${forced[s] ? "on" : ""}" data-sw="${esc(s)}"></span></div>`).join("")
      : '<div class="hint">입력이 없습니다.</div>';
    box.querySelectorAll("[data-sw]").forEach((sw) =>
      sw.onclick = () => toggleInput(sw.dataset.sw));
    renderOutputs((res.modules || []).flatMap((m) => m.outputs || []), {});
  }
  function renderOutputs(outs, state) {
    const uniq = [...new Set(outs)];
    $("sim-outputs").innerHTML = uniq.length
      ? uniq.map((s) => `<div class="io-item">
          <span class="lamp ${state[s] ? "outon" : ""}"></span>
          <span class="lab">${pretty(s)}</span></div>`).join("")
      : '<div class="hint">출력이 없습니다.</div>';
  }
  function toggleInput(sym) {
    forced[sym] = !forced[sym];
    if (simRunning) simEvents.push([Date.now() - simEpoch, { [sym]: forced[sym] }]);
    // 입력 램프/스위치 즉시 갱신
    document.querySelectorAll(`[data-sw="${cssesc(sym)}"]`).forEach((e) => e.classList.toggle("on", forced[sym]));
    document.querySelectorAll(`[data-il="${cssesc(sym)}"]`).forEach((e) => e.classList.toggle("on", forced[sym]));
    if (simRunning) runSim(); else runSim(true);
  }
  function cssesc(s) { return String(s).replace(/["\\]/g, "\\$&"); }

  async function runSim(once) {
    if (!last || !last.structured_text) return;
    let timeline, duration;
    if (once || !simRunning) {
      timeline = [[0, { ...forced }]]; duration = 300;
    } else {
      timeline = simEvents.length ? simEvents : [[0, { ...forced }]];
      duration = Math.min(60000, Math.max(800, (simEvents.length ? simEvents[simEvents.length - 1][0] : 0) + 1500));
    }
    let res;
    try { res = await api("/api/simulate", { st_code: last.structured_text, inputs_timeline: timeline, duration_ms: duration, step_ms: 100 }); }
    catch (e) { return; }
    if (!res.ok || !res.samples || !res.samples.length) { return; }
    const lastS = res.samples[res.samples.length - 1];
    renderOutputs(res.outputs || [], lastS.outputs || {});
  }

  function toggleSim() {
    simRunning = !simRunning;
    const b = $("sim-toggle");
    b.textContent = simRunning ? "■ 정지" : "▶ 가동";
    b.classList.toggle("run", !simRunning);
    if (simRunning) { simEpoch = Date.now(); simEvents = [[0, { ...forced }]]; runSim(); }
  }

  // ── 내보내기 ────────────────────────────────────────────────────────────────
  async function exportEmit() {
    if (!last || !last.structured_text) { setStatus("먼저 설계를 만드세요", "err"); return; }
    const res = await api("/api/emit", { st_code: last.structured_text, vendor: $("vendor").value });
    if (!res.ok) { setStatus(res.error || "내보내기 실패", "err"); return; }
    download(`${project.title || "ladder"}_${res.vendor}.txt`, res.text);
    setStatus("✓ " + res.vendor + " 래더 내보냄", "ok");
  }
  async function exportXml() {
    if (!last || !last.structured_text) { setStatus("먼저 설계를 만드세요", "err"); return; }
    const res = await api("/api/export/plcopen", { st_code: last.structured_text, title: project.title });
    if (!res.ok) { setStatus(res.error || "내보내기 실패", "err"); return; }
    download(`${project.title || "ladder"}.xml`, res.content);
    setStatus("✓ PLCopen XML 내보냄", "ok");
  }
  function download(name, text) {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    URL.revokeObjectURL(a.href);
  }

  // ── 탭 ──────────────────────────────────────────────────────────────────────
  document.querySelectorAll(".tab").forEach((t) => t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("on"));
    document.querySelectorAll(".view").forEach((x) => x.classList.remove("on"));
    t.classList.add("on"); $("v-" + t.dataset.v).classList.add("on");
  });

  // ── 이벤트 ────────────────────────────────────────────────────────────────────
  $("send").onclick = () => { const v = $("nl").value.trim(); if (v) { $("nl").value = ""; handleNL(v); } };
  $("nl").addEventListener("keydown", (e) => { if (e.key === "Enter") $("send").click(); });
  $("btn-undo").onclick = undo;
  $("btn-emit").onclick = exportEmit;
  $("btn-xml").onclick = exportXml;
  $("sim-toggle").onclick = toggleSim;
  $("sim-once").onclick = () => runSim(true);

  renderProject();
})();
