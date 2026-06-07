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
  let simRunning = false, simEngine = null, simTimer = null;
  const SIM_STEP_MS = 100;  // 스캔 주기(브라우저 라이브 루프)
  let recipeFields = {};    // recipe_id -> [{key,label,default,kind}] (모듈 편집용)
  let editingIdx = -1;      // 현재 인라인 편집 중인 모듈 인덱스

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

  async function loadRecipes() {
    try {
      const list = await (await fetch("/api/recipes")).json();
      list.forEach((r) => { recipeFields[r.id] = r.fields || []; });
    } catch (e) { /* 오프라인이면 편집 폼 없이 진행 */ }
  }

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

  // 자유 문장 전체를 LLM 설계 에이전트로 — 여러 서브시스템 자동 분해(키워드 천장 돌파).
  async function handleDesign(text) {
    addMsg("u", esc(text));
    const m = addMsg("a", "🤖 설계 중…");
    const bubble = m.querySelector(".b");
    let res;
    try { res = await api("/api/design", { text }); }
    catch (e) { bubble.textContent = "서버 연결 실패: " + String(e); return; }
    if (res.project && (res.project.modules || []).length) {
      snapshot();
      adoptProject(res.project);
      const n = res.project.modules.length;
      const verdict = res.ok ? "✅ 검증 통과" : "⚠️ 검증 이슈 있음";
      const rev = res.revisions ? ` · 재설계 ${res.revisions}회` : "";
      bubble.innerHTML = `${n}개 서브시스템으로 설계했어요 — ${verdict}${rev}`;
      recompose();
    } else {
      bubble.innerHTML = "⚠ " + esc(res.error || "설계 실패");
    }
  }

  function adoptProject(proj) {
    project.title = proj.title || project.title;
    project.modules = (proj.modules || []).map((mod) => ({
      name: mod.name,
      recipe: mod.recipe || "",
      recipe_title: (mod.spec && mod.spec.title) || mod.recipe || mod.name,
      answers: mod.answers || {},
      shared: mod.shared || {},
      spec: mod.spec || null,
    }));
    project.cross_interlocks = proj.cross_interlocks || [];
    editingIdx = -1;
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

  function editorHTML(m, i) {
    const fields = recipeFields[m.recipe] || [];
    const rows = fields.map((f) => {
      const val = (m.answers && m.answers[f.key] != null) ? m.answers[f.key] : f.default;
      const num = f.kind && f.kind !== "symbol" ? 'type="number"' : "";
      return `<label style="display:flex;gap:6px;align-items:center;margin:3px 0;font-size:12px">
        <span style="flex:1;color:var(--dim)">${esc(f.label)}</span>
        <input data-fk="${esc(f.key)}" value="${esc(val)}" ${num}
          style="width:130px;background:var(--panel);color:var(--txt);border:1px solid var(--line);border-radius:5px;padding:3px 6px"/></label>`;
    }).join("");
    return `<div style="margin-top:8px;border-top:1px dashed var(--line);padding-top:6px">
      ${rows}
      <div class="row" style="gap:6px;margin-top:6px">
        <button data-apply="${i}" style="background:var(--accent);color:#06101e;border:none;border-radius:6px;padding:4px 10px;cursor:pointer">적용</button>
        <button data-cancel="1" style="background:var(--panel);color:var(--txt);border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer">취소</button>
      </div></div>`;
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
      const canEdit = (recipeFields[m.recipe] || []).length > 0;
      html += `<div class="module"><div class="row">
        <span class="nm">${esc(m.name)}</span>
        <span class="rc">${esc(m.recipe_title)}</span>
        ${canEdit ? `<button class="x" data-edit="${i}" title="편집" style="color:var(--accent);font-size:13px">✎</button>` : ""}
        <button class="x" data-rm="${i}" title="삭제">×</button></div>
        <div class="io">IN ${(s.inputs || []).map(pretty).join(", ") || "—"}</div>
        <div class="io">OUT ${(s.outputs || []).map(pretty).join(", ") || "—"}</div>
        ${s.safety_note ? `<div class="sn">⚠ ${esc(s.safety_note)}</div>` : ""}
        ${editingIdx === i ? editorHTML(m, i) : ""}</div>`;
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
    el.querySelectorAll("[data-edit]").forEach((b) =>
      b.onclick = () => { editingIdx = +b.dataset.edit; renderProject(); });
    el.querySelectorAll("[data-cancel]").forEach((b) =>
      b.onclick = () => { editingIdx = -1; renderProject(); });
    el.querySelectorAll("[data-apply]").forEach((b) =>
      b.onclick = () => {
        const i = +b.dataset.apply;
        const ans = {};
        b.closest(".module").querySelectorAll("[data-fk]").forEach((inp) => {
          const v = inp.value.trim(); if (v) ans[inp.dataset.fk] = v;
        });
        snapshot(); project.modules[i].answers = ans; editingIdx = -1; recompose();
      });
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
    persist();  // 모든 상태 변경마다 로컬 자동저장(빈 상태 포함)
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
  }

  function clearViews() {
    $("ladder").innerHTML = '<div class="empty">서브시스템을 추가하면 래더가 그려집니다.</div>';
    $("st").textContent = "(아직 없음)";
    $("addr").querySelector("tbody").innerHTML = "";
    $("verify").innerHTML = '<div class="empty">검증 결과가 여기 표시됩니다.</div>';
    $("sim-inputs").innerHTML = '<div class="hint">서브시스템을 추가하면 입력 스위치가 생깁니다.</div>';
    $("sim-outputs").innerHTML = '<div class="hint">—</div>';
  }
  function renderLadder(ladder, state) {
    $("ladder").innerHTML = (window.LadderRender && ladder)
      ? window.LadderRender.svg(ladder, state)
      : '<div class="empty">래더 없음</div>';
  }
  function ladderVisible() {
    const v = document.getElementById("v-ladder");
    return v && v.classList.contains("on");
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

  // ── 라이브 시뮬 (브라우저 내 SimEngine 스캔 루프 — 서버 왕복 없음) ───────────
  function cssesc(s) { return String(s).replace(/["\\]/g, "\\$&"); }

  function rebuildSimInputs(res) {
    // 검증된 ST 로 브라우저 스캔 엔진을 새로 만든다(파이썬 시뮬레이터와 패리티 보장).
    simEngine = (window.SimEngine && res.structured_text)
      ? window.SimEngine.create(res.structured_text) : null;
    const uniq = simEngine ? simEngine.inputs : [];
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
    renderOutputs(simEngine ? simEngine.outputs : [], {});
    tick(); // 현재 입력으로 1스캔 — 즉시 출력 반영
  }
  function renderOutputs(outs, state) {
    const uniq = [...new Set(outs)];
    $("sim-outputs").innerHTML = uniq.length
      ? uniq.map((s) => `<div class="io-item">
          <span class="lamp ${state[s] ? "outon" : ""}" data-ol="${esc(s)}"></span>
          <span class="lab">${pretty(s)}</span></div>`).join("")
      : '<div class="hint">출력이 없습니다.</div>';
  }
  function updateLamps(r) {
    for (const s in r.outputs)
      document.querySelectorAll(`[data-ol="${cssesc(s)}"]`).forEach((e) => e.classList.toggle("outon", r.outputs[s]));
    for (const s in r.inputs) {
      document.querySelectorAll(`[data-il="${cssesc(s)}"]`).forEach((e) => e.classList.toggle("on", r.inputs[s]));
    }
  }
  function tick() {
    if (!simEngine) return;
    const r = simEngine.step(forced, SIM_STEP_MS);
    updateLamps(r);
    // 래더 파워플로우: 매 스캔 table 로 도통 접점/경로/코일을 라이브 하이라이트.
    if (last && last.ladder && ladderVisible()) renderLadder(last.ladder, r.table);
  }
  function toggleInput(sym) {
    forced[sym] = !forced[sym];
    document.querySelectorAll(`[data-sw="${cssesc(sym)}"]`).forEach((e) => e.classList.toggle("on", forced[sym]));
    document.querySelectorAll(`[data-il="${cssesc(sym)}"]`).forEach((e) => e.classList.toggle("on", forced[sym]));
    if (!simRunning) tick(); // 정지 상태에서도 토글하면 1스캔 반영(조합/즉시 결과)
  }
  function toggleSim() {
    simRunning = !simRunning;
    const b = $("sim-toggle");
    b.textContent = simRunning ? "■ 정지" : "▶ 가동";
    b.classList.toggle("run", !simRunning);
    if (simTimer) { clearInterval(simTimer); simTimer = null; }
    if (simRunning) simTimer = setInterval(tick, SIM_STEP_MS);
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

  // ── 로컬 저장 (localStorage 자동저장 + .ldproj 파일 내보내기/가져오기) ───────────
  const LS_KEY = "ladder-studio:project";
  const PROJ_VERSION = 1;
  function projectDoc() {
    return { v: PROJ_VERSION, title: project.title,
      modules: project.modules, cross_interlocks: project.cross_interlocks };
  }
  function applyDoc(doc) {
    // 신뢰 못 할 입력 방어: 모양 검증 후에만 채택.
    if (!doc || typeof doc !== "object" || !Array.isArray(doc.modules)) throw new Error("형식 오류");
    project.title = typeof doc.title === "string" ? doc.title : "내 라인";
    project.modules = doc.modules.filter((m) => m && typeof m.name === "string")
      .map((m) => ({ name: m.name, recipe: m.recipe || "", recipe_title: m.recipe_title || m.recipe || m.name,
        answers: (m.answers && typeof m.answers === "object") ? m.answers : {},
        shared: (m.shared && typeof m.shared === "object") ? m.shared : {},
        spec: (m.spec && typeof m.spec === "object") ? m.spec : null }));
    project.cross_interlocks = Array.isArray(doc.cross_interlocks)
      ? doc.cross_interlocks.filter((c) => c && c.output_a && c.output_b)
        .map((c) => ({ output_a: c.output_a, output_b: c.output_b, reason: c.reason || "" })) : [];
  }
  function persist() {
    try { localStorage.setItem(LS_KEY, JSON.stringify(projectDoc())); } catch (e) { /* 용량초과 등 무시 */ }
  }
  function loadLocal() {
    let raw; try { raw = localStorage.getItem(LS_KEY); } catch (e) { return; }
    if (!raw) return;
    try { applyDoc(JSON.parse(raw)); } catch (e) { return; }
  }
  function exportProject() {
    const name = (project.title || "ladder").replace(/[^\w가-힣 .-]/g, "_").trim() || "ladder";
    download(`${name}.ldproj`, JSON.stringify(projectDoc(), null, 2));
    setStatus("✓ 프로젝트 저장(.ldproj)", "ok");
  }
  function importProject(file) {
    const r = new FileReader();
    r.onload = () => {
      try { applyDoc(JSON.parse(String(r.result))); }
      catch (e) { setStatus("열기 실패: 형식이 올바르지 않습니다", "err"); return; }
      history.length = 0; editingIdx = -1;
      setStatus("✓ 프로젝트 열기 완료", "ok");
      recompose();
    };
    r.readAsText(file);
  }
  function newProject() {
    if (project.modules.length && !confirm("현재 프로젝트를 비우고 새로 시작할까요?")) return;
    snapshot();
    project.title = "내 라인"; project.modules = []; project.cross_interlocks = [];
    editingIdx = -1; $("chat-log").innerHTML = "";
    recompose();
  }

  // ── 탭 ──────────────────────────────────────────────────────────────────────
  document.querySelectorAll(".tab").forEach((t) => t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("on"));
    document.querySelectorAll(".view").forEach((x) => x.classList.remove("on"));
    t.classList.add("on"); $("v-" + t.dataset.v).classList.add("on");
  });

  // ── 이벤트 ────────────────────────────────────────────────────────────────────
  $("send").onclick = () => { const v = $("nl").value.trim(); if (v) { $("nl").value = ""; handleNL(v); } };
  $("design-btn").onclick = () => { const v = $("nl").value.trim(); if (v) { $("nl").value = ""; handleDesign(v); } };
  $("nl").addEventListener("keydown", (e) => { if (e.key === "Enter") $("send").click(); });
  $("btn-undo").onclick = undo;
  $("btn-emit").onclick = exportEmit;
  $("btn-xml").onclick = exportXml;
  $("btn-new").onclick = newProject;
  $("btn-save").onclick = exportProject;
  $("btn-open").onclick = () => $("file-open").click();
  $("file-open").addEventListener("change", (e) => {
    const f = e.target.files && e.target.files[0];
    if (f) importProject(f);
    e.target.value = "";  // 같은 파일 다시 열기 허용
  });
  $("sim-toggle").onclick = toggleSim;
  $("sim-once").onclick = tick;

  loadRecipes();
  loadLocal();           // 새로고침해도 직전 작업 복원(로컬 자동저장)
  if (project.modules.length) recompose();
  else renderProject();
})();
