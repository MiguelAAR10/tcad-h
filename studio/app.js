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
