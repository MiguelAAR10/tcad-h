// TCAD Studio — Phase 1.7 / Phase 4 v0 client logic.
// No frameworks. No external assets. Polling-based refresh.

(() => {
  "use strict";

  const REFRESH_MS = 5000;
  let lastSelectedRoomId = null;

  const $ = (sel) => document.querySelector(sel);
  const el = (tag, opts = {}) => {
    const node = document.createElement(tag);
    if (opts.cls) node.className = opts.cls;
    if (opts.text !== undefined) node.textContent = opts.text;
    if (opts.html !== undefined) node.innerHTML = opts.html;
    if (opts.attrs) for (const [k, v] of Object.entries(opts.attrs)) node.setAttribute(k, v);
    return node;
  };

  function fmtTimestamp(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleTimeString();
  }

  async function fetchState() {
    const r = await fetch("/api/state", { cache: "no-store" });
    if (!r.ok) throw new Error("state fetch failed: " + r.status);
    return r.json();
  }

  // ----- Phase 3.3: Atlas panel ------------------------------------------
  async function fetchAtlas() {
    const r = await fetch("/api/atlas", { cache: "no-store" });
    if (!r.ok) return null;
    return r.json();
  }

  function renderAtlas(atlas) {
    const summary = document.getElementById("atlas-summary");
    const layersNode = document.getElementById("atlas-layers");
    const hotsNode = document.getElementById("atlas-hotspots");
    if (!summary || !layersNode || !hotsNode) return;

    if (!atlas) {
      summary.textContent = "No atlas built yet. Run `python3 scripts/tcad_atlas.py build`.";
      layersNode.innerHTML = "";
      hotsNode.innerHTML = "";
      return;
    }
    summary.textContent =
      `${atlas.wps_total} WPs · ${(atlas.layers || []).length} layers · ` +
      `${(atlas.hotspots || []).filter(h => h.times_changed >= 2).length} hotspot(s) · ` +
      `generated ${(atlas.generated_at || "").slice(11, 19)}`;

    layersNode.innerHTML = "";
    const layers = atlas.layers || [];
    const max = Math.max(1, ...layers.map(l => l.files_changed_total));
    for (const L of layers) {
      const row = el("div", { cls: "atlas-layer-row" });
      row.appendChild(el("span", { cls: "layer-name", text: L.layer }));
      row.appendChild(el("span", { text: `WPs ${L.wps_touched_count}` }));
      row.appendChild(el("span", { text: `files ${L.files_changed_total}` }));
      const critTxt = L.critical_findings ? `crit ${L.critical_findings}` : "ok";
      row.appendChild(el("span", { text: critTxt }));
      const bar = el("div", { cls: "layer-bar" });
      bar.style.width = `${Math.round((L.files_changed_total / max) * 100)}%`;
      row.appendChild(bar);
      layersNode.appendChild(row);
    }

    hotsNode.innerHTML = "";
    const hots = (atlas.hotspots || []).filter(h => h.times_changed >= 2);
    if (hots.length === 0) return;
    hotsNode.appendChild(el("h3", { text: "Hotspots (≥2 touches)" }));
    for (const h of hots.slice(0, 10)) {
      const row = el("div", { cls: "atlas-hotspot-row" });
      row.appendChild(el("span", { cls: "times", text: `${h.times_changed}x` }));
      row.appendChild(el("code", { text: h.file }));
      row.appendChild(el("span", { cls: "muted small", text: `last: ${h.last_wp}` }));
      hotsNode.appendChild(row);
    }
  }

  // ----- Phase 3: Development Graph panel --------------------------------
  let lastGraphWp = null;

  async function fetchGraphList() {
    const r = await fetch("/api/graphs", { cache: "no-store" });
    if (!r.ok) return [];
    return r.json();
  }

  async function fetchGraph(wp) {
    const r = await fetch("/api/graph/" + encodeURIComponent(wp), { cache: "no-store" });
    if (!r.ok) return null;
    return r.json();
  }

  async function fetchMermaid(wp) {
    const r = await fetch("/api/mermaid/" + encodeURIComponent(wp), { cache: "no-store" });
    if (!r.ok) return null;
    return r.text();
  }

  function renderGraphSelector(graphs) {
    const sel = document.getElementById("graph-wp-select");
    if (!sel) return;
    const previous = sel.value;
    sel.innerHTML = "";
    if (graphs.length === 0) {
      const opt = el("option", { text: "(no graphs yet — run tcad_graph static)" });
      opt.disabled = true;
      sel.appendChild(opt);
      return;
    }
    const placeholder = el("option", { text: "Select a Work Package…", attrs: { value: "" } });
    sel.appendChild(placeholder);
    for (const g of graphs) {
      const tag = g.review_pass === true ? " · PASS"
                : g.review_pass === false ? " · FAIL"
                : "";
      const opt = el("option", {
        text: `${g.wp}${tag}`,
        attrs: { value: g.wp },
      });
      sel.appendChild(opt);
    }
    if (previous && graphs.some(g => g.wp === previous)) sel.value = previous;
  }

  function renderGates(graph) {
    const node = document.getElementById("graph-gates");
    node.innerHTML = "";
    const g = graph.gates || {};
    function chip(text, cls) {
      const c = el("span", { cls: `gate-chip ${cls}`, text });
      node.appendChild(c);
    }
    if (g.close_present) chip("close PRESENT", "gate-pass");
    else chip("close MISSING", "gate-fail");
    if (g.smoke_skipped) {
      chip("smoke SKIPPED", "gate-skipped");
    } else if (g.smoke_total > 0) {
      const ok = g.smoke_passed === g.smoke_total;
      chip(`smoke ${g.smoke_passed}/${g.smoke_total}`, ok ? "gate-pass" : "gate-fail");
    }
    if (g.review_present) {
      if (g.review_pass) chip("review PASS", "gate-pass");
      else chip(`review FAIL (${g.review_critical_count || 0})`, "gate-fail");
    } else {
      chip("review not run", "gate-skipped");
    }
  }

  function renderFindings(graph) {
    const node = document.getElementById("graph-findings");
    node.innerHTML = "";
    const crit = (graph.review_findings || []).filter(f => f.severity === "critical");
    if (crit.length === 0) return;
    const h = el("h3", { text: `${crit.length} critical findings` });
    node.appendChild(h);
    for (const f of crit) {
      const row = el("div", { cls: "finding-row" });
      row.appendChild(el("div", { html: `<span class="ftype">${f.type}</span> — ${escapeHTML(f.message || "")}` }));
      for (const loc of f.locations || []) {
        const fp = loc.file || f.file || "?";
        const ln = loc.line || "?";
        row.appendChild(el("div", { cls: "floc", text: `at ${fp}:${ln}` }));
      }
      node.appendChild(row);
    }
  }

  function renderFocus(graph) {
    const node = document.getElementById("graph-focus");
    node.innerHTML = "";
    const focus = graph.reviewer_focus || [];
    if (focus.length === 0) return;
    node.appendChild(el("h3", { text: "Reviewer focus" }));
    for (const f of focus) {
      const row = el("div", { cls: "focus-row" });
      row.appendChild(el("code", { text: f.file }));
      row.appendChild(el("span", { cls: "reason", text: "— " + (f.reason || "") }));
      node.appendChild(row);
    }
  }

  function renderSummary(graph) {
    const s = graph.summary || {};
    const node = document.getElementById("graph-summary");
    node.textContent =
      `${graph.wp}` +
      (graph.role ? ` (${graph.role})` : "") +
      ` — ${s.files_total ?? 0} files (` +
      `+${s.files_created ?? 0} new, ` +
      `~${s.files_modified ?? 0} mod, ` +
      `-${s.files_deleted ?? 0} del). ` +
      `Diff: +${s.additions ?? 0}/-${s.deletions ?? 0}.`;
  }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  async function refreshGraphPanel() {
    const sel = document.getElementById("graph-wp-select");
    if (!sel) return;
    try {
      const graphs = await fetchGraphList();
      renderGraphSelector(graphs);
      if (lastGraphWp && graphs.some(g => g.wp === lastGraphWp)) {
        sel.value = lastGraphWp;
        await loadGraph(lastGraphWp);
      }
    } catch (err) {
      console.warn("graph refresh failed", err);
    }
  }

  async function loadGraph(wp) {
    lastGraphWp = wp;
    if (!wp) return;
    const graph = await fetchGraph(wp);
    if (!graph) return;
    renderSummary(graph);
    renderGates(graph);
    renderFindings(graph);
    renderFocus(graph);
    const mermaid = await fetchMermaid(wp);
    document.getElementById("graph-mermaid").textContent = mermaid || "(no mermaid)";
  }

  // Wire selector — runs once, after DOM ready.
  function wireGraphSelector() {
    const sel = document.getElementById("graph-wp-select");
    if (!sel) return;
    sel.addEventListener("change", (e) => {
      const wp = e.target.value;
      if (!wp) return;
      loadGraph(wp);
    });
  }
  wireGraphSelector();

  async function fetchEvents(limit = 10) {
    const r = await fetch("/api/events?limit=" + limit, { cache: "no-store" });
    if (!r.ok) return [];
    return r.json();
  }

  function renderEvents(events) {
    const panel = document.getElementById("events");
    if (!panel) return;
    panel.innerHTML = "";
    if (!events || events.length === 0) {
      panel.appendChild(el("p", { cls: "muted", text: "No events yet." }));
      return;
    }
    for (const ev of events.slice().reverse()) {
      const card = el("div", { cls: "event-row" });
      const ts = (ev.ts || "").slice(11, 19);
      card.appendChild(el("span", { cls: "event-ts", text: ts }));
      card.appendChild(el("span", { cls: "event-actor", text: ev.actor || "?" }));
      card.appendChild(el("span", { cls: "event-name", text: ev.event || "?" }));
      if (ev.wp) card.appendChild(el("span", { cls: "event-wp", text: ev.wp }));
      panel.appendChild(card);
    }
  }

  async function fetchWpDetails(wpId) {
    const r = await fetch("/api/wp/" + encodeURIComponent(wpId), { cache: "no-store" });
    if (!r.ok) throw new Error("wp fetch failed: " + r.status);
    return r.json();
  }

  function renderTopbar(state) {
    const project = state.project || {};
    $("#project-name").textContent = project.name || "TCAD Studio";
    $("#project-desc").textContent =
      project.description || "No description in blueprint.";
    $("#conductor-state").textContent = (state.status && state.status.state) || "—";
    $("#active-wp").textContent =
      (state.status && state.status.active_wp) || "none";
    $("#open-q").textContent = String((state.open_questions || []).length);
    $("#last-refresh").textContent = fmtTimestamp(state.timestamp);
  }

  function renderBuilding(state) {
    const building = $("#building");
    building.innerHTML = "";
    const floors = state.floors || [];
    if (floors.length === 0) {
      building.appendChild(
        el("p", {
          cls: "muted",
          text: "No floors declared in blueprint. Create .protocol/blueprint/blueprint.yaml.",
        })
      );
      return;
    }
    for (const floor of floors) {
      const floorNode = el("div", { cls: "floor" });
      const head = el("div", { cls: "floor-head" });
      head.appendChild(el("span", { text: floor.label || floor.id }));
      const totalRooms = (floor.rooms || []).length;
      const finished = (floor.rooms || []).filter(
        (r) => r.status === "finished"
      ).length;
      head.appendChild(
        el("span", { text: `${finished}/${totalRooms} finished` })
      );
      floorNode.appendChild(head);

      const body = el("div", { cls: "floor-body" });
      for (const room of floor.rooms || []) {
        body.appendChild(renderRoom(room));
      }
      floorNode.appendChild(body);
      building.appendChild(floorNode);
    }
  }

  function renderRoom(room) {
    const status = room.status || "planned";
    const node = el("div", {
      cls: `room status-${status}` + (room.id === lastSelectedRoomId ? " selected" : ""),
      attrs: { "data-room-id": room.id },
    });
    node.appendChild(el("div", { cls: "room-label", text: room.label || room.id }));
    node.appendChild(el("div", { cls: "room-id", text: room.id }));

    const meta = el("div", { cls: "room-meta" });
    meta.appendChild(el("span", { text: `${room.file_count ?? 0} files` }));
    meta.appendChild(el("span", { text: `${room.loc ?? 0} loc` }));
    if (room.built_by_wps && room.built_by_wps.length) {
      meta.appendChild(el("span", { text: `${room.built_by_wps.length} wp` }));
    }
    node.appendChild(meta);

    const progress = el("div", { cls: "progress" });
    progress.style.width = `${Math.round((room.progress || 0) * 100)}%`;
    node.appendChild(progress);

    node.addEventListener("click", () => selectRoom(room));
    return node;
  }

  function selectRoom(room) {
    lastSelectedRoomId = room.id;
    document.querySelectorAll(".room.selected").forEach((r) =>
      r.classList.remove("selected")
    );
    const target = document.querySelector(`.room[data-room-id="${room.id}"]`);
    if (target) target.classList.add("selected");

    $("#detail-empty").hidden = true;
    $("#detail").hidden = false;
    $("#detail-title").textContent = room.label || room.id;
    $("#detail-desc").textContent = room.description || "";
    $("#detail-status").textContent = room.status || "planned";
    $("#detail-progress").textContent =
      `${Math.round((room.progress || 0) * 100)}% — ${room.file_count ?? 0} files, ${room.loc ?? 0} loc`;
    setListContent("#detail-files", [`${room.file_count ?? 0} files match the allowed_paths`]);
    setListContent("#detail-loc", [`${room.loc ?? 0} lines of code (rough count)`]);
    setListContent("#detail-paths", room.allowed_paths || []);
    setListContent("#detail-furniture", room.expected_furniture || []);
    setListContent("#detail-deps", room.depends_on || []);
    setListContent("#detail-wps", room.built_by_wps || []);
  }

  function setListContent(sel, items) {
    const dd = document.querySelector(sel);
    dd.innerHTML = "";
    if (!items || items.length === 0) {
      dd.appendChild(el("span", { cls: "muted", text: "—" }));
      return;
    }
    if (items.length === 1 && typeof items[0] === "string" && !items[0].includes("/")) {
      dd.appendChild(el("span", { text: items[0] }));
      return;
    }
    const ul = el("ul");
    for (const item of items) {
      const li = el("li");
      li.appendChild(el("code", { cls: "path", text: String(item) }));
      ul.appendChild(li);
    }
    dd.appendChild(ul);
  }

  function renderTimeline(state) {
    const tl = $("#timeline");
    tl.innerHTML = "";
    const wps = state.wps || [];
    if (wps.length === 0) {
      tl.appendChild(
        el("p", {
          cls: "muted",
          text: "No Work Packages yet. Generate one with: python scripts/tcad_handoff.py",
        })
      );
      return;
    }
    for (const wp of wps) {
      const card = el("div", {
        cls: `wp-card status-${wp.status}`,
        attrs: { "data-wp-id": wp.id },
      });
      card.appendChild(el("div", { cls: "wp-id", text: wp.id }));
      if (wp.goal)
        card.appendChild(el("div", { cls: "wp-goal", text: wp.goal }));
      const meta = el("div", { cls: "wp-meta" });
      meta.appendChild(el("span", { text: wp.status }));
      if (wp.target_room) meta.appendChild(el("span", { text: "→ " + wp.target_room }));
      if (wp.verdict) meta.appendChild(el("span", { text: "verdict: " + wp.verdict }));
      if (wp.created) meta.appendChild(el("span", { text: wp.created }));
      card.appendChild(meta);
      card.addEventListener("click", () => showWpDetail(wp.id));
      tl.appendChild(card);
    }
  }

  function renderConstructionPlan(state) {
    const node = $("#construction-plan");
    node.innerHTML = "";
    const plan = state.construction_plan || [];
    for (const phase of plan) {
      const div = el("div", { cls: "plan-phase" });
      div.appendChild(el("strong", { text: phase.phase || "phase" }));
      div.appendChild(
        el("span", { text: (phase.rooms || []).join(", ") || "(no rooms)" })
      );
      node.appendChild(div);
    }
  }

  async function showWpDetail(wpId) {
    const panel = $("#wp-detail-panel");
    const body = $("#wp-detail-body");
    panel.hidden = false;
    $("#wp-detail-title").textContent = wpId;
    body.innerHTML = "";
    body.appendChild(el("p", { cls: "muted", text: "Loading…" }));
    try {
      const detail = await fetchWpDetails(wpId);
      body.innerHTML = "";

      const fileList = el("div", { cls: "wp-file-list" });
      for (const name of Object.keys(detail.files || {})) {
        const chip = el("span", { text: name });
        chip.style.cursor = "pointer";
        chip.addEventListener("click", () => {
          const content = detail.files[name] || "";
          showFileContent(name, content);
        });
        fileList.appendChild(chip);
      }
      body.appendChild(fileList);

      // Show 01_goal by default
      const def = detail.files && detail.files["01_goal.md"];
      if (def) showFileContent("01_goal.md", def);
    } catch (err) {
      body.innerHTML = "";
      body.appendChild(el("p", { cls: "muted", text: "Error: " + err.message }));
    }
  }

  function showFileContent(name, content) {
    const body = $("#wp-detail-body");
    let pre = body.querySelector(".wp-file-content");
    if (!pre) {
      pre = el("pre", { cls: "wp-file-content" });
      body.appendChild(pre);
    }
    pre.textContent = `# ${name}\n\n${content}`;
  }

  $("#wp-detail-close").addEventListener("click", () => {
    $("#wp-detail-panel").hidden = true;
  });

  $("#refresh-btn").addEventListener("click", () => refresh(true));

  async function refresh(manual = false) {
    try {
      const state = await fetchState();
      renderTopbar(state);
      renderBuilding(state);
      renderTimeline(state);
      renderConstructionPlan(state);
      const events = await fetchEvents(10);
      renderEvents(events);
      // Phase 3: graph panel refresh
      try { await refreshGraphPanel(); } catch (e) { console.warn("graph panel", e); }
      // Phase 3.3: atlas panel refresh
      try { renderAtlas(await fetchAtlas()); } catch (e) { console.warn("atlas panel", e); }
      if (lastSelectedRoomId) {
        const room = findRoom(state, lastSelectedRoomId);
        if (room) selectRoom(room);
      }
      if (manual) flashRefresh();
    } catch (err) {
      console.error(err);
      $("#last-refresh").textContent = "error";
    }
  }

  function findRoom(state, id) {
    for (const floor of state.floors || []) {
      for (const room of floor.rooms || []) {
        if (room.id === id) return room;
      }
    }
    return null;
  }

  function flashRefresh() {
    const btn = $("#refresh-btn");
    btn.style.borderColor = "var(--accent)";
    setTimeout(() => (btn.style.borderColor = ""), 200);
  }

  refresh();
  setInterval(refresh, REFRESH_MS);
})();
