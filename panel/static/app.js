const state = {
  configs: [],
  groups: [],
  tabs: new Map(),
  activeTab: null,
  activeView: "home",
  commandHistory: [],
  historyIndex: -1,
  ws: null,
  eventWs: null,
  telemetry: null,
  editor: null,
  applyingEditor: false,
  autoscroll: true,
  health: null,
  players: [],
  founders: [],
  launch: null,
  slots: null,
  schedulerTasks: [],
  serverLogContent: "",
  maxPlayers: 32,
  panelStartedAt: Date.now(),
  saving: false,
  logAutoRefresh: true,
  cityWipeId: null,
  logKind: "console",
  wipePreview: null,
  worldNotify: { local: null, remote: null },
  servers: [],
  serversActive: null,
  serversPresets: {},
  wizardCaps: { rcon: null, files: null, query: null, process: false },
  editingServerId: null,
  smokePoll: null,
  token: localStorage.getItem("pz_panel_token") || null,
  user: null,
  authDisabled: false,
  authMode: "login",
  appBootstrapped: false,
  localBypass: false,
};

const $ = (sel) => document.querySelector(sel);
const consoleEl = $("#console");
const consoleInput = $("#console-input");
const toast = $("#toast");

const MODE_MAP = {
  lua: "lua",
  ini: "properties",
  shell: "shell",
  json: "application/json",
  plaintext: null,
};

const PRESET_COMMANDS = {
  save: "save",
  announce: 'servermsg "Сообщение"',
  restart: "quit",
  mods: "checkModsNeedUpdate",
  custom: "",
};

const HISTORY_LIMIT = 100;

function showToast(message, type = "ok") {
  toast.textContent = message;
  toast.className = `toast ${type}`;
  toast.classList.remove("hidden");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => toast.classList.add("hidden"), 4500);
}

function classifyConsoleLine(text) {
  const upper = text.toUpperCase();
  if (/\[ERROR\]|ERROR:|EXCEPTION|FAILED/.test(upper)) return "err";
  if (/\[WARN\]|WARN:|WARNING/.test(upper)) return "warn";
  if (/\[LUA\]|LUA\s/.test(upper)) return "lua";
  if (/\[STEAM\]|STEAM/.test(upper)) return "steam";
  if (/\[INFO\]|INFO:|LOG:/.test(upper)) return "info";
  return "out";
}

function appendConsole(text, cls) {
  const lines = String(text).split(/\r?\n/);
  for (const part of lines) {
    if (part === "" && lines.length === 1) continue;
    const line = document.createElement("div");
    line.className = `line ${cls || classifyConsoleLine(part)}`;
    line.textContent = part;
    consoleEl.appendChild(line);
  }
  if (state.autoscroll) consoleEl.scrollTop = consoleEl.scrollHeight;
}

function clearConsole() {
  consoleEl.innerHTML = "";
}

function downloadLog() {
  const text = Array.from(consoleEl.querySelectorAll(".line")).map((el) => el.textContent).join("\n");
  downloadText(text || "(empty)", `rcon-log_${ts()}.txt`);
}

function downloadText(text, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

function ts() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function t(key, vars) {
  return (window.I18n && window.I18n.t(key, vars)) || key;
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(path, {
    headers,
    credentials: "same-origin",
    ...options,
  });
  let data = {};
  try { data = await res.json(); } catch { data = {}; }
  if (res.status === 401 && !String(path).startsWith("/api/auth/")) {
    state.token = null;
    localStorage.removeItem("pz_panel_token");
    showAuthModal(state.authMode === "setup" ? "setup" : "login");
    const err = new Error(t("toast.unauthorized"));
    err.status = 401;
    throw err;
  }
  if (res.status === 403) {
    showToast(t("rbac.denied") || "Insufficient permissions", "err");
  }
  if (!res.ok) {
    const detail = data.detail;
    const msg = typeof detail === "string"
      ? detail
      : (detail && detail.message) || JSON.stringify(detail) || res.statusText;
    const err = new Error(`[${res.status}] ${msg}`);
    err.detail = detail;
    throw err;
  }
  return data;
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* —— Auth (Sprint 3) —— */
function showAuthModal(mode) {
  state.authMode = mode || "login";
  const modal = $("#auth-modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  document.body.classList.add("auth-locked");
  const setup = mode === "setup";
  const localOnly = mode === "local" || (state.authDisabled && state.localBypass);
  document.querySelectorAll(".auth-setup-only").forEach((el) => el.classList.toggle("hidden", !setup));
  const formFields = $("#auth-form")?.querySelectorAll("label.field:not(.auth-setup-only)");
  formFields?.forEach((el) => el.classList.toggle("hidden", localOnly));
  const credWrap = $("#auth-credentials-wrap");
  const localWrap = $("#auth-local-wrap");
  if (credWrap) credWrap.classList.toggle("hidden", localOnly);
  if (localWrap) {
    localWrap.classList.toggle("hidden", !state.localBypass && !localOnly);
    localWrap.classList.toggle("auth-local-prominent", localOnly);
  }
  const titleKey = localOnly ? "auth.local_title" : (setup ? "auth.setup" : "auth.login");
  const hintKey = localOnly ? "auth.local_hint" : (setup ? "auth.setup_hint" : "auth.login_hint");
  const title = $("#auth-modal-title");
  const hint = $("#auth-modal-hint");
  const submit = $("#auth-submit");
  if (title) title.textContent = t(titleKey);
  if (hint) hint.textContent = t(hintKey);
  if (submit) submit.textContent = t(setup ? "auth.setup" : "auth.login");
  const err = $("#auth-error");
  if (err) { err.classList.add("hidden"); err.textContent = ""; }
}

function hideAuthModal() {
  $("#auth-modal")?.classList.add("hidden");
  document.body.classList.remove("auth-locked");
}

function renderUserBadge() {
  const badge = $("#user-badge");
  const logout = $("#btn-logout");
  if (!badge || !logout) return;
  if (!state.user?.username) {
    badge.classList.add("hidden");
    logout.classList.add("hidden");
    return;
  }
  badge.textContent = state.user.role === "moderator"
    ? `${state.user.username} [Mod]`
    : `${state.user.username} [Admin]`;
  badge.title = state.user.local
    ? t("auth.local_badge")
    : `${state.user.username} · ${state.user.role || "admin"}`;
  badge.classList.toggle("user-local", !!state.user.local);
  badge.classList.toggle("user-mod", state.user.role === "moderator");
  badge.classList.toggle("user-admin", state.user.role !== "moderator");
  badge.classList.remove("hidden");
  logout.classList.remove("hidden");
  applyRolePermissions();
}

function isAdmin() {
  return !state.user || state.user.role !== "moderator";
}

function applyRolePermissions() {
  const mod = state.user?.role === "moderator";
  document.body.classList.toggle("role-moderator", !!mod);
  document.body.classList.toggle("role-admin", !mod);
  [
    "#btn-save",
    "#ws-compile-form button[type='submit']",
    "#btn-ws-analyze",
    "#btn-ws-steamcmd-install",
    "#btn-ws-download",
    "#btn-mirror-pull",
    "#btn-mirror-verify",
    "#btn-city-wipe-run",
    "#btn-wipe-apply",
    "#btn-wipe-preview",
    "#server-wizard-form",
    "#btn-home-save",
  ].forEach((sel) => {
    document.querySelectorAll(sel).forEach((el) => {
      if (mod) {
        el.disabled = true;
        el.classList.add("rbac-disabled");
        el.title = t("rbac.denied") || "Insufficient permissions";
      } else {
        el.classList.remove("rbac-disabled");
      }
    });
  });
  ["#ws-deploy-server", "#ws-fail-conflict", "#ws-update-ini"].forEach((id) => {
    const el = document.getElementById(id.replace("#", ""));
    if (el && mod) el.disabled = true;
  });
  const compileDrawer = $("#ws-compile-form");
  if (compileDrawer && mod) compileDrawer.classList.add("rbac-disabled");
}

async function enterLocalAuth() {
  const errEl = $("#auth-error");
  if (state.authDisabled) {
    state.user = { username: "local", role: "admin", local: true };
    hideAuthModal();
    renderUserBadge();
    if (!state.appBootstrapped) bootstrapApp();
    else { connectWs(); connectEventWs(); }
    return;
  }
  try {
    const res = await fetch("/api/auth/local", {
      method: "POST",
      credentials: "same-origin",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errEl.textContent = typeof data.detail === "string" ? data.detail : res.statusText;
      errEl.classList.remove("hidden");
      return;
    }
    state.token = data.token;
    localStorage.setItem("pz_panel_token", data.token);
    state.user = data.user;
    hideAuthModal();
    renderUserBadge();
    if (!state.appBootstrapped) bootstrapApp();
    else { connectWs(); connectEventWs(); }
  } catch (ex) {
    errEl.textContent = ex.message;
    errEl.classList.remove("hidden");
  }
}

async function submitAuthForm(e) {
  e.preventDefault();
  const username = $("#auth-username").value.trim();
  const password = $("#auth-password").value;
  const password2 = $("#auth-password2")?.value || "";
  const errEl = $("#auth-error");
  if (state.authMode === "setup" && password !== password2) {
    errEl.textContent = "Passwords do not match";
    errEl.classList.remove("hidden");
    return;
  }
  const path = state.authMode === "setup" ? "/api/auth/setup" : "/api/auth/login";
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errEl.textContent = typeof data.detail === "string" ? data.detail : res.statusText;
      errEl.classList.remove("hidden");
      return;
    }
    state.token = data.token;
    localStorage.setItem("pz_panel_token", data.token);
    state.user = data.user;
    hideAuthModal();
    renderUserBadge();
    if (!state.appBootstrapped) bootstrapApp();
    else { connectWs(); connectEventWs(); }
  } catch (ex) {
    errEl.textContent = ex.message;
    errEl.classList.remove("hidden");
  }
}

async function logoutUser() {
  try { await api("/api/auth/logout", { method: "POST", body: "{}" }); } catch { /* ignore */ }
  state.token = null;
  state.user = null;
  localStorage.removeItem("pz_panel_token");
  if (state.ws) { try { state.ws.close(); } catch { /* ignore */ } state.ws = null; }
  if (state.eventWs) { try { state.eventWs.close(); } catch { /* ignore */ } state.eventWs = null; }
  state.appBootstrapped = false;
  renderUserBadge();
  showAuthModal(state.authDisabled && state.localBypass ? "local" : "login");
  showToast(t("toast.logged_out"));
}

async function initAuth() {
  try {
    const status = await fetch("/api/auth/status").then((r) => r.json());
    state.authDisabled = !!status.auth_disabled;
    state.localBypass = !!status.local_bypass;
    if (state.authDisabled && state.localBypass) {
      showAuthModal("local");
      return;
    }
    if (status.needs_setup) {
      showAuthModal("setup");
      return;
    }
    if (!state.token) {
      showAuthModal("login");
      return;
    }
    state.user = await api("/api/auth/me");
    hideAuthModal();
    renderUserBadge();
    bootstrapApp();
  } catch {
    showAuthModal(state.localBypass ? "local" : "login");
  }
}

function bootstrapApp() {
  if (state.appBootstrapped) return;
  state.appBootstrapped = true;
  loadPrefs();
  loadSlots();
  loadHealth();
  loadServers();
  checkOnboarding();
  loadConfigs().catch((e) => showToast(e.message, "err"));
  applyStatusPayload(null);
  tickUptime();
  connectWs();
  connectEventWs();
  api("/api/telemetry/stats").then(renderTelemetryBar).catch(() => {});
  api("/api/status").then(applyStatusPayload).catch(() => {});
}

function telemetryClass(percent) {
  const p = Number(percent) || 0;
  if (p >= 90) return "tel-critical";
  if (p >= 70) return "tel-warn";
  return "tel-ok";
}

function renderTelemetryBar(data) {
  if (!data) return;
  state.telemetry = data;
  const host = data.host || {};
  const cpuEl = $("#tel-cpu");
  const ramEl = $("#tel-ram");
  const gsEl = $("#tel-gameserver");
  if (cpuEl) {
    cpuEl.textContent = `CPU: ${host.cpu_percent ?? "—"}%`;
    cpuEl.className = `telemetry-badge ${telemetryClass(host.cpu_percent)}`;
  }
  if (ramEl) {
    const used = host.ram_used_gb ?? (host.ram_used_mb ? (host.ram_used_mb / 1024).toFixed(1) : "—");
    const total = host.ram_total_gb ?? (host.ram_total_mb ? (host.ram_total_mb / 1024).toFixed(1) : "—");
    ramEl.textContent = `RAM: ${used} / ${total} GB`;
    ramEl.className = `telemetry-badge ${telemetryClass(host.ram_percent)}`;
  }
  if (gsEl) {
    const gs = data.gameserver;
    if (gs && gs.running) {
      gsEl.textContent = `JVM: ${gs.rss_mb ?? "—"} MB · ${gs.cpu_percent ?? 0}%`;
      gsEl.className = `telemetry-badge ${telemetryClass(gs.cpu_percent)}`;
      gsEl.classList.remove("hidden");
    } else {
      gsEl.classList.add("hidden");
    }
  }
}

function applyStatusPayload(status) {
  if (!status) return;
  updateStatusPill(status.rcon_online, status.error);
  updatePlayersPill(status.players ? realPlayers(status.players).length : (status.players_online || 0));
  if (status.players) {
    state.players = realPlayers(status.players);
    if (state.activeView === "players") renderPlayersPage();
  }
  if (status.founders) {
    state.founders = status.founders;
    if (state.activeView === "players") renderFounders();
  }
  if (status.npcs) {
    state.slots = { ...(state.slots || {}), npcs: status.npcs, count: status.dummy_slots };
    if (state.activeView === "npc") renderTrainersRoster();
  }
  if (state.activeView === "home") loadHome();
  if (state.activeView === "mirror") loadMirror();
}

function eventWsConnected() {
  return state.eventWs && state.eventWs.readyState === WebSocket.OPEN;
}

function handleEventMessage(msg) {
  const channel = msg.channel;
  const data = msg.data;
  if (channel === "telemetry") {
    renderTelemetryBar(data);
    return;
  }
  if (channel === "status") {
    applyStatusPayload(data);
    return;
  }
  if (channel === "console_tail" && state.logAutoRefresh && state.activeView === "logs") {
    const kind = $("#log-kind")?.value || state.logKind || "console";
    if (kind !== "audit") {
      const pre = $("#server-log");
      if (pre && data.content !== undefined) {
        state.serverLogContent = data.content || "";
        pre.textContent = state.serverLogContent || "(пусто — файла ещё нет на зеркале)";
        pre.scrollTop = pre.scrollHeight;
        if ($("#log-meta") && data.filename) {
          $("#log-meta").textContent = `${data.filename} · ${data.source || ""} · ${data.total_lines} строк`;
        }
      }
    }
    return;
  }
  if (channel === "pull_progress") {
    if (state.activeView === "mirror") loadMirror();
    return;
  }
  if (channel === "steamcmd_progress") {
    renderSteamcmdBanner({ installed: false, install: data });
    if (!data.running) {
      if (data.phase === "done") {
        loadWorkshop();
        showToast(t("workshop.steamcmd_done") || "SteamCMD installed", "ok");
      }
      if (data.phase === "error") showToast(data.message || "SteamCMD install failed", "err");
    }
    return;
  }
  if (channel === "workshop_progress") {
    setWorkshopDownloadStatus(
      `${data.phase || "…"} · ${data.percent || 0}% · ${data.message || ""}`,
      data.phase === "error" ? false : undefined,
    );
    if (!data.running) {
      if (data.phase === "done") {
        loadWorkshop();
        showToast(t("workshop.download_done") || "Workshop download complete", "ok");
      }
      if (data.phase === "error") showToast(data.message || "download error", "err");
    }
    return;
  }
  if (channel === "compile_progress") {
    const log = $("#ws-compile-log");
    if (log && data.message) log.textContent = (log.textContent ? log.textContent + "\n" : "") + data.message;
  }
}

function connectEventWs() {
  if (!state.authDisabled && !state.token) return;
  if (state.eventWs) {
    try { state.eventWs.close(); } catch { /* ignore */ }
  }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const q = state.token ? `?token=${encodeURIComponent(state.token)}` : "";
  state.eventWs = new WebSocket(`${proto}://${location.host}/ws/events${q}`);
  state.eventWs.onclose = (ev) => {
    if (ev.code === 4401) return;
    setTimeout(connectEventWs, 4000);
  };
  state.eventWs.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "pong") return;
      handleEventMessage(msg);
    } catch { /* ignore */ }
  };
}

async function initI18n() {
  const lang = localStorage.getItem("pz_lang") || "ru";
  await I18n.loadLocale(lang);
  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.onclick = async () => {
      await I18n.loadLocale(btn.dataset.lang);
      renderUserBadge();
    };
  });
}

/* —— Navigation —— */
function capHints() {
  return {
    rcon: t("cap.rcon"),
    files: t("cap.files"),
    query: t("cap.query"),
    process: t("cap.process"),
    meatballs: t("cap.meatballs"),
  };
}

function activeCapabilities() {
  const active = (state.servers || []).find((s) => s.id === state.serversActive);
  return (state.health && state.health.capabilities)
    || (active && active.capabilities)
    || {};
}

function activePlugins() {
  const active = (state.servers || []).find((s) => s.id === state.serversActive);
  if (state.health && state.health.plugins) return state.health.plugins;
  if (active && active.plugins) return active.plugins;
  return null;
}

function viewGate(view) {
  if (!state.health && !(state.servers || []).length) return { ok: true, need: null, hint: "" };
  const views = (state.health && state.health.views) || (state.servers || []).find((s) => s.id === state.serversActive)?.views;
  if (views && views[view]) return views[view];
  const btn = document.querySelector(`.nav-item[data-view="${view}"]`);
  const plugin = btn?.dataset.needPlugin;
  const plugins = activePlugins();
  if (plugin && plugins && !plugins[plugin]) {
    return { ok: false, need: plugin, hint: capHints()[plugin] || plugin };
  }
  const need = btn?.dataset.need;
  if (!need) return { ok: true, need: null, hint: "" };
  return { ok: !!activeCapabilities()[need], need, hint: capHints()[need] || need };
}

function applyCapabilities() {
  const active = (state.servers || []).find((s) => s.id === state.serversActive);
  const caps = (state.health && state.health.capabilities) || (active && active.capabilities);
  if (!caps) return;
  const plugins = activePlugins();
  document.querySelectorAll("[data-need]").forEach((el) => {
    const need = el.dataset.need;
    const ok = !!caps[need];
    el.classList.toggle("is-disabled", !ok);
    if (el.tagName === "BUTTON") el.disabled = !ok;
    el.title = ok ? "" : (capHints()[need] || need);
  });
  if (plugins) {
    document.querySelectorAll("[data-need-plugin]").forEach((el) => {
      const key = el.dataset.needPlugin;
      const ok = !!plugins[key];
      el.classList.toggle("is-disabled", !ok);
      el.classList.toggle("hidden", !ok);
      if (el.tagName === "BUTTON") el.disabled = !ok;
      el.title = ok ? "" : (capHints()[key] || key);
    });
  }
  const start = $("#btn-home-local-start");
  const stop = $("#btn-home-local-stop");
  const localBtns = [$("#btn-local-start"), $("#btn-local-stop")];
  [start, stop, ...localBtns].forEach((btn) => {
    if (!btn) return;
    btn.disabled = !caps.process;
    btn.title = caps.process ? "" : capHints().process;
    btn.classList.toggle("is-disabled", !caps.process);
  });
  ["btn-home-save", "btn-home-graceful", "btn-home-hard"].forEach((id) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.disabled = !caps.rcon;
    btn.title = caps.rcon ? "" : capHints().rcon;
  });
  const note = $("#home-host-note");
  if (note) {
    note.textContent = caps.process
      ? "Local Start запускает JVM на этой машине."
      : "Запустить хост панель не может — после quit открой панель хостера.";
  }
  const hint = $("#home-hint");
  if (hint) {
    const active = (state.servers || []).find((s) => s.id === state.serversActive);
    const name = (active && active.name) || (state.health && state.health.server_name) || "сервер";
    hint.textContent = `${name} · rcon=${caps.rcon ? "да" : "нет"} · files=${caps.files ? "да" : "нет"} · process=${caps.process ? "local" : "none"}`;
  }
}

function renderCapStrip(caps, notes) {
  const el = $("#cap-strip");
  if (!el) return;
  const keys = ["rcon", "files", "query", "process"];
  el.innerHTML = keys.map((key) => {
    const on = !!caps[key];
    const hints = capHints();
    const tip = (notes && notes[key]) || (on ? "ok" : hints[key]);
    return `<span class="cap-chip ${on ? "ok" : "off"}" title="${escapeHtml(tip)}">${key}</span>`;
  }).join("");
}

function switchView(view) {
  const gate = viewGate(view);
  if (view !== "home" && gate && gate.ok === false) {
    showToast(gate.hint || "канал недоступен", "err");
    return;
  }
  state.activeView = view;
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((el) => {
    el.classList.toggle("view-active", el.id === `view-${view}`);
  });
  if (view === "files" && state.editor) {
    setTimeout(() => state.editor.refresh(), 50);
  }
  if (view === "home") loadHome();
  if (view === "scheduler") loadScheduler();
  if (view === "logs") loadServerLog();
  if (view === "network") loadNetwork();
  if (view === "players") {
    loadPlayers();
    loadLaunch();
  }
  if (view === "npc") loadSlots();
  if (view === "mods") loadMods();
  if (view === "workshop") loadWorkshop();
  if (view === "mirror") {
    loadMirror();
    loadCityWipeCities();
  }
  if (view === "smoke") loadSmoke();
  if (view === "chat") loadChat();
  if (view === "bans") loadBans();
  if (view === "privates") loadPrivates();
  if (view === "home" || view === "files") {
    setBottomNavActive(view === "files" ? "files" : "home");
  }
  location.hash = view;
}

function initNavigation() {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.onclick = () => switchView(btn.dataset.view);
  });
  document.querySelectorAll(".bottom-nav-item[data-bottom-view]").forEach((btn) => {
    btn.onclick = () => switchView(btn.dataset.bottomView);
  });
  const hash = (location.hash || "#home").replace("#", "");
  if (document.getElementById(`view-${hash}`)) switchView(hash);
  else switchView("home");
}

/* —— Editor —— */
function initEditor() {
  state.editor = CodeMirror(document.getElementById("codemirror-host"), {
    value: "",
    theme: "material-darker",
    lineNumbers: true,
    lineWrapping: false,
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    gutters: ["CodeMirror-linenumbers"],
    extraKeys: {
      "Ctrl-S": () => { saveActiveTab(); return false; },
      "Cmd-S": () => { saveActiveTab(); return false; },
    },
  });
  state.editor.on("change", () => {
    if (state.applyingEditor || !state.activeTab) return;
    const tab = state.tabs.get(state.activeTab);
    if (!tab) return;
    tab.content = state.editor.getValue();
    tab.dirty = tab.content !== tab.original;
    renderTabs();
    $("#btn-save").disabled = false;
  });
  state.editor.setSize("100%", "100%");
}

function setEditorMode(language) {
  state.editor.setOption("mode", MODE_MAP[language] || null);
  $("#editor-lang").textContent = language || "";
}

function formatUptime(ms) {
  const s = Math.floor(ms / 1000);
  const h = String(Math.floor(s / 3600)).padStart(2, "0");
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const sec = String(s % 60).padStart(2, "0");
  return `${h}:${m}:${sec}`;
}

function updateHeaderFromHealth() {
  const h = state.health;
  if (!h) return;
  const ep = h.header || {};
  $("#pill-ip").textContent = ep.server_ip || h.rcon_host || "—";
  $("#pill-query").textContent = String(ep.query_port || h.query_port || "—");
  $("#pill-rcon").textContent = String(ep.rcon_port || h.rcon_port || "—");
  state.maxPlayers = ep.max_players || h.max_players || 32;
}

function updateStatusPill(online, error) {
  const pill = $("#status-pill");
  const text = $("#status-pill-text");
  if (online) {
    pill.className = "status-pill online";
    text.textContent = "ONLINE";
    pill.title = "RCON reachable";
  } else {
    pill.className = "status-pill offline";
    text.textContent = "OFFLINE";
    pill.title = error || "RCON unreachable";
  }
  updateStatusRing(online, error);
}

function updateStatusRing(online, error) {
  const ring = $("#status-ring");
  const label = $("#ring-label");
  const sub = $("#ring-sub");
  if (!ring || !label) return;
  const caps = activeCapabilities();
  const hasServer = !!(state.serversActive || (state.servers || []).length);
  if (online) {
    ring.className = "amnezia-status-ring online";
    label.textContent = "ONLINE";
    if (sub) sub.textContent = "RCON · Game";
  } else if (hasServer && caps.files) {
    ring.className = "amnezia-status-ring degraded";
    label.textContent = "PARTIAL";
    if (sub) sub.textContent = error ? String(error).slice(0, 40) : "Files ok · RCON down";
  } else {
    ring.className = "amnezia-status-ring offline";
    label.textContent = hasServer ? "OFFLINE" : "NO SERVER";
    if (sub) sub.textContent = hasServer ? (error || "RCON") : "Add VPS";
  }
  const meta = $("#dashboard-meta");
  if (meta) {
    const active = (state.servers || []).find((s) => s.id === state.serversActive);
    meta.textContent = active
      ? `${active.name} · ${(active.files && active.files.kind) || "?"} · ${online ? "online" : "offline"}`
      : "Подключите VPS через SSH";
  }
}

const TRAINER_NAMES = new Set(["Rook", "Otto", "Sarge", "Ash", "Vera"]);

function isTrainerName(name) {
  const roster = (state.slots && (state.slots.roster || state.slots.npcs)) || [];
  if (roster.some((n) => n.name === name)) return true;
  return TRAINER_NAMES.has(name);
}

function realPlayers(list) {
  return (list || []).filter((p) => !isTrainerName(p.name));
}

function updatePlayersPill(count) {
  const real = Number(count) || 0;
  const pill = $("#pill-players");
  if (!pill) return;
  pill.textContent = `${real}/${state.maxPlayers}`;
  pill.title = `Живые игроки ${real} · тренеры во вкладке NPC`;
}

function tickUptime() {
  $("#pill-uptime").textContent = formatUptime(Date.now() - state.panelStartedAt);
}

function maybeNotifyWorld(kind, world) {
  const ready = !!(world && world.ready);
  const prev = state.worldNotify[kind];
  if (ready && prev === false) {
    showToast(kind === "local" ? "Локальный дедик запущен" : "Хост: мир запущен");
  }
  if (world && world.failed && prev === false) {
    const first = (world.errors && world.errors[0]) || world.label || "ошибка старта";
    showToast(`${kind === "local" ? "Локальный дедик" : "Хост"}: ${first}`, "err");
    state.worldNotify[kind] = "failed";
    return;
  }
  state.worldNotify[kind] = ready;
}

async function pollStatus() {
  try {
    const status = await api("/api/status");
    updateStatusPill(status.rcon_online, status.error);
    updatePlayersPill(status.players ? realPlayers(status.players).length : (status.players_online || 0));
    if (status.players) {
      state.players = realPlayers(status.players);
      if (state.activeView === "players") renderPlayersPage();
    }
    if (status.founders) {
      state.founders = status.founders;
      if (state.activeView === "players") renderFounders();
    }
    if (status.npcs) {
      state.slots = { ...(state.slots || {}), npcs: status.npcs, count: status.dummy_slots };
      if (state.activeView === "npc") renderTrainersRoster();
    }
    if (state.activeView === "home") loadHome();
    if (state.activeView === "mirror") loadMirror();
    else {
      api("/api/world/status").then((world) => {
        maybeNotifyWorld("remote", world.remote);
        maybeNotifyWorld("local", (world.local_process && world.local_process.world) || world.local);
      }).catch(() => {});
    }
  } catch {
    updateStatusPill(false, "Status poll failed");
  }
}

async function loadHealth() {
  try {
    state.health = await api("/api/health");
    updateHeaderFromHealth();
    applyCapabilities();
    updateStatusRing(false);
    if (!state.health.rcon_configured) showToast("RCON password не задан в профиле", "err");
  } catch {
    updateStatusPill(false, "Backend offline");
  }
}

/* —— Server profiles —— */
function renderServerSwitcher() {
  const sel = $("#server-switcher");
  if (!sel) return;
  const rows = state.servers || [];
  sel.innerHTML = rows.length
    ? rows.map((s) => `<option value="${escapeHtml(s.id)}"${s.id === state.serversActive ? " selected" : ""}>${escapeHtml(s.name || s.id)}</option>`).join("")
    : '<option value="">нет профилей</option>';
  const hint = $("#home-hint");
  if (hint) {
    const active = rows.find((s) => s.id === state.serversActive);
    hint.textContent = active
      ? `${active.name} · ${active.hoster || "?"} · files=${(active.files && active.files.kind) || "?"} · process=${(active.process && active.process.kind) || "none"}`
      : "профиль сервера · хостер — адаптер";
  }
  const mobileName = $("#mobile-server-name");
  if (mobileName) {
    const active = rows.find((s) => s.id === state.serversActive);
    mobileName.textContent = active ? (active.name || active.id) : "Нет сервера";
  }
  renderServerPickerPopover();
}

function renderServerPickerPopover() {
  const pop = $("#server-picker-popover");
  if (!pop) return;
  const rows = state.servers || [];
  if (!rows.length) {
    pop.innerHTML = "";
    pop.classList.add("hidden");
    return;
  }
  pop.innerHTML = rows.map((s) => `
    <button type="button" class="server-picker-item${s.id === state.serversActive ? " active" : ""}" data-server-id="${escapeHtml(s.id)}">
      ${escapeHtml(s.name || s.id)}
    </button>`).join("");
  pop.querySelectorAll(".server-picker-item").forEach((btn) => {
    btn.onclick = () => {
      switchServer(btn.dataset.serverId);
      pop.classList.add("hidden");
    };
  });
}

function toggleServerPickerPopover() {
  const pop = $("#server-picker-popover");
  if (!pop) return;
  const rows = state.servers || [];
  if (!rows.length) {
    openVpsSetupModal();
    return;
  }
  pop.classList.toggle("hidden");
}

function parseSshEndpoint(raw) {
  const text = String(raw || "").trim();
  if (!text) return { host: "", port: 22 };
  if (text.startsWith("[")) {
    const m = text.match(/^\[([^\]]+)\](?::(\d+))?$/);
    if (m) return { host: m[1], port: Number(m[2]) || 22 };
  }
  const lastColon = text.lastIndexOf(":");
  if (lastColon > 0 && /^\d+$/.test(text.slice(lastColon + 1))) {
    return { host: text.slice(0, lastColon), port: Number(text.slice(lastColon + 1)) || 22 };
  }
  return { host: text, port: 22 };
}

function isSshPrivateKey(text) {
  const t = String(text || "").trim();
  return t.includes("BEGIN") && t.includes("PRIVATE KEY");
}

function detectRemoteRoot(probe) {
  const names = (probe.entries || []).map((n) => String(n));
  if (names.includes("ServerWorld")) return "/ServerWorld";
  const lower = names.map((n) => n.toLowerCase());
  const idx = lower.indexOf("serverworld");
  if (idx >= 0) return `/${names[idx]}`;
  const checks = probe.checks || {};
  if (checks.server_dir || checks.logs_dir) return "/ServerWorld";
  return "/";
}

function openVpsSetupModal() {
  const modal = $("#vps-setup-modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  const err = $("#vps-setup-error");
  if (err) {
    err.textContent = "";
    err.classList.add("hidden");
  }
  $("#vps-host")?.focus();
}

function closeVpsSetupModal() {
  $("#vps-setup-modal")?.classList.add("hidden");
  $("#server-picker-popover")?.classList.add("hidden");
}

async function submitVpsSetup(e) {
  if (e && e.preventDefault) e.preventDefault();
  const errEl = $("#vps-setup-error");
  const btn = $("#vps-setup-submit");
  const hostRaw = $("#vps-host")?.value.trim() || "";
  const user = $("#vps-user")?.value.trim() || "";
  const secret = $("#vps-secret")?.value || "";
  const { host, port } = parseSshEndpoint(hostRaw);
  if (!host || !user || !secret.trim()) {
    if (errEl) {
      errEl.textContent = "Заполните IP, пользователя и пароль/ключ";
      errEl.classList.remove("hidden");
    }
    return;
  }
  const keyMode = isSshPrivateKey(secret);
  const probePayload = {
    kind: "sftp",
    host,
    user,
    port,
    root: "/",
    password: keyMode ? "" : secret,
    sftp_private_key: keyMode ? secret.trim() : "",
  };
  if (btn) btn.disabled = true;
  if (errEl) errEl.classList.add("hidden");
  try {
    const probe = await api("/api/servers/probe/files", {
      method: "POST",
      body: JSON.stringify(probePayload),
    });
    if (!probe.ok) {
      throw new Error(probe.error || "SSH/SFTP недоступен");
    }
    const root = detectRemoteRoot(probe);
    const serverPayload = {
      name: host,
      hoster: "vps",
      game_version: "",
      rcon: { host, port: 16284 },
      files: {
        kind: "sftp",
        host,
        user,
        root,
        ini: "world.ini",
        port,
        sftp_key_path: "",
      },
      plugins: { meatballs: false },
      public: { host, game_port: 16282, query_port: 16281 },
      process: { kind: "none" },
      authority: "panel_wins",
      secrets: {
        rcon_password: "",
        ftp_password: keyMode ? "" : secret,
        sftp_private_key: keyMode ? secret.trim() : "",
      },
      capabilities: {
        rcon: false,
        files: true,
        query: false,
        process: false,
        inferred: false,
        probed_at: new Date().toISOString().slice(0, 19),
        notes: { files: (probe.checks && probe.checks.ok) ? `root=${root}` : "ssh ok" },
      },
    };
    const created = await api("/api/servers", { method: "POST", body: JSON.stringify(serverPayload) });
    await api(`/api/servers/${encodeURIComponent(created.id)}/activate`, { method: "POST", body: "{}" });
    $("#vps-secret").value = "";
    closeVpsSetupModal();
    $("#onboarding-modal")?.classList.add("hidden");
    await loadServers();
    await loadHealth();
    await pollStatus();
    applyCapabilities();
    showToast(`Сервер подключён: ${created.name || host}`);
    switchView("home");
  } catch (exc) {
    if (errEl) {
      errEl.textContent = exc.message || String(exc);
      errEl.classList.remove("hidden");
    }
    showToast(exc.message || "Ошибка подключения", "err");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function setBottomNavActive(view) {
  document.querySelectorAll(".bottom-nav-item[data-bottom-view]").forEach((el) => {
    el.classList.toggle("active", el.dataset.bottomView === view);
  });
}

async function loadServers() {
  try {
    const data = await api("/api/servers");
    state.servers = data.servers || [];
    state.serversActive = data.active || null;
    state.serversPresets = data.presets || {};
    renderServerSwitcher();
    applyCapabilities();
    if (state.activeView && viewGate(state.activeView).ok === false) switchView("home");
  } catch (e) {
    const sel = $("#server-switcher");
    if (sel) sel.innerHTML = `<option value="">${escapeHtml(e.message)}</option>`;
  }
}

async function switchServer(serverId) {
  if (!serverId || serverId === state.serversActive) return;
  try {
    await api(`/api/servers/${encodeURIComponent(serverId)}/activate`, { method: "POST", body: "{}" });
    await loadServers();
    await loadHealth();
    await pollStatus();
    applyCapabilities();
    if (state.activeView && viewGate(state.activeView).ok === false) switchView("home");
    if (state.activeView === "home") loadHome();
    if (activeCapabilities().files) loadConfigs().catch(() => {});
    showToast(`Активен: ${serverId}`);
  } catch (e) {
    showToast(e.message, "err");
    renderServerSwitcher();
  }
}

function applyHosterPreset() {
  const hoster = $("#srv-hoster")?.value || "vps";
  const preset = state.serversPresets[hoster] || {};
  const rcon = preset.rcon || {};
  const files = preset.files || {};
  const pub = preset.public || {};
  const proc = preset.process || {};
  $("#srv-rcon-host").value = rcon.host || "";
  if (rcon.port) $("#srv-rcon-port").value = rcon.port;
  if (files.kind) $("#srv-files-kind").value = files.kind;
  $("#srv-files-root").value = files.root || "";
  if (files.ini && $("#srv-files-ini")) $("#srv-files-ini").value = files.ini;
  $("#srv-ftp-host").value = files.host || "";
  if ($("#srv-sftp-port")) {
    $("#srv-sftp-port").value = files.port || files.sftp_port || 22;
  }
  if ($("#srv-sftp-key-path")) {
    $("#srv-sftp-key-path").value = files.sftp_key_path || "";
  }
  const plugins = preset.plugins || {};
  if ($("#srv-plugin-meatballs")) {
    $("#srv-plugin-meatballs").checked = !!plugins.meatballs;
  }
  state.wizardCaps.process = (proc.kind || $("#srv-process")?.value) === "local";
  renderWizardCaps();
  if (pub.game_port) $("#srv-game-port").value = pub.game_port;
  if (pub.query_port) $("#srv-query-port").value = pub.query_port;
  if (proc.kind) $("#srv-process").value = proc.kind;
  toggleServerFormKind();
}

function toggleServerFormKind() {
  const kind = $("#srv-files-kind")?.value || "ftp";
  document.querySelectorAll(".srv-remote-only").forEach((el) => {
    el.classList.toggle("hidden", kind === "local");
  });
  document.querySelectorAll(".srv-ftp-only").forEach((el) => {
    el.classList.toggle("hidden", kind !== "ftp");
  });
  document.querySelectorAll(".srv-sftp-only").forEach((el) => {
    el.classList.toggle("hidden", kind !== "sftp");
  });
}

function serverFormPayload() {
  const kind = $("#srv-files-kind").value;
  const port = kind === "sftp"
    ? Number($("#srv-sftp-port")?.value) || 22
    : kind === "ftp"
      ? 21
      : undefined;
  return {
    name: $("#srv-name").value.trim(),
    hoster: $("#srv-hoster").value,
    game_version: $("#srv-version").value.trim(),
    rcon: {
      host: $("#srv-rcon-host").value.trim(),
      port: Number($("#srv-rcon-port").value) || 16284,
    },
    files: {
      kind,
      host: $("#srv-ftp-host").value.trim(),
      user: $("#srv-ftp-user").value.trim(),
      root: $("#srv-files-root").value.trim(),
      ini: ($("#srv-files-ini") && $("#srv-files-ini").value.trim()) || "world.ini",
      port,
      sftp_key_path: ($("#srv-sftp-key-path") && $("#srv-sftp-key-path").value.trim()) || "",
    },
    plugins: {
      meatballs: !!($("#srv-plugin-meatballs") && $("#srv-plugin-meatballs").checked),
    },
    public: {
      host: $("#srv-public-host").value.trim(),
      game_port: Number($("#srv-game-port").value) || 16282,
      query_port: Number($("#srv-query-port").value) || 16281,
    },
    process: { kind: $("#srv-process").value },
    authority: $("#srv-hoster").value === "xlgames" ? "host_wins" : "panel_wins",
    secrets: {
      rcon_password: $("#srv-rcon-pass").value,
      ftp_password: $("#srv-ftp-pass").value,
      sftp_private_key: ($("#srv-sftp-key-inline") && $("#srv-sftp-key-inline").value) || "",
    },
    capabilities: wizardCapabilitiesPayload(),
  };
}

function wizardCapabilitiesPayload() {
  const w = state.wizardCaps || {};
  if (w.rcon === null && w.files === null && w.query === null) return {};
  return {
    rcon: !!w.rcon,
    files: !!w.files,
    query: !!w.query,
    process: $("#srv-process")?.value === "local",
    inferred: false,
    probed_at: new Date().toISOString().slice(0, 19),
    notes: w.notes || {},
  };
}

function renderWizardCaps() {
  state.wizardCaps.process = $("#srv-process")?.value === "local";
  renderCapStrip(
    {
      rcon: !!state.wizardCaps.rcon,
      files: !!state.wizardCaps.files,
      query: !!state.wizardCaps.query,
      process: !!state.wizardCaps.process,
    },
    state.wizardCaps.notes || {},
  );
}

function setServerProbe(text, ok) {
  const el = $("#srv-probe");
  if (!el) return;
  el.textContent = text;
  el.className = `server-probe ${ok ? "ok" : "err"}`;
}

async function probeServerRcon() {
  try {
    const data = await api("/api/servers/probe/rcon", {
      method: "POST",
      body: JSON.stringify({
        host: $("#srv-rcon-host").value.trim(),
        port: Number($("#srv-rcon-port").value) || 16284,
        password: $("#srv-rcon-pass").value,
      }),
    });
    state.wizardCaps.rcon = true;
    state.wizardCaps.notes = { ...(state.wizardCaps.notes || {}), rcon: data.output || "players ok" };
    renderWizardCaps();
    setServerProbe(data.output || "RCON ok", true);
    showToast("RCON отвечает");
  } catch (e) {
    state.wizardCaps.rcon = false;
    state.wizardCaps.notes = { ...(state.wizardCaps.notes || {}), rcon: e.message };
    renderWizardCaps();
    setServerProbe(e.message, false);
    showToast(e.message, "err");
  }
}

async function probeServerFiles() {
  try {
    const kind = $("#srv-files-kind").value;
    const data = await api("/api/servers/probe/files", {
      method: "POST",
      body: JSON.stringify({
        kind,
        host: $("#srv-ftp-host").value.trim(),
        user: $("#srv-ftp-user").value.trim(),
        password: $("#srv-ftp-pass").value,
        root: $("#srv-files-root").value.trim(),
        port: kind === "sftp" ? Number($("#srv-sftp-port")?.value) || 22 : 21,
        sftp_key_path: ($("#srv-sftp-key-path") && $("#srv-sftp-key-path").value.trim()) || "",
        sftp_private_key: ($("#srv-sftp-key-inline") && $("#srv-sftp-key-inline").value) || "",
      }),
    });
    const names = (data.entries || []).slice(0, 8).join(", ");
    const chk = data.checks || {};
    const detail = [
      chk.server_console ? "console" : "",
      chk.logs_dir ? "Logs" : "",
      (chk.ini_files || []).length ? `ini×${chk.ini_files.length}` : "",
    ].filter(Boolean).join(" · ");
    state.wizardCaps.files = !!data.ok;
    state.wizardCaps.notes = { ...(state.wizardCaps.notes || {}), files: detail || names || data.error || (data.ok ? "ok" : "нет") };
    renderWizardCaps();
    setServerProbe(data.ok ? `Файлы: ${detail || names || "ok"}` : (data.error || "нет каталога"), data.ok);
    showToast(data.ok ? "Файлы доступны" : (data.error || "файлы недоступны"), data.ok ? "ok" : "err");
  } catch (e) {
    state.wizardCaps.files = false;
    state.wizardCaps.notes = { ...(state.wizardCaps.notes || {}), files: e.message };
    renderWizardCaps();
    setServerProbe(e.message, false);
    showToast(e.message, "err");
  }
}

async function probeServerQuery() {
  const host = $("#srv-public-host").value.trim() || $("#srv-rcon-host").value.trim();
  const port = Number($("#srv-query-port").value) || 16281;
  try {
    const data = await api("/api/servers/probe/query", {
      method: "POST",
      body: JSON.stringify({ host, port }),
    });
    state.wizardCaps.query = !!data.ok;
    state.wizardCaps.notes = { ...(state.wizardCaps.notes || {}), query: data.ok ? "A2S ok" : (data.error || "нет ответа") };
    renderWizardCaps();
    setServerProbe(data.ok ? "Query A2S отвечает" : (data.error || "Query молчит"), !!data.ok);
  } catch (e) {
    state.wizardCaps.query = false;
    setServerProbe(e.message, false);
    showToast(e.message, "err");
  }
}

async function probeServerAll() {
  try {
    const payload = serverFormPayload();
    const data = await api("/api/servers/probe/all", { method: "POST", body: JSON.stringify(payload) });
    state.wizardCaps = {
      rcon: !!data.rcon,
      files: !!data.files,
      query: !!data.query,
      process: !!data.process,
      notes: data.notes || {},
    };
    renderWizardCaps();
    const parts = ["rcon", "files", "query", "process"].map((k) => `${k}:${data[k] ? "да" : "нет"}`);
    setServerProbe(parts.join(" · "), !!(data.rcon || data.files));
    showToast("Каналы проверены");
  } catch (e) {
    setServerProbe(e.message, false);
    showToast(e.message, "err");
  }
}

async function submitServerForm(e, { draft = false } = {}) {
  if (e && e.preventDefault) e.preventDefault();
  const payload = serverFormPayload();
  payload.draft = draft;
  if (!payload.name) {
    showToast("Укажи имя сервера", "err");
    return;
  }
  if (payload.files.kind === "local") {
    const ok = confirm(t("confirm.local_path"));
    if (!ok) return;
  }
  try {
    const editId = ($("#srv-edit-id") && $("#srv-edit-id").value) || state.editingServerId;
    let created;
    if (editId) {
      created = await api(`/api/servers/${encodeURIComponent(editId)}`, { method: "PATCH", body: JSON.stringify(payload) });
    } else {
      created = await api("/api/servers", { method: "POST", body: JSON.stringify(payload) });
    }
    if (!draft) {
      await api(`/api/servers/${encodeURIComponent(created.id)}/activate`, { method: "POST", body: "{}" });
    }
    if (!draft) {
      $("#srv-rcon-pass").value = "";
      $("#srv-ftp-pass").value = "";
      if ($("#srv-sftp-key-inline")) $("#srv-sftp-key-inline").value = "";
    }
    state.editingServerId = created.id;
    if ($("#srv-edit-id")) $("#srv-edit-id").value = created.id;
    await loadServers();
    await loadHealth();
    if (!draft) await pollStatus();
    if (activeCapabilities().files) loadConfigs().catch(() => {});
    applyCapabilities();
    showToast(draft ? `Черновик: ${created.name}` : `Сохранён и активен: ${created.name}`);
  } catch (err) {
    showToast(err.message, "err");
  }
}

function fillFormFromProfile(p) {
  if (!p) return;
  state.editingServerId = p.id;
  if ($("#srv-edit-id")) $("#srv-edit-id").value = p.id;
  $("#srv-name").value = p.name || "";
  $("#srv-hoster").value = p.hoster || "vps";
  $("#srv-version").value = p.game_version || "";
  $("#srv-rcon-host").value = (p.rcon && p.rcon.host) || "";
  $("#srv-rcon-port").value = (p.rcon && p.rcon.port) || 16284;
  $("#srv-files-kind").value = (p.files && p.files.kind) || "ftp";
  $("#srv-ftp-host").value = (p.files && p.files.host) || "";
  $("#srv-ftp-user").value = (p.files && p.files.user) || "";
  $("#srv-files-root").value = (p.files && p.files.root) || "";
  if ($("#srv-files-ini")) $("#srv-files-ini").value = (p.files && p.files.ini) || "world.ini";
  if ($("#srv-sftp-port")) {
    $("#srv-sftp-port").value = (p.files && (p.files.port || p.files.sftp_port)) || 22;
  }
  if ($("#srv-sftp-key-path")) {
    $("#srv-sftp-key-path").value = (p.files && p.files.sftp_key_path) || "";
  }
  if ($("#srv-plugin-meatballs")) {
    $("#srv-plugin-meatballs").checked = !!(p.plugins && p.plugins.meatballs);
  }
  $("#srv-public-host").value = (p.public && p.public.host) || "";
  $("#srv-game-port").value = (p.public && p.public.game_port) || 16282;
  $("#srv-query-port").value = (p.public && p.public.query_port) || 16281;
  $("#srv-process").value = (p.process && p.process.kind) || "none";
  toggleServerFormKind();
}

async function editActiveProfile() {
  const active = (state.servers || []).find((s) => s.id === state.serversActive);
  if (!active) {
    showToast("Нет активного профиля", "err");
    return;
  }
  fillFormFromProfile(active);
  switchView("home");
  document.getElementById("server-form")?.scrollIntoView({ behavior: "smooth" });
  showToast(`Редактирование: ${active.name}`);
}

async function deleteActiveProfile() {
  const id = state.serversActive;
  if (!id) return;
  if (!confirm(t("confirm.delete_profile", { id }))) return;
  try {
    await api(`/api/servers/${encodeURIComponent(id)}`, { method: "DELETE" });
    state.editingServerId = null;
    if ($("#srv-edit-id")) $("#srv-edit-id").value = "";
    await loadServers();
    await loadHealth();
    applyCapabilities();
    showToast("Профиль удалён");
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function checkOnboarding() {
  try {
    const data = await api("/api/onboarding");
    if (data.needs_wizard) {
      $("#onboarding-modal")?.classList.remove("hidden");
    }
  } catch { /* ignore */ }
}

function renderSmoke(data) {
  const box = $("#smoke-status");
  if (!box) return;
  const sm = (data && data.smoke) || {};
  const verdictKey = {
    pass: "smoke.verdict.pass",
    fail: "smoke.verdict.fail",
    running: "smoke.verdict.running",
    idle: "smoke.verdict.idle",
  }[sm.verdict] || null;
  const label = verdictKey ? t(verdictKey) : (sm.label || "—");
  const cells = [
    [I18n.currentLang() === "en" ? "Verdict" : "Вердикт", label, sm.verdict === "pass" ? "ok" : sm.verdict === "fail" ? "bad" : ""],
    ["Cachedir", data.cache_dir || "—", data.cache_dir ? "ok" : "bad"],
    ["Dedicated", data.kind_label || data.kind || "—", data.dedicated_dir ? "ok" : "bad"],
    [I18n.currentLang() === "en" ? "Mirror" : "Зеркало", data.mirror_root || "—", ""],
  ];
  box.innerHTML = cells.map(([k, v, cls]) => `
    <div class="net-stat ${cls}">
      <span class="net-label">${escapeHtml(k)}</span>
      <span class="net-value">${escapeHtml(String(v))}</span>
    </div>`).join("");
  const log = $("#smoke-log");
  if (!log) return;
  const lines = (sm.log_tail || []).concat(sm.errors || []).map((l) => String(l));
  log.textContent = lines.length ? lines.join("\n") : "(нет лога — сначала Pull на Зеркале, затем Start smoke)";
  if (sm.errors && sm.errors.length) {
    log.innerHTML = lines.map((l) => {
      const hot = /illegalargumentexception|duplicate texture|mod id mismatch|nullpointerexception/i.test(l);
      return `<span class="${hot ? "smoke-err-hot" : "smoke-line"}">${escapeHtml(l)}</span>`;
    }).join("\n");
  }
}

async function loadSmoke() {
  try {
    const data = await api("/api/smoke/status");
    renderSmoke(data);
    if (data.running && !state.smokePoll) {
      state.smokePoll = setInterval(() => {
        if (state.activeView === "smoke") loadSmoke();
        else { clearInterval(state.smokePoll); state.smokePoll = null; }
      }, 3000);
    }
    if (!data.running && state.smokePoll) {
      clearInterval(state.smokePoll);
      state.smokePoll = null;
    }
  } catch (e) {
    const box = $("#smoke-status");
    if (box) box.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
  }
}

async function startSmoke() {
  try {
    const data = await api("/api/smoke/start", { method: "POST", body: "{}" });
    renderSmoke(data);
    showToast("Smoke test запущен");
    loadSmoke();
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function stopSmoke() {
  try {
    const data = await api("/api/smoke/stop", { method: "POST", body: "{}" });
    renderSmoke(data);
    showToast("Smoke test остановлен");
  } catch (e) {
    showToast(e.message, "err");
  }
}

function renderFileTree() {
  const tree = $("#file-tree");
  tree.innerHTML = "";
  if (!state.groups.length) {
    tree.innerHTML = '<p class="muted">No config files on FTP</p>';
    return;
  }
  for (const group of state.groups) {
    const section = document.createElement("div");
    section.className = "tree-group";
    const title = document.createElement("div");
    title.className = "tree-group-title";
    title.textContent = group.label;
    section.appendChild(title);
    const list = document.createElement("ul");
    list.className = "tree-list";
    for (const file of group.files) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      const open = state.tabs.has(file.filename);
      const active = state.activeTab === file.filename;
      btn.className = "tree-file" + (active ? " active" : open ? " open" : "");
      btn.textContent = file.filename + (state.tabs.get(file.filename)?.dirty ? " ●" : "");
      btn.title = file.remote_path;
      btn.onclick = () => openConfig(file.filename);
      li.appendChild(btn);
      list.appendChild(li);
    }
    section.appendChild(list);
    tree.appendChild(section);
  }
}

function renderTabs() {
  const tabsEl = $("#config-tabs");
  tabsEl.innerHTML = "";
  for (const [filename, tab] of state.tabs) {
    const wrap = document.createElement("button");
    wrap.type = "button";
    wrap.className = "editor-tab" + (state.activeTab === filename ? " active" : "");
    if (tab.dirty) {
      const dot = document.createElement("span");
      dot.className = "dirty-dot";
      wrap.appendChild(dot);
    }
    const label = document.createElement("span");
    label.textContent = filename;
    wrap.appendChild(label);
    const close = document.createElement("span");
    close.className = "tab-close";
    close.textContent = "×";
    close.onclick = (e) => { e.stopPropagation(); closeTab(filename); };
    wrap.appendChild(close);
    wrap.onclick = () => switchTab(filename);
    tabsEl.appendChild(wrap);
  }
  renderFileTree();
}

function flushActiveToState() {
  if (!state.activeTab || !state.editor) return;
  const tab = state.tabs.get(state.activeTab);
  if (!tab) return;
  tab.content = state.editor.getValue();
  tab.dirty = tab.content !== tab.original;
}

function switchTab(filename) {
  if (!state.tabs.has(filename)) return;
  flushActiveToState();
  state.activeTab = filename;
  const tab = state.tabs.get(filename);
  state.applyingEditor = true;
  state.editor.setValue(tab.content);
  setEditorMode(tab.language);
  state.applyingEditor = false;
  $("#current-file").textContent = tab.remotePath || filename;
  $("#btn-save").disabled = false;
  renderTabs();
  state.editor.focus();
}

function closeTab(filename) {
  const tab = state.tabs.get(filename);
  if (!tab) return;
  if (tab.dirty && !confirm(`${filename} has unsaved changes. Close anyway?`)) return;
  state.tabs.delete(filename);
  if (state.activeTab === filename) {
    const next = state.tabs.keys().next().value || null;
    state.activeTab = next;
    if (next) switchTab(next);
    else {
      state.applyingEditor = true;
      state.editor.setValue("");
      state.applyingEditor = false;
      $("#current-file").textContent = "No file open";
      $("#editor-lang").textContent = "";
      $("#btn-save").disabled = true;
      renderTabs();
    }
  } else renderTabs();
}

async function loadConfigs(force = false) {
  const url = force ? "/api/configs?refresh=true" : "/api/configs";
  const data = await api(url);
  state.configs = data.configs;
  state.groups = data.groups;
  renderFileTree();
}

async function openConfig(filename) {
  switchView("files");
  if (state.tabs.has(filename)) { switchTab(filename); return; }
  try {
    const data = await api(`/api/config/load?filename=${encodeURIComponent(filename)}`);
    flushActiveToState();
    state.tabs.set(filename, {
      content: data.content || "",
      original: data.content || "",
      language: data.language || "plaintext",
      remotePath: data.remote_path,
      dirty: false,
    });
    state.activeTab = filename;
    state.applyingEditor = true;
    state.editor.setValue(data.content || "");
    setEditorMode(data.language);
    state.applyingEditor = false;
    $("#current-file").textContent = data.remote_path;
    $("#btn-save").disabled = false;
    renderTabs();
    showToast(`Opened ${filename}`);
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function saveActiveTab() {
  if (!state.activeTab || state.saving) return;
  flushActiveToState();
  const tab = state.tabs.get(state.activeTab);
  if (!tab) return;
  state.saving = true;
  $("#save-spinner").classList.remove("hidden");
  $("#save-label").textContent = "Saving…";
  $("#btn-save").disabled = true;
  try {
    const data = await api("/api/config/save", {
      method: "POST",
      body: JSON.stringify({ filename: state.activeTab, content: tab.content }),
    });
    tab.original = tab.content;
    tab.dirty = false;
    renderTabs();
    showToast(`Pushed to FTP · backup ${data.backup}`);
  } catch (e) {
    if (e.detail && e.detail.reason === "host_panel_wins" && e.detail.remote_content != null) {
      tab.content = e.detail.remote_content;
      tab.original = e.detail.remote_content;
      tab.dirty = false;
      if (state.editor && state.activeTab) {
        state.applyingEditor = true;
        state.editor.setValue(tab.content);
        state.applyingEditor = false;
      }
      renderTabs();
      showToast("Хост изменил файл — взяли версию XLGAMES", "warn");
    } else {
      showToast(e.message, "err");
    }
  } finally {
    state.saving = false;
    $("#save-spinner").classList.add("hidden");
    $("#save-label").textContent = "Save & Push to FTP";
    $("#btn-save").disabled = !state.activeTab;
  }
}

/* —— RCON —— */
function connectWs() {
  if (!state.authDisabled && !state.token) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const q = state.token ? `?token=${encodeURIComponent(state.token)}` : "";
  state.ws = new WebSocket(`${proto}://${location.host}/ws/console${q}`);
  state.ws.onopen = () => appendConsole("[ws] connected", "sys");
  state.ws.onclose = (ev) => {
    if (ev.code === 4401) {
      appendConsole("[ws] auth required", "err");
      showAuthModal("login");
      return;
    }
    appendConsole("[ws] disconnected — retry 3s", "sys");
    setTimeout(connectWs, 3000);
  };
  state.ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "result") {
      appendConsole(`❯ ${msg.command}`, "cmd");
      appendConsole(msg.output || "(empty)", classifyConsoleLine(msg.output || ""));
      if (msg.command === "players") pollStatus();
    } else if (msg.type === "error") {
      appendConsole(msg.message, "err");
    }
  };
}

function pushHistory(command) {
  if (!state.commandHistory.length || state.commandHistory[0] !== command) {
    state.commandHistory.unshift(command);
    if (state.commandHistory.length > HISTORY_LIMIT) state.commandHistory.length = HISTORY_LIMIT;
  }
  state.historyIndex = -1;
}

function sendRcon(command) {
  command = command.trim();
  if (!command) return;
  pushHistory(command);
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ type: "exec", command }));
    return;
  }
  api("/api/rcon/exec", { method: "POST", body: JSON.stringify({ command }) })
    .then((data) => {
      appendConsole(`❯ ${data.command}`, "cmd");
      appendConsole(data.output, classifyConsoleLine(data.output));
      if (command.startsWith("players") || command.startsWith("setaccesslevel")) pollStatus();
    })
    .catch((e) => appendConsole(e.message, "err"));
}

function renderTrainersRoster() {
  const el = $("#trainers-roster");
  if (!el) return;
  const snap = state.slots || {};
  const roster = snap.roster || [];
  const activeIds = new Set((snap.npcs || []).map((n) => n.id));
  if (!roster.length) {
    el.innerHTML = '<p class="muted">Ростер ещё не загружен</p>';
    return;
  }
  el.innerHTML = roster.map((n) => {
    const on = activeIds.has(n.id);
    return `<div class="npc-card player-card${on ? "" : " npc-off"}">
      <div class="player-name">${escapeHtml(n.name)}
        <span class="npc-badge${on ? "" : " npc-badge-off"}">${on ? "в мире" : "выкл"}</span>
      </div>
      <div class="player-id">${escapeHtml(n.role_ru || n.role || "")} · ${escapeHtml(n.city || "")}</div>
      <div class="player-id">научит ${escapeHtml(n.teaches || "—")}</div>
    </div>`;
  }).join("");
  const nextEl = $("#npc-next");
  const next = snap.next;
  if (nextEl) {
    nextEl.textContent = next
      ? `Следующий в очереди (ещё не в моде): ${next.name} · ${next.role_ru} · ${next.city} · ${next.teaches}`
      : "";
  }
}

function hasElevatedAccess(player) {
  if (player?.is_elevated === true) return true;
  const lvl = String(player?.access_level || "user").toLowerCase();
  return ["admin", "moderator", "overseer", "gm", "observer", "priority"].includes(lvl);
}

function renderPlayersPage() {
  const el = $("#players-page-list");
  if (!el) return;
  if (!state.players.length) {
    el.innerHTML = '<p class="muted">Нет игроков онлайн</p>';
    return;
  }
  el.innerHTML = "";
  for (const p of state.players) {
    const elevated = hasElevatedAccess(p);
    const accessLabel = elevated ? String(p.access_level || "admin").toUpperCase() : "";
    const card = document.createElement("div");
    card.className = `player-card${elevated ? " player-card-admin" : ""}`;
    card.innerHTML = `
      <div class="player-name">
        ${escapeHtml(p.name)}
        ${elevated ? `<span class="player-admin-badge">${escapeHtml(accessLabel)}</span>` : ""}
      </div>
      <div class="player-id">${escapeHtml(p.steamid || p.id || "—")}</div>
      <div class="player-actions">
        <button type="button" class="btn xs danger" data-act="kick">Kick</button>
        <button type="button" class="btn xs danger" data-act="ban">Ban</button>
        <button type="button" class="btn xs" data-act="tp">Teleport</button>
        <button type="button" class="btn xs${elevated ? " admin-active" : ""}" data-act="admin">${elevated ? t("players.admin_active") : t("players.admin_grant")}</button>
      </div>`;
    card.querySelectorAll("[data-act]").forEach((btn) => {
      btn.onclick = () => playerAction(btn.dataset.act, p);
    });
    el.appendChild(card);
  }
}

function renderFounders() {
  const el = $("#founders-list");
  if (!el) return;
  const rows = state.founders || [];
  if (!rows.length) {
    el.innerHTML = '<p class="muted">Пока никого не добавили</p>';
    return;
  }
  el.innerHTML = rows.map((row) => {
    const joined = row.joined_at ? "зашёл" : "ждём";
    const account = row.account_created ? "аккаунт есть" : "без adduser";
    return `<div class="founder-row">
      <div>
        <div class="player-name">${escapeHtml(row.name)}</div>
        <div class="player-id">${escapeHtml(row.steamid || "нет SteamID")} · ${joined} · ${account}${row.note ? " · " + escapeHtml(row.note) : ""}</div>
      </div>
      <button type="button" class="btn xs danger" data-fid="${escapeHtml(row.id)}">Убрать</button>
    </div>`;
  }).join("");
  el.querySelectorAll("[data-fid]").forEach((btn) => {
    btn.onclick = () => removeFounder(btn.dataset.fid);
  });
}

function renderLaunchCard(text) {
  const card = $("#invite-card");
  if (card) card.textContent = text || "";
  const meta = $("#launch-meta");
  const ep = (state.launch && state.launch.endpoints) || {};
  if (meta) {
    meta.textContent = ep.host
      ? `${ep.public_name} · ${ep.host}:${ep.game_port} · query ${ep.query_port}`
      : "Задай PUBLIC_HOST / RCON_HOST в .env";
  }
  const discordBox = $("#label-discord-announce");
  if (discordBox) discordBox.classList.toggle("hidden", !ep.webhook_configured);
}

async function copyInvite(withPassword) {
  try {
    const data = await api("/api/launch/invite", {
      method: "POST",
      body: JSON.stringify({ include_password: !!withPassword }),
    });
    await navigator.clipboard.writeText(data.text || "");
    showToast(withPassword ? "Инвайт с паролем скопирован" : "Инвайт скопирован");
  } catch (e) {
    showToast(e.message, "err");
  }
}

function fillSlotsForm(data) {
  if (!data) return;
  state.slots = data;
  const count = $("#slots-count");
  if (count) count.value = String(data.count ?? 0);
  const names = (data.npcs || []).map((n) => n.name).join(", ");
  const hint = $("#slots-hint");
  if (hint) {
    hint.textContent = data.count
      ? `Сейчас в мире: ${names}. В Steam, RCON players и вкладке «Игроки» их нет.`
      : "0 тренеров. Можно включить 1–5: Rook, Otto, Sarge, Ash, Vera.";
  }
  renderTrainersRoster();
}

async function loadSlots() {
  try {
    const data = await api("/api/slots");
    fillSlotsForm(data);
  } catch (e) {
    const hint = $("#slots-hint");
    if (hint) hint.textContent = e.message;
  }
}

async function submitSlots(e) {
  e.preventDefault();
  const count = Number($("#slots-count").value || 0);
  try {
    const data = await api("/api/slots", {
      method: "POST",
      body: JSON.stringify({
        count,
        x: 0,
        y: 0,
        z: 0,
        prefix: "Dummy",
        push_ftp: !!$("#chk-slots-ftp")?.checked,
        upload_mod: !!$("#chk-slots-mod")?.checked,
      }),
    });
    fillSlotsForm(data);
    showToast(data.count ? `Тренеры в мире: ${data.count}` : "Тренеры выключены");
  } catch (err) {
    showToast(err.message, "err");
  }
}

async function loadLaunch() {
  try {
    const data = await api("/api/launch");
    state.launch = data;
    state.founders = data.founders || [];
    renderLaunchCard(data.invite);
    renderFounders();
  } catch (e) {
    const card = $("#invite-card");
    if (card) card.textContent = e.message;
  }
}

async function submitFounder(e) {
  e.preventDefault();
  try {
    const data = await api("/api/launch/founders", {
      method: "POST",
      body: JSON.stringify({
        name: $("#founder-name").value.trim(),
        steamid: $("#founder-steamid").value.trim(),
        note: $("#founder-note").value.trim(),
      }),
    });
    state.founders = data.founders || [];
    renderFounders();
    $("#founder-form").reset();
    showToast(`В списке: ${data.founder.name}`);
  } catch (err) {
    showToast(err.message, "err");
  }
}

async function removeFounder(id) {
  try {
    const data = await api(`/api/launch/founders/${id}`, { method: "DELETE" });
    state.founders = data.founders || [];
    renderFounders();
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function submitAddUser(e) {
  e.preventDefault();
  const name = $("#adduser-name").value.trim();
  if (!name) { showToast("Укажи ник", "err"); return; }
  if (!confirm(`Создать аккаунт ${name} на живом сервере (RCON adduser)?`)) return;
  try {
    const data = await api("/api/launch/adduser", {
      method: "POST",
      body: JSON.stringify({
        name,
        password: $("#adduser-pass").value.trim(),
      }),
    });
    state.founders = data.founders || [];
    renderFounders();
    showToast(`Пароль для ${name}: ${data.password}`, "warn");
    appendConsole(`❯ ${data.command}`, "cmd");
    appendConsole(data.output || "", classifyConsoleLine(data.output || ""));
  } catch (err) {
    showToast(err.message, "err");
  }
}

async function submitAnnounce(e) {
  e.preventDefault();
  const message = $("#announce-text").value.trim();
  if (!message) return;
  try {
    const data = await api("/api/launch/announce", {
      method: "POST",
      body: JSON.stringify({
        message,
        discord: !!$("#chk-announce-discord")?.checked,
      }),
    });
    showToast("Сообщение ушло в мир");
    appendConsole(`❯ ${data.command}`, "cmd");
    appendConsole(data.output || "", classifyConsoleLine(data.output || ""));
  } catch (err) {
    showToast(err.message, "err");
  }
}

async function playerAction(act, player) {
  const name = player.name;
  const steamid = player.steamid || "";
  if (act === "admin") {
    const elevated = hasElevatedAccess(player);
    if (elevated) {
      const msg = t("players.revoke_admin_confirm").replace("{name}", name);
      if (!confirm(msg)) return;
      await runPlayerRcon(`setaccesslevel "${name}" user`);
    } else {
      await runPlayerRcon(`setaccesslevel "${name}" admin`);
    }
    setTimeout(() => loadPlayers(), 900);
    return;
  }
  const cmds = {
    kick: `kick "${name}"`,
    ban: steamid ? `banid ${steamid}` : `banuser "${name}"`,
    tp: `teleport "${name}"`,
  };
  const cmd = cmds[act];
  if (!cmd) return;
  if ((act === "kick" || act === "ban") && !confirm(`${act.toUpperCase()} ${name}?`)) return;
  await runPlayerRcon(cmd);
}

async function runPlayerRcon(command) {
  try {
    const data = await api("/api/rcon/exec", { method: "POST", body: JSON.stringify({ command }) });
    appendConsole(`❯ ${data.command}`, "cmd");
    appendConsole(data.output, classifyConsoleLine(data.output));
    const out = String(data.output || "");
    if (/access level.*unknown/i.test(out) || /^unknown command/i.test(out)) {
      showToast(out.split("\n")[0] || "RCON error", "err");
      return data;
    }
    showToast(`Sent: ${command}`);
    return data;
  } catch (err) {
    showToast(err.message, "err");
    throw err;
  }
}

async function loadPlayers() {
  try {
    const data = await api("/api/rcon/players");
    state.players = realPlayers(data.players || []);
    if (data.founders) {
      state.founders = data.founders;
      renderFounders();
    }
    updatePlayersPill(state.players.length);
    renderPlayersPage();
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function quickAction(action) {
  try {
    if (action === "graceful") {
      if (!confirm("Start graceful restart (~5 min countdown)?")) return;
      await api("/api/rcon/graceful-restart", { method: "POST" });
      appendConsole("[system] Graceful restart started (~5 min)", "sys");
      return;
    }
    const data = await api(`/api/rcon/quick/${action}`, { method: "POST" });
    appendConsole(`❯ ${data.command}`, "cmd");
    appendConsole(data.output, classifyConsoleLine(data.output));
    if (action === "players") {
      state.players = realPlayers(data.players || []);
      renderPlayersPage();
      pollStatus();
    }
  } catch (e) {
    appendConsole(e.message, "err");
  }
}

/* —— Scheduler —— */
async function loadScheduler() {
  try {
    const data = await api("/api/scheduler/tasks");
    state.schedulerTasks = data.tasks || [];
    renderScheduler();
  } catch (e) {
    $("#scheduler-list").innerHTML = `<p class="muted err">${escapeHtml(e.message)}</p>`;
  }
}

function renderScheduler() {
  const el = $("#scheduler-list");
  if (!state.schedulerTasks.length) {
    el.innerHTML = '<p class="muted">Нет заданий. Создайте первое.</p>';
    return;
  }
  el.innerHTML = "";
  for (const task of state.schedulerTasks) {
    const card = document.createElement("div");
    card.className = "task-card" + (task.enabled ? "" : " task-disabled");
    const cf = task.cron_fields || {};
    card.innerHTML = `
      <div class="task-main">
        <div class="task-icon">📅</div>
        <div class="task-info">
          <div class="task-name">${escapeHtml(task.name)}</div>
          <div class="task-meta muted">Последний запуск: ${escapeHtml(task.last_run_label || "Никогда")}</div>
          <code class="task-cmd">${escapeHtml(task.command)}</code>
        </div>
      </div>
      <div class="task-cron">
        <div class="cron-col"><span>Мин</span><b>${escapeHtml(cf.minute || "*")}</b></div>
        <div class="cron-col"><span>Час</span><b>${escapeHtml(cf.hour || "*")}</b></div>
        <div class="cron-col"><span>День</span><b>${escapeHtml(cf.day || "*")}</b></div>
        <div class="cron-col"><span>Мес</span><b>${escapeHtml(cf.month || "*")}</b></div>
        <div class="cron-col"><span>Нед</span><b>${escapeHtml(cf.weekday || "*")}</b></div>
      </div>
      <div class="task-actions">
        <span class="task-badge ${task.enabled ? "active" : "inactive"}">${task.enabled ? "АКТИВНЫЙ" : "ВЫКЛ"}</span>
        <button type="button" class="btn xs" data-act="run">Run</button>
        <button type="button" class="btn xs" data-act="edit">Edit</button>
        <button type="button" class="btn xs ghost" data-act="toggle">${task.enabled ? "Off" : "On"}</button>
        <button type="button" class="btn xs danger" data-act="delete">Del</button>
      </div>`;
    card.querySelector('[data-act="run"]').onclick = () => runTaskNow(task.id);
    card.querySelector('[data-act="edit"]').onclick = () => openTaskModal(task);
    card.querySelector('[data-act="toggle"]').onclick = () => toggleTask(task);
    card.querySelector('[data-act="delete"]').onclick = () => deleteTask(task.id);
    el.appendChild(card);
  }
}

function buildCron() {
  return [
    $("#cron-min").value.trim(),
    $("#cron-hour").value.trim(),
    $("#cron-day").value.trim(),
    $("#cron-month").value.trim(),
    $("#cron-weekday").value.trim(),
  ].join(" ");
}

function openTaskModal(task = null) {
  $("#task-modal").classList.remove("hidden");
  $("#task-modal-title").textContent = task ? "Редактировать задание" : "Новое задание";
  $("#task-id").value = task?.id || "";
  $("#task-name").value = task?.name || "";
  $("#task-preset").value = task?.preset || "custom";
  $("#task-command").value = task?.command || "";
  $("#task-enabled").checked = task ? task.enabled : true;
  if (task?.cron_fields) {
    $("#cron-min").value = task.cron_fields.minute;
    $("#cron-hour").value = task.cron_fields.hour;
    $("#cron-day").value = task.cron_fields.day;
    $("#cron-month").value = task.cron_fields.month;
    $("#cron-weekday").value = task.cron_fields.weekday;
  } else {
    $("#cron-min").value = "0";
    $("#cron-hour").value = "*";
    $("#cron-day").value = "*";
    $("#cron-month").value = "*";
    $("#cron-weekday").value = "*";
  }
}

function closeTaskModal() {
  $("#task-modal").classList.add("hidden");
}

async function saveTaskForm(e) {
  e.preventDefault();
  const id = $("#task-id").value;
  const body = {
    name: $("#task-name").value.trim(),
    command: $("#task-command").value.trim(),
    cron: buildCron(),
    preset: $("#task-preset").value,
    enabled: $("#task-enabled").checked,
  };
  try {
    if (id) {
      await api(`/api/scheduler/tasks/${id}`, { method: "PATCH", body: JSON.stringify(body) });
      showToast("Задание обновлено");
    } else {
      await api("/api/scheduler/tasks", { method: "POST", body: JSON.stringify(body) });
      showToast("Задание создано");
    }
    closeTaskModal();
    loadScheduler();
  } catch (err) {
    showToast(err.message, "err");
  }
}

async function toggleTask(task) {
  try {
    await api(`/api/scheduler/tasks/${task.id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: !task.enabled }),
    });
    loadScheduler();
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function deleteTask(id) {
  if (!confirm("Удалить задание?")) return;
  try {
    await api(`/api/scheduler/tasks/${id}`, { method: "DELETE" });
    loadScheduler();
    showToast("Удалено");
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function runTaskNow(id) {
  try {
    const data = await api(`/api/scheduler/tasks/${id}/run`, { method: "POST" });
    showToast(`Выполнено: ${data.command}`);
    loadScheduler();
  } catch (e) {
    showToast(e.message, "err");
  }
}

/* —— Home —— */
function renderHomeStatus(status, world, local) {
  const el = $("#home-status");
  if (!el) return;
  const remote = (world && world.remote) || {};
  const loc = local || {};
  const players = realPlayers(status.players || state.players || []);
  const cells = [
    ["Хост RCON", status.rcon_online ? "ONLINE" : "OFFLINE", status.rcon_online ? "ok" : "bad"],
    ["Мир", remote.label || remote.stage || "—", worldStageClass(remote.stage)],
    ["Игроки", `${players.length}/${state.maxPlayers}`, ""],
    ["Local", loc.running ? "Running" : "Stopped", loc.running ? "ok" : ""],
  ];
  el.innerHTML = cells.map(([k, v, cls]) => `
    <div class="net-stat ${cls}">
      <span class="net-label">${escapeHtml(k)}</span>
      <span class="net-value">${escapeHtml(String(v))}</span>
    </div>`).join("");
  const strip = $("#home-players");
  if (strip) {
    strip.innerHTML = players.length
      ? players.map((p) => `<span class="home-player-chip">${escapeHtml(p.name)}</span>`).join("")
      : '<p class="muted">Нет игроков онлайн</p>';
  }
}

async function createPanelSnapshot() {
  const btn = $("#btn-panel-snapshot");
  if (btn) btn.disabled = true;
  try {
    showToast(t("home.snapshot_working") || "Snapshot…");
    const data = await api("/api/panel/snapshot", { method: "POST", body: "{}" });
    if (!data || !data.ok) {
      throw new Error((data && data.detail) || "Snapshot failed");
    }
    const href = data.download || `/api/panel/snapshot/file?name=${encodeURIComponent(data.filename || "")}`;
    const headers = {};
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    const res = await fetch(href, { credentials: "same-origin", headers });
    if (!res.ok) throw new Error(`Download failed: ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = data.filename || "panel-snapshot.txt";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    const where = data.relative || data.path || data.filename;
    showToast(`${t("home.snapshot_ok")} · ${data.file_count || "?"} files · ${where}`);
  } catch (e) {
    const msg = String(e && e.message ? e.message : e);
    if (msg.includes("404")) {
      showToast("Snapshot API 404 — перезапусти панель (нужна 3.13.1+)", "err");
    } else {
      showToast(msg, "err");
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function loadHome() {
  try {
    applyCapabilities();
    const canFiles = !!activeCapabilities().files;
    const [status, local, log] = await Promise.all([
      api("/api/status"),
      api("/api/local-server").catch(() => ({})),
      canFiles ? api("/api/logs/tail?kind=console&lines=400").catch(() => ({})) : Promise.resolve({}),
    ]);
    state.players = realPlayers(status.players || []);
    updatePlayersPill(state.players.length);
    updateStatusPill(status.rcon_online, status.error);
    renderHomeStatus(status, {}, local);
    const extra = (log.content || "").split(/\r?\n/).filter((l) => /ERROR|EXCEPTION/i.test(l)).slice(-5);
    const list = $("#home-errors");
    if (list) {
      if (!canFiles) list.innerHTML = '<li class="muted">нужен FTP или локальный путь</li>';
      else list.innerHTML = extra.length
        ? extra.map((l) => `<li>${escapeHtml(l)}</li>`).join("")
        : '<li class="muted">нет</li>';
    }
    api("/api/world/status").then((world) => {
      renderHomeStatus(status, world, local);
      const errors = (world.remote && world.remote.errors) || [];
      if (list && errors.length) {
        list.innerHTML = errors.slice(-5).map((l) => `<li>${escapeHtml(l)}</li>`).join("");
      }
    }).catch(() => {});
  } catch (e) {
    const el = $("#home-status");
    if (el) el.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
  }
}

async function hardRestart() {
  if (!confirm("Сейчас save + quit. XLGAMES поднимет процесс. Продолжить?")) return;
  if (!confirm("Точно перезапустить хост прямо сейчас?")) return;
  sendRcon("save");
  setTimeout(() => sendRcon("quit"), 1500);
  showToast("save + quit отправлены");
}

function jumpView(view, filename) {
  switchView(view);
  if (filename) openConfig(filename);
}

/* —— Server log —— */
async function loadServerLog() {
  const kind = $("#log-kind")?.value || state.logKind || "console";
  state.logKind = kind;
  const auditPanel = $("#audit-panel");
  const pre = $("#server-log");
  if (kind === "audit") {
    if (auditPanel) auditPanel.classList.remove("hidden");
    if (pre) pre.classList.add("hidden");
    return loadAdminAudit();
  }
  if (auditPanel) auditPanel.classList.add("hidden");
  if (pre) pre.classList.remove("hidden");
  try {
    const data = await api(`/api/logs/tail?kind=${encodeURIComponent(kind)}&lines=500`);
    state.serverLogContent = data.content || "";
    pre.textContent = state.serverLogContent || "(пусто — файла ещё нет на зеркале)";
    pre.scrollTop = pre.scrollHeight;
    $("#log-meta").textContent = data.filename
      ? `${data.filename} · ${data.source || ""} · ${data.total_lines} строк`
      : `${data.label || kind} · файла нет`;
  } catch (e) {
    $("#server-log").textContent = `Error: ${e.message}`;
  }
}

async function loadAdminAudit() {
  const box = $("#audit-table");
  const meta = $("#audit-meta");
  if (!box) return;
  try {
    const data = await api("/api/admintools/audit?limit=250");
    const rows = data.actions || [];
    state.serverLogContent = rows.map((r) => r.raw).join("\n");
    if (meta) {
      meta.textContent = `${t("admintools.audit_title")} · ${data.count || 0} · high ${data.high_risk || 0}`;
    }
    $("#log-meta").textContent = `audit · ${data.total_parsed || 0} parsed`;
    box.innerHTML = rows.length
      ? rows.map((r) => `<div class="audit-row">
          <span>${escapeHtml(r.ts || "—")}</span>
          <span><span class="sev sev-${escapeHtml(r.severity || "low")}">${escapeHtml(r.severity || "low")}</span></span>
          <span>${escapeHtml(r.admin || r.steamid || "—")}</span>
          <span><code>${escapeHtml(r.command || "")}</code> ${escapeHtml(r.args || "")}</span>
          <span>${escapeHtml(r.target || r.coords || r.source || "")}</span>
        </div>`).join("")
      : `<p class="muted" style="padding:0.75rem">Нет записей — нужен Pull логов (_admin.txt / _cmd.txt)</p>`;
  } catch (e) {
    box.innerHTML = `<p class="err" style="padding:0.75rem">${escapeHtml(e.message)}</p>`;
  }
}

async function loadCityWipeCities() {
  const box = $("#city-wipe-cities");
  if (!box) return;
  try {
    const data = await api("/api/admintools/cities");
    const cities = data.cities || [];
    box.innerHTML = cities.map((c) => {
      const active = state.cityWipeId === c.id ? " active" : "";
      return `<button type="button" class="city-wipe-card${active}" data-city-id="${escapeHtml(c.id)}">
        <strong>${escapeHtml(c.name)}</strong>
        <span class="city-bbox">${c.x1},${c.y1} → ${c.x2},${c.y2}</span>
      </button>`;
    }).join("");
    box.querySelectorAll("[data-city-id]").forEach((btn) => {
      btn.onclick = () => {
        state.cityWipeId = btn.dataset.cityId;
        loadCityWipeCities();
      };
    });
  } catch (e) {
    box.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
  }
}

async function triggerCityWipe() {
  if (!state.cityWipeId) {
    showToast(t("admintools.pick_city"), "err");
    return;
  }
  const status = $("#city-wipe-status");
  const btn = $("#btn-city-wipe");
  if (btn) btn.disabled = true;
  try {
    const data = await api("/api/admintools/city-wipe", {
      method: "POST",
      body: JSON.stringify({
        city_id: state.cityWipeId,
        refill_loot: !!$("#city-wipe-loot")?.checked,
        reconstruct_containers: !!$("#city-wipe-containers")?.checked,
        upload: true,
        rcon_notify: true,
      }),
    });
    const city = (data.city && data.city.name) || state.cityWipeId;
    const bits = [];
    if (data.uploaded) bits.push("FTP ok");
    if (data.upload_error) bits.push(`upload: ${data.upload_error}`);
    if (data.rcon != null) bits.push("RCON ok");
    if (data.rcon_error) bits.push(`rcon: ${data.rcon_error}`);
    const msg = `${t("admintools.queued")}: ${city} · ${bits.join(" · ") || "local only"}`;
    if (status) status.textContent = msg;
    showToast(msg, data.upload_error && !data.uploaded ? "warn" : "ok");
  } catch (e) {
    if (status) status.textContent = e.message;
    showToast(e.message, "err");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function loadChat() {
  const channel = $("#chat-channel")?.value || "all";
  const el = $("#chat-feed");
  if (!el) return;
  try {
    const data = await api(`/api/chat?channel=${encodeURIComponent(channel)}&limit=200`);
    const rows = data.messages || [];
    el.innerHTML = rows.length
      ? rows.map((m) => `<div class="chat-row">
          <div class="chat-meta">${escapeHtml(m.ts)} · ${escapeHtml(m.chat)} · ${escapeHtml(m.channel)}</div>
          <div><span class="chat-author">${escapeHtml(m.author || "—")}</span> ${escapeHtml(m.text || "")}</div>
        </div>`).join("")
      : `<p class="muted">${escapeHtml(data.note || "Нет сообщений в логе")}</p>`;
    el.scrollTop = el.scrollHeight;
  } catch (e) {
    el.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
  }
}

async function submitChatAnnounce(e) {
  e.preventDefault();
  const text = ($("#chat-announce-text")?.value || "").trim();
  if (!text) return;
  try {
    await api("/api/launch/announce", {
      method: "POST",
      body: JSON.stringify({ message: text, discord: false }),
    });
    $("#chat-announce-text").value = "";
    showToast("servermsg отправлен");
  } catch (err) {
    showToast(err.message, "err");
  }
}

async function loadBans() {
  const list = $("#bans-list");
  const kicks = $("#kicks-list");
  try {
    const data = await api("/api/bans");
    const bans = data.bans || [];
    if (list) {
      list.innerHTML = bans.length
        ? bans.map((b) => `<div class="founder-row">
            <div>
              <div class="player-name">${escapeHtml(b.name || b.steamid || b.raw)}</div>
              <div class="player-id">${escapeHtml(b.kind)} · ${escapeHtml(b.steamid || "—")}</div>
            </div>
            <button type="button" class="btn xs" data-unban-id="${escapeHtml(b.steamid || "")}" data-unban-name="${escapeHtml(b.name || "")}">Снять бан</button>
          </div>`).join("")
        : `<p class="muted">${escapeHtml(data.note || "Список банов пуст")}</p>`;
      list.querySelectorAll("[data-unban-id], [data-unban-name]").forEach((btn) => {
        btn.onclick = () => unbanPlayer(btn.dataset.unbanId, btn.dataset.unbanName);
      });
    }
    if (kicks) {
      const rows = data.kicks || [];
      kicks.innerHTML = rows.length
        ? `<pre class="world-tail">${rows.map((k) => escapeHtml(k.line)).join("\n")}</pre>`
        : "Нет строк kick/disconnect в логах зеркала";
    }
  } catch (e) {
    if (list) list.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
  }
}

async function unbanPlayer(steamid, name) {
  if (!confirm(`Снять бан ${steamid || name}?`)) return;
  try {
    const data = await api("/api/bans/unban", {
      method: "POST",
      body: JSON.stringify({ steamid: steamid || "", name: name || "" }),
    });
    showToast(data.command);
    loadBans();
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function loadPrivates() {
  const list = $("#privates-list");
  const note = $("#privates-note");
  const journal = $("#privates-journal");
  try {
    const data = await api("/api/safehouses");
    if (note) note.textContent = data.note || "";
    const houses = data.safehouses || [];
    const factions = data.factions || [];
    let html = "";
    if (houses.length) {
      html += houses.map((h) => `<div class="npc-card player-card">
        <div class="player-name">${escapeHtml(h.title || h.owner || "приват")}</div>
        <div class="player-id">владелец ${escapeHtml(h.owner || "—")} · ${h.x},${h.y} ${h.w}×${h.h}</div>
        <div class="player-id">члены: ${escapeHtml((h.members || []).join(", ") || "—")}</div>
        ${h.expiry ? `<div class="player-id">last visit / expiry: ${escapeHtml(String(h.expiry))}</div>` : ""}
        <p class="muted">Продление срока — в игре. Панель сейв не пишет.</p>
      </div>`).join("");
    }
    if (factions.length) {
      html += `<h3 class="players-subhead">Фракции</h3>` + factions.map((f) => `<div class="founder-row">
        <div>
          <div class="player-name">${escapeHtml(f.name || "фракция")} ${f.tag ? "[" + escapeHtml(f.tag) + "]" : ""}</div>
          <div class="player-id">${escapeHtml(f.owner || "")} · ${(f.members || []).map(escapeHtml).join(", ")}</div>
        </div>
      </div>`).join("");
    }
    if (list) list.innerHTML = html || '<p class="muted">Нет данных</p>';
    if (journal) {
      const rows = data.journal || [];
      journal.innerHTML = rows.length
        ? `<pre class="world-tail">${rows.map((r) => escapeHtml(r.line)).join("\n")}</pre>`
        : "Журнала _safehouse.txt на зеркале нет";
    }
  } catch (e) {
    if (list) list.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
  }
}

function wipePayload() {
  const x = $("#wipe-x")?.value;
  const y = $("#wipe-y")?.value;
  const cx = $("#wipe-cx")?.value;
  const cy = $("#wipe-cy")?.value;
  const body = {};
  if (cx !== "" && cy !== "") {
    body.cell_x = Number(cx);
    body.cell_y = Number(cy);
  } else if (x !== "" && y !== "") {
    body.x = Number(x);
    body.y = Number(y);
  }
  return body;
}

async function previewWipe() {
  const el = $("#wipe-preview");
  try {
    const data = await api("/api/wipe/preview", {
      method: "POST",
      body: JSON.stringify(wipePayload()),
    });
    state.wipePreview = data;
    const files = data.files || [];
    el.innerHTML = `
      <p>Клетка <strong>${data.cell_x}, ${data.cell_y}</strong> (мир ~${data.world_x}, ${data.world_y}). Файлов: ${data.count}</p>
      <p class="muted">${escapeHtml(data.note || "")}</p>
      ${files.length ? `<ul class="wipe-files">${files.map((f) => `<li>${escapeHtml(f.relative)} · ${f.size} B</li>`).join("")}</ul>` : "<p>На зеркале файлов этой клетки нет — Pull Saves или клетка пустая.</p>"}
      <p>Чтобы вайпнуть, введи <code>${escapeHtml(data.confirm)}</code> и подтверди дважды.</p>
      <input id="wipe-confirm" type="text" placeholder="${escapeHtml(data.confirm)}" />
      <button type="button" id="btn-wipe-apply" class="btn danger sm">Вайп (бэкап + удаление)</button>`;
    const apply = $("#btn-wipe-apply");
    if (apply) apply.onclick = applyWipe;
  } catch (e) {
    el.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
  }
}

async function applyWipe() {
  const prev = state.wipePreview;
  if (!prev) return;
  const typed = ($("#wipe-confirm")?.value || "").trim();
  if (typed !== prev.confirm) {
    showToast(`Нужно ввести ${prev.confirm}`, "err");
    return;
  }
  if (!confirm(`Удалить ${prev.count} файлов клетки ${prev.cell_x},${prev.cell_y}?`)) return;
  if (!confirm("Второй раз: это сотрёт чанк на зеркале и на FTP. Продолжить?")) return;
  try {
    const data = await api("/api/wipe/apply", {
      method: "POST",
      body: JSON.stringify({ ...wipePayload(), confirm: typed, apply: true }),
    });
    showToast(data.ok ? `Вайп: бэкап ${data.backup}` : (data.errors || []).join("; "), data.ok ? "ok" : "err");
    $("#wipe-preview").innerHTML = `<p>Бэкап: <code>${escapeHtml(data.backup || "")}</code></p>
      <p>Локально: ${(data.deleted_local || []).length} · FTP: ${(data.deleted_remote || []).length}</p>
      ${(data.errors || []).length ? `<p class="err">${escapeHtml(data.errors.join("; "))}</p>` : ""}`;
  } catch (e) {
    showToast(e.message, "err");
  }
}

/* —— Network —— */
async function loadNetwork() {
  const el = $("#network-grid");
  el.innerHTML = '<p class="muted">Проверка портов…</p>';
  try {
    const data = await api("/api/network");
    const svc = data.services || {};
    const rows = [
      ["RCON", svc.rcon, data.rcon_online],
      ["Query", svc.query, undefined],
      ["FTP", svc.ftp, data.ftp_ok],
    ];
    const gamePort = data.unmonitored?.game_port ?? data.game_port;
    const unmonitoredNote = data.unmonitored?.reason
      || "UDPPort — нет публичного healthcheck";
    el.innerHTML = `
      <div class="net-summary">
        <div class="net-stat ${data.rcon_online ? "ok" : "bad"}">
          <span class="net-label">RCON</span>
          <span class="net-value">${data.rcon_online ? "Online" : "Offline"}</span>
        </div>
        <div class="net-stat ${data.ftp_ok ? "ok" : "bad"}">
          <span class="net-label">FTP</span>
          <span class="net-value">${data.ftp_ok ? "OK" : "Fail"}</span>
        </div>
        <div class="net-stat">
          <span class="net-label">Players</span>
          <span class="net-value" id="net-players">—</span>
        </div>
        <div class="net-stat">
          <span class="net-label">Checked</span>
          <span class="net-value">${escapeHtml(data.checked_at || "")}</span>
        </div>
      </div>
      <div class="net-cards">
        ${rows.map(([label, probe, appOk]) => renderNetCard(label, probe, appOk)).join("")}
      </div>
      <div class="net-details muted">
        <p>Host: <code>${escapeHtml(data.rcon_host)}</code></p>
        <p>Game UDPPort <code>:${escapeHtml(String(gamePort ?? "—"))}</code> — не мониторится (${escapeHtml(unmonitoredNote)})</p>
        ${data.rcon_error ? `<p class="err">RCON: ${escapeHtml(data.rcon_error)}</p>` : ""}
        ${data.ftp_error ? `<p class="err">FTP: ${escapeHtml(data.ftp_error)}</p>` : ""}
      </div>`;
    const status = await api("/api/status").catch(() => null);
    if (status) $("#net-players").textContent = `${status.players_online}/${status.max_players}`;
  } catch (e) {
    el.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
  }
}

function renderNetCard(label, probe, appOk) {
  if (!probe) return "";
  const ok = probe.reachable;
  const proto = probe.protocol ? probe.protocol.toUpperCase() : "TCP";
  let foot = "";
  if (label === "RCON" || label === "FTP") {
    if (appOk !== undefined) {
      foot = `<div class="net-card-foot">${appOk ? "App layer OK" : "App layer fail"}</div>`;
    }
  } else if (label === "Query" && ok) {
    foot = `<div class="net-card-foot">Steam A2S OK</div>`;
  }
  return `
    <div class="net-card ${ok ? "ok" : "bad"}">
      <div class="net-card-head">${label} :${probe.port} <span class="muted">(${proto})</span></div>
      <div class="net-card-body">
        <span class="net-dot ${ok ? "on" : "off"}"></span>
        ${ok ? `${probe.latency_ms} ms` : escapeHtml(probe.error || probe.detail || "unreachable")}
      </div>
      ${foot}
    </div>`;
}

function renderModRow(item, liveMods, liveWs) {
  const onServer = liveMods.includes(item.id) || (item.workshop_id && liveWs.includes(item.workshop_id));
  return `
    <div class="mod-row">
      <div>
        <div class="player-name">${escapeHtml(item.name || item.id)}
          <span class="task-badge ${item.kind === "library" ? "inactive" : "active"}">${escapeHtml(item.kind)}</span>
        </div>
        <div class="player-id">${escapeHtml(item.id)}${item.workshop_id ? " · WS " + escapeHtml(item.workshop_id) : ""} · ${escapeHtml(item.source || "")}${item.path ? " · " + escapeHtml(item.path) : ""}</div>
      </div>
      <div class="player-actions">
        <span class="task-badge ${onServer ? "active" : "inactive"}">${onServer ? "В INI" : "НЕ В INI"}</span>
        <button type="button" class="btn xs danger" data-del="${escapeHtml(item.id)}">Del</button>
      </div>
    </div>`;
}

async function loadMods() {
  const el = $("#mods-catalog");
  const live = $("#mods-live");
  try {
    const data = await api("/api/mods/catalog");
    const items = data.catalog?.items || [];
    const lm = data.live?.mods || [];
    const lw = data.live?.workshop_ids || [];
    live.innerHTML = `Сервер ${escapeHtml(data.live?.ini || "world.ini")}: Mods ${lm.length} · Workshop ${lw.length}` +
      (lm.length ? `<br><code>${escapeHtml(lm.join("; "))}</code>` : "");
    if (!items.length) {
      el.innerHTML = '<p class="muted">Каталог пуст. Добавь мод или библиотеку справа.</p>';
      return;
    }
    el.innerHTML = items.map((i) => renderModRow(i, lm, lw)).join("");
    el.querySelectorAll("[data-del]").forEach((btn) => {
      btn.onclick = async () => {
        if (!confirm(`Убрать ${btn.dataset.del} из каталога?`)) return;
        try {
          await api(`/api/mods/catalog/${encodeURIComponent(btn.dataset.del)}`, { method: "DELETE" });
          loadMods();
          showToast("Удалено из каталога");
        } catch (e) {
          showToast(e.message, "err");
        }
      };
    });
  } catch (e) {
    el.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
  }
}

async function submitModAdd(e) {
  e.preventDefault();
  const body = {
    kind: $("#mod-kind").value,
    id: $("#mod-id").value.trim(),
    workshop_id: $("#mod-workshop").value.trim() || null,
    name: $("#mod-name").value.trim() || null,
    source: $("#mod-workshop").value.trim() ? "workshop" : "local",
    download: $("#mod-download").checked,
  };
  try {
    await api("/api/mods/catalog", { method: "POST", body: JSON.stringify(body) });
    showToast("Добавлено в каталог");
    loadMods();
  } catch (err) {
    showToast(err.message, "err");
  }
}

async function scaffoldMod() {
  const id = $("#mod-id").value.trim();
  if (!id) { showToast("Укажи Mod ID", "err"); return; }
  try {
    await api("/api/mods/scaffold", {
      method: "POST",
      body: JSON.stringify({ id, name: $("#mod-name").value.trim() || id, kind: $("#mod-kind").value }),
    });
    showToast(`Скелет src/mods/${id}`);
    loadMods();
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function applyModsIni() {
  if (!confirm("Перезаписать Mods= и WorkshopItems= в world.ini на FTP?")) return;
  try {
    const data = await api("/api/mods/apply-ini", { method: "POST" });
    showToast(`INI обновлён · backup ${data.backup}`);
    loadMods();
  } catch (e) {
    if (e.detail && e.detail.reason === "host_panel_wins") {
      showToast(e.detail.message || "world.ini на хосте изменился — Apply отменён", "warn");
      const remote = e.detail.remote_content;
      const name = e.detail.filename;
      if (remote != null && name && state.tabs.has(name)) {
        const tab = state.tabs.get(name);
        tab.content = remote;
        tab.original = remote;
        tab.dirty = false;
        if (state.editor && state.activeTab === name) {
          state.applyingEditor = true;
          state.editor.setValue(remote);
          state.applyingEditor = false;
        }
        renderTabs();
      }
    } else {
      showToast(e.message, "err");
    }
  }
}

function renderWorkshopTable(items) {
  const el = $("#ws-table");
  if (!el) return;
  if (!items || !items.length) {
    el.innerHTML = `<p class="muted">${escapeHtml(t("workshop.empty") || "Нет WorkshopItems — сначала Pull зеркала / world.ini")}</p>`;
    return;
  }
  el.innerHTML = `
    <table class="ws-table">
      <thead>
        <tr>
          <th>Workshop ID</th>
          <th data-i18n="workshop.col_title">Title</th>
          <th>Local</th>
          <th>Steam</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        ${items.map((item) => {
          const badge = item.update_available
            ? `<span class="ws-badge update">${escapeHtml(t("workshop.update") || "UPDATE")}</span>`
            : (item.installed
              ? `<span class="ws-badge ok">OK</span>`
              : `<span class="ws-badge missing">${escapeHtml(t("workshop.missing") || "нет")}</span>`);
          return `<tr>
            <td class="mono">${escapeHtml(item.workshop_id || "")}</td>
            <td>${escapeHtml(item.title || (item.mod_ids || []).join(", ") || "—")}</td>
            <td class="mono">${escapeHtml(item.local_mtime || "—")}</td>
            <td class="mono">${escapeHtml(item.remote_updated_iso || (item.remote_updated ? String(item.remote_updated) : "—"))}</td>
            <td>${badge}</td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>`;
}

function renderWorkshopPicker(mods) {
  const el = $("#ws-mod-picker");
  if (!el) return;
  if (!mods || !mods.length) {
    el.innerHTML = `<p class="muted">${escapeHtml(t("workshop.no_local_mods") || "Локальных модов нет — скачайте Workshop")}</p>`;
    return;
  }
  el.innerHTML = mods.map((m) => `
    <label class="ws-pick-row">
      <input type="checkbox" class="ws-mod-check" value="${escapeHtml(m.id)}" />
      <span><strong>${escapeHtml(m.id)}</strong> · ${escapeHtml(m.name || "")}${m.workshop_id ? " · WS " + escapeHtml(m.workshop_id) : ""}</span>
    </label>`).join("");
}

function selectedWorkshopModIds() {
  return [...document.querySelectorAll(".ws-mod-check:checked")].map((el) => el.value);
}

function setWorkshopDownloadStatus(text, ok) {
  const el = $("#ws-download-status");
  if (!el) return;
  el.textContent = text || "";
  el.className = `muted workshop-status ${ok === false ? "err" : ok ? "ok" : ""}`;
}

function renderSteamcmdBanner(steamcmd) {
  const banner = $("#ws-steamcmd-banner");
  const statusEl = $("#ws-steamcmd-status");
  const progress = $("#ws-steamcmd-progress");
  const installBtn = $("#btn-ws-steamcmd-install");
  const sc = steamcmd || {};
  const install = sc.install || {};
  if (banner) {
    banner.classList.toggle("hidden", !!sc.installed);
  }
  if (installBtn) installBtn.disabled = !!install.running;
  if (progress) {
    if (install.running) {
      progress.classList.remove("hidden");
      progress.innerHTML = progressBar(install.percent || 0, install.message || install.phase || "");
    } else {
      progress.classList.add("hidden");
      progress.innerHTML = "";
    }
  }
  if (statusEl) {
    if (sc.installed) {
      statusEl.textContent = `${t("workshop.steamcmd_ready") || "SteamCMD"}: ${sc.path || ""}${sc.version_hint ? ` · ${sc.version_hint}` : ""}`;
      statusEl.className = "muted workshop-status ok";
    } else if (install.phase === "error") {
      statusEl.textContent = install.message || "SteamCMD install failed";
      statusEl.className = "muted workshop-status err";
    } else if (install.running) {
      statusEl.textContent = install.message || t("workshop.steamcmd_installing") || "Installing SteamCMD…";
      statusEl.className = "muted workshop-status";
    } else {
      statusEl.textContent = t("workshop.steamcmd_missing") || "SteamCMD not found";
      statusEl.className = "muted workshop-status err";
    }
  }
}

async function pollSteamcmdInstall() {
  try {
    const install = await api("/api/workshop/steamcmd/install/status");
    renderSteamcmdBanner({ installed: false, install });
    if (!install.running) {
      state.wsSteamcmdPoll = false;
      loadWorkshop();
      if (install.phase === "done") showToast(t("workshop.steamcmd_done") || "SteamCMD installed", "ok");
      if (install.phase === "error") showToast(install.message || "SteamCMD install failed", "err");
    }
  } catch {
    state.wsSteamcmdPoll = false;
  }
}

async function installSteamcmd() {
  try {
    const data = await api("/api/workshop/steamcmd/install", { method: "POST", body: "{}" });
    if (data.skipped) {
      showToast(data.message || t("workshop.steamcmd_ready") || "SteamCMD ready", "ok");
      loadWorkshop();
      return;
    }
    state.wsSteamcmdPoll = true;
    renderSteamcmdBanner({ installed: false, install: data.status || { running: true, phase: "starting" } });
    showToast(t("workshop.steamcmd_installing") || "Installing SteamCMD…");
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function loadWorkshop() {
  try {
    const data = await api("/api/workshop/status");
    state.workshop = data;
    renderWorkshopTable(data.items || []);
    renderWorkshopPicker(data.available_mods || []);
    const auto = $("#chk-ws-auto-restart");
    if (auto) auto.checked = !!(data.monitor && data.monitor.auto_restart);
    const dl = data.download || {};
    renderSteamcmdBanner(data.steamcmd || {});
    const deployCb = $("#ws-deploy-server");
    const active = (state.servers || []).find((s) => s.id === state.serversActive);
    const remoteFiles = active && active.files && active.files.kind !== "local";
    if (deployCb) {
      deployCb.disabled = !remoteFiles;
      if (!remoteFiles) deployCb.checked = false;
    }
    if (dl.running) {
      state.wsDownloadPoll = true;
      setWorkshopDownloadStatus(`${dl.phase || "…"} · ${dl.percent || 0}% · ${dl.message || ""}`);
    } else if (dl.phase && dl.phase !== "idle") {
      setWorkshopDownloadStatus(`${dl.phase}: ${dl.message || ""}`, dl.phase !== "error");
    } else {
      setWorkshopDownloadStatus(data.ini_path ? `INI: ${data.ini_path}` : "");
    }
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function pollWorkshopDownload() {
  try {
    const dl = await api("/api/workshop/download/status");
    setWorkshopDownloadStatus(`${dl.phase || "…"} · ${dl.percent || 0}% · ${dl.message || ""}`, dl.phase === "error" ? false : undefined);
    if (!dl.running) {
      state.wsDownloadPoll = false;
      loadWorkshop();
      if (dl.phase === "done") showToast(t("workshop.download_done") || "Workshop download complete");
      if (dl.phase === "error") showToast(dl.message || "download error", "err");
    }
  } catch {
    state.wsDownloadPoll = false;
  }
}

async function startWorkshopDownload() {
  try {
    const data = await api("/api/workshop/download", {
      method: "POST",
      body: JSON.stringify({ missing_only: true }),
    });
    if (data.skipped) {
      showToast(data.message || "nothing to download");
      return;
    }
    state.wsDownloadPoll = true;
    setWorkshopDownloadStatus("starting…");
    showToast((t("workshop.download_started") || "SteamCMD started") + ` · ${(data.workshop_ids || []).length}`);
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function checkWorkshopUpdates() {
  try {
    const data = await api("/api/workshop/check-updates", { method: "POST", body: "{}" });
    renderWorkshopTable(data.items || []);
    const n = data.updates_available || 0;
    showToast(n ? `${n} update(s)` : (t("workshop.up_to_date") || "Up to date"), n ? "warn" : "ok");
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function setWorkshopAutoRestart(enabled) {
  try {
    await api("/api/workshop/auto-restart", {
      method: "POST",
      body: JSON.stringify({ enabled: !!enabled }),
    });
    showToast(enabled ? "Auto-restart ON" : "Auto-restart OFF");
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function startWorkshopGraceful() {
  if (!confirm(t("workshop.confirm_restart") || "RCON servermsg → save → quit через 3 минуты?")) return;
  try {
    await api("/api/workshop/graceful-restart", {
      method: "POST",
      body: JSON.stringify({ minutes: 3 }),
    });
    showToast("Graceful restart started");
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function analyzeWorkshopPack() {
  const modIds = selectedWorkshopModIds();
  const log = $("#ws-compile-log");
  try {
    const data = await api("/api/workshop/analyze", {
      method: "POST",
      body: JSON.stringify({ mod_ids: modIds }),
    });
    const lines = [
      `Mods: ${data.count}`,
      ...(data.conflicts || []).map((c) => `[${c.kind}] ${c.message}${c.mod_b ? " <-> " + c.mod_b : ""}`),
    ];
    if (!(data.conflicts || []).length) lines.push("No conflicts detected.");
    if (log) log.textContent = lines.join("\n");
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function compileWorkshopPack(e) {
  if (e && e.preventDefault) e.preventDefault();
  const modIds = selectedWorkshopModIds();
  const packId = $("#ws-pack-id")?.value.trim();
  const packName = $("#ws-pack-name")?.value.trim() || packId;
  const log = $("#ws-compile-log");
  try {
    const data = await api("/api/workshop/compile", {
      method: "POST",
      body: JSON.stringify({
        mod_ids: modIds,
        pack_id: packId,
        pack_name: packName,
        fail_on_conflict: !!$("#ws-fail-conflict")?.checked,
        deploy_to_server: !!$("#ws-deploy-server")?.checked,
        update_ini: !!$("#ws-update-ini")?.checked,
      }),
    });
    const lines = [
      ...(data.log || []),
      `output: ${data.output_dir || ""}`,
      ...(data.deploy ? [`deploy: ${data.deploy.remote_mod_dir || ""}`, `uploaded: ${(data.deploy.uploaded || []).length}`] : []),
      ...(data.conflicts || []).map((c) => `[${c.kind}] ${c.message}`),
    ];
    if (log) log.textContent = lines.join("\n");
    const ok = data.ok && !data.deploy_error;
    showToast(
      data.deploy_error
        ? data.deploy_error
        : data.deploy
          ? `${t("workshop.deploy_done") || "Deployed"} ${packId}`
          : data.ok
            ? `Compiled ${packId}`
            : "Compile failed",
      ok ? "ok" : "err",
    );
    loadWorkshop();
  } catch (err) {
    showToast(err.message, "err");
    if (log) log.textContent = err.message;
  }
}

function progressBar(percent, label) {
  const pct = Math.max(0, Math.min(100, Number(percent) || 0));
  return `
    <div class="progress-wrap">
      <div class="progress-meta">
        <span>${escapeHtml(label || "")}</span>
        <span>${pct}%</span>
      </div>
      <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
    </div>`;
}

function worldStageClass(stage) {
  if (stage === "ready") return "ok";
  if (stage === "failed") return "bad";
  if (stage && stage !== "idle" && stage !== "stopped") return "warn";
  return "";
}

function renderIssueList(items, extraClass) {
  if (!items || !items.length) return "";
  return `<ul class="world-errors ${extraClass || ""}">${items.map((l) => `<li>${escapeHtml(l)}</li>`).join("")}</ul>`;
}

function renderWorldCard(title, world, extra) {
  if (!world) {
    return `<div class="net-card"><div class="net-card-head">${title}</div><div class="muted">Нет данных — ещё не было запуска или нет лога</div></div>`;
  }
  const cls = worldStageClass(world.stage);
  const tail = (world.log_tail || []).slice(-40).map((l) => escapeHtml(l)).join("\n");
  const errors = world.errors || [];
  const warnings = world.warnings || [];
  const meta = extra || {};
  return `
    <div class="net-card ${cls}">
      <div class="net-card-head">${title}${world.version ? ` <span class="muted">${escapeHtml(world.version)}</span>` : ""}</div>
      <div class="net-card-body">
        <span class="net-dot ${cls === "ok" ? "on" : cls === "bad" ? "off" : "warn"}"></span>
        ${escapeHtml(world.label || world.stage || "—")}
        ${meta.pid ? `<span class="muted">PID ${escapeHtml(String(meta.pid))}</span>` : ""}
      </div>
      ${world.source ? `<div class="net-card-foot">${escapeHtml(world.source)}</div>` : ""}
      ${errors.length ? `<div class="world-subhead">Ошибки (${errors.length})</div>${renderIssueList(errors)}` : `<div class="world-subhead">Ошибки</div><p class="muted">нет</p>`}
      ${warnings.length ? `<div class="world-subhead">Предупреждения модов (${warnings.length})</div>${renderIssueList(warnings, "warn-list")}` : ""}
      <div class="world-subhead">Лог старта</div>
      ${tail ? `<pre class="world-tail">${tail}</pre>` : `<p class="muted">Лог ещё не появился</p>`}
    </div>`;
}

async function loadMirror() {
  const el = $("#mirror-grid");
  try {
    const [mirror, local, world] = await Promise.all([
      api("/api/mirror/status"),
      api("/api/local-server"),
      api("/api/world/status").catch(() => ({})),
    ]);
    const mb = Math.round((mirror.bytes || 0) / 1024 / 1024);
    const p = mirror.progress || {};
    const pulling = !!mirror.pulling;
    const paused = !!mirror.paused || !!mirror.stale;
    const complete = !!mirror.complete;
    const verified = p.verified ?? p.done ?? mirror.verified_count ?? 0;
    const total = p.total || 0;
    const remaining = p.remaining ?? Math.max(0, total - verified);
    const unchanged = p.unchanged ?? mirror.last_unchanged ?? 0;
    const transferred = p.done ?? mirror.last_transferred ?? 0;
    const phaseLabel = {
      connecting: "Подключение к FTP…",
      scanning: "Сканирование дерева…",
      comparing: `Сверяю размеры ${verified} / ${total} · новых ${transferred} · без изменений ${unchanged}`,
      downloading: `Качаю только изменённые ${transferred} · пропуск ${unchanged}`,
      verifying: `Проверка MD5 ${verified} / ${total}`,
      paused: mirror.stale ? "Оборвано — нужен повторный Pull" : "Пауза — повреждённый файл",
      done: complete
        ? (transferred ? `Готово · скачано ${transferred}, без изменений ${unchanged}` : `Уже актуально · ${unchanged || verified} файлов`)
        : "Завершено с ошибками",
      error: "Ошибка",
      idle: "Pull не запущен",
    }[p.phase] || p.phase || "";
    const btn = $("#btn-mirror-pull");
    if (btn) btn.disabled = pulling;
    const verifyBtn = $("#btn-mirror-verify");
    if (verifyBtn) verifyBtn.disabled = pulling;
    const startBtn = $("#btn-local-start");
    if (startBtn) startBtn.disabled = pulling || paused || !local.ready || !!local.running;

    const corrupt = mirror.corrupt;
    const staleBanner = mirror.stale
      ? `<div class="pause-banner">
          <strong>Прогресс завис — процесс pull мёртв.</strong>
          <p>${escapeHtml(mirror.last_error || "Панель перезапускалась, счётчик остался от старого качания.")}</p>
          <div class="player-actions">
            <button type="button" class="btn sm primary" id="btn-mirror-retry">Продолжить / докачать</button>
          </div>
        </div>`
      : "";
    const pauseBanner = (paused && corrupt && !mirror.stale)
      ? `<div class="pause-banner">
          <strong>Загрузка на паузе.</strong> Файл повреждён и не сохранён в зеркало.
          <p><code>${escapeHtml(corrupt.remote || "")}</code></p>
          <p class="err">${escapeHtml(corrupt.reason || "")}</p>
          <div class="player-actions">
            <button type="button" class="btn sm primary" id="btn-mirror-retry">Перекачать этот файл</button>
            <button type="button" class="btn sm ghost" id="btn-mirror-abort">Прервать</button>
          </div>
        </div>`
      : "";

    el.innerHTML = `
      <div class="net-summary">
        <div class="net-stat ${complete ? "ok" : ""}">
          <span class="net-label">Проверено MD5</span>
          <span class="net-value">${verified}/${total || "—"}</span>
        </div>
        <div class="net-stat ${pulling ? "ok" : paused ? "bad" : ""}">
          <span class="net-label">Статус pull</span>
          <span class="net-value">${pulling ? "Качает" : paused ? "Пауза" : complete ? "Полный" : "—"}</span>
        </div>
        <div class="net-stat">
          <span class="net-label">Размер</span>
          <span class="net-value">${mb} MB</span>
        </div>
        <div class="net-stat ${worldStageClass((world.local && world.local.stage) || (local.running ? "starting" : "idle"))}">
          <span class="net-label">Local process</span>
          <span class="net-value">${local.running ? `Running${local.pid ? " · " + local.pid : ""}` : "Stopped"}</span>
        </div>
      </div>
      ${progressBar(p.percent || 0, phaseLabel)}
      ${p.current && (pulling || paused) ? `<p class="muted pull-current">Текущий файл: <code>${escapeHtml(p.current)}</code>${p.last_md5 ? " · MD5 " + escapeHtml(p.last_md5.slice(0, 12)) + "…" : ""}</p>` : ""}
      ${staleBanner}
      ${pauseBanner}
      <div class="net-cards world-cards">
        ${renderWorldCard("Start World (хост)", world.remote)}
        ${renderWorldCard("Start World (локально)", (local.world || world.local), { pid: local.pid })}
      </div>
      <div class="net-details muted">
        <p>Качает: ${pulling ? "да" : "нет"} · Скачано новых: ${mirror.last_transferred ?? transferred} · Без изменений: ${mirror.last_unchanged ?? unchanged} · Осталось: ${remaining} · Ошибок: ${p.errors || 0}</p>
        <p>Mirror: <code>${escapeHtml(mirror.path || "")}</code></p>
        <p>Last pull: ${escapeHtml(mirror.last_pull || "никогда")} ${mirror.last_error && !paused ? `<span class="err">${escapeHtml(mirror.last_error)}</span>` : ""}</p>
        <p>Dedicated: <code>${escapeHtml(local.dedicated_dir || "—")}</code> · ${escapeHtml(local.kind_label || local.kind || "—")}${local.version ? " · " + escapeHtml(local.version) : ""}</p>
        <p>Launcher: <code>${escapeHtml(local.java || local.launcher || "—")}</code></p>
        <p>Cache (-cachedir): <code>${escapeHtml(local.cache_dir || "—")}</code></p>
        ${local.hint ? `<p>${escapeHtml(local.hint)}</p>` : ""}
      </div>`;

    maybeNotifyWorld("remote", world.remote);
    maybeNotifyWorld("local", local.world || world.local);

    const retry = $("#btn-mirror-retry");
    if (retry) retry.onclick = () => (mirror.stale ? pullMirror() : resumeMirror(true));
    const abortBtn = $("#btn-mirror-abort");
    if (abortBtn) abortBtn.onclick = () => abortMirror();

    const busy = pulling || (local.running && world.local && !world.local.ready && !world.local.failed);
    if (busy && state.activeView === "mirror") {
      clearTimeout(loadMirror._t);
      loadMirror._t = setTimeout(loadMirror, 900);
    }
  } catch (e) {
    el.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
  }
}

async function pullMirror() {
  try {
    await api("/api/mirror/pull", { method: "POST", body: JSON.stringify({ remote: "/ServerWorld", mode: "incremental" }) });
    showToast("Pull: качаю только новые или изменённые по размеру");
    loadMirror();
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function verifyMirror() {
  try {
    await api("/api/mirror/verify", { method: "POST" });
    showToast("Проверка сумм: размер + локальный MD5, без повторной качки");
    loadMirror();
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function loadPrefs() {
  try {
    const prefs = await api("/api/prefs");
    const box = $("#chk-host-wins");
    if (box) box.checked = prefs.host_panel_wins !== false;
  } catch {
    /* ignore */
  }
}

async function setHostWins(on) {
  try {
    await api("/api/prefs", { method: "POST", body: JSON.stringify({ host_panel_wins: !!on }) });
    showToast(on ? "Правки XLGAMES важнее наших" : "Наша панель может перезаписывать хост");
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function resumeMirror(retryCorrupt) {
  try {
    await api("/api/mirror/resume", { method: "POST", body: JSON.stringify({ retry_corrupt: !!retryCorrupt }) });
    showToast("Перекачка повреждённого файла…");
    loadMirror();
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function abortMirror() {
  try {
    await api("/api/mirror/abort", { method: "POST" });
    showToast("Pull прерван", "err");
    loadMirror();
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function startLocal() {
  try {
    const data = await api("/api/local-server/start", { method: "POST" });
    showToast(data.message || `Локальный дедик стартует · PID ${data.pid}`);
    loadMirror();
  } catch (e) {
    showToast(e.message, "err");
  }
}

async function stopLocal() {
  try {
    await api("/api/local-server/stop", { method: "POST" });
    showToast("Local server stopped");
    loadMirror();
  } catch (e) {
    showToast(e.message, "err");
  }
}

function initTheme() {
  document.documentElement.setAttribute("data-theme", localStorage.getItem("mb-theme") || "dark");
}

function toggleTheme() {
  const next = document.documentElement.getAttribute("data-theme") === "oled" ? "dark" : "oled";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("mb-theme", next);
  showToast(next === "oled" ? "OLED mode" : "Dark mode");
}

/* —— Bindings —— */
$("#btn-save").onclick = saveActiveTab;
$("#btn-sync-ftp").onclick = () =>
  loadConfigs(true).then(() => showToast("FTP refreshed")).catch((e) => showToast(e.message, "err"));
$("#btn-theme").onclick = toggleTheme;
$("#btn-clear-console").onclick = clearConsole;
$("#btn-download-log").onclick = downloadLog;
$("#autoscroll-lock").onchange = (e) => { state.autoscroll = e.target.checked; };
$("#console-form").onsubmit = (e) => {
  e.preventDefault();
  sendRcon(consoleInput.value);
  consoleInput.value = "";
};
consoleInput.addEventListener("keydown", (e) => {
  if (e.key === "ArrowUp") {
    e.preventDefault();
    if (!state.commandHistory.length) return;
    state.historyIndex = Math.min(state.historyIndex + 1, state.commandHistory.length - 1);
    consoleInput.value = state.commandHistory[state.historyIndex];
  }
  if (e.key === "ArrowDown") {
    e.preventDefault();
    if (state.historyIndex <= 0) { state.historyIndex = -1; consoleInput.value = ""; return; }
    state.historyIndex -= 1;
    consoleInput.value = state.commandHistory[state.historyIndex];
  }
});
document.querySelectorAll("[data-cmd]").forEach((btn) => { btn.onclick = () => quickAction(btn.dataset.cmd); });
$("#btn-graceful").onclick = () => quickAction("graceful");
document.querySelector("[data-action=mods]").onclick = () => quickAction("mods");
$("#btn-players-refresh").onclick = () => { loadPlayers(); loadLaunch(); };
$("#btn-npc-refresh").onclick = () => loadSlots();
$("#slots-form").onsubmit = submitSlots;
const slotsFive = $("#btn-slots-five");
if (slotsFive) {
  slotsFive.onclick = () => {
    $("#slots-count").value = "5";
    submitSlots({ preventDefault() {} });
  };
}
$("#btn-invite-copy").onclick = () => copyInvite(false);
$("#btn-invite-copy-pwd").onclick = () => copyInvite(true);
$("#founder-form").onsubmit = submitFounder;
$("#adduser-form").onsubmit = submitAddUser;
$("#announce-form").onsubmit = submitAnnounce;
$("#btn-new-task").onclick = () => openTaskModal();
$("#btn-task-close").onclick = closeTaskModal;
$("#btn-task-cancel").onclick = closeTaskModal;
$("#task-form").onsubmit = saveTaskForm;
$("#task-preset").onchange = (e) => {
  const cmd = PRESET_COMMANDS[e.target.value];
  if (cmd) $("#task-command").value = cmd;
};
$("#task-modal").onclick = (e) => { if (e.target === $("#task-modal")) closeTaskModal(); };
$("#btn-home-refresh").onclick = () => loadHome();
{
  const snapBtn = $("#btn-panel-snapshot");
  if (snapBtn) snapBtn.onclick = () => createPanelSnapshot();
}
$("#btn-home-save").onclick = () => sendRcon("save");
$("#btn-home-graceful").onclick = () => quickAction("graceful");
$("#btn-home-hard").onclick = () => hardRestart();
$("#btn-home-local-start").onclick = () => startLocal();
$("#btn-home-local-stop").onclick = () => stopLocal();
const serverSwitcher = $("#server-switcher");
if (serverSwitcher) {
  serverSwitcher.onchange = () => switchServer(serverSwitcher.value);
}
$("#srv-hoster").onchange = applyHosterPreset;
$("#srv-files-kind").onchange = toggleServerFormKind;
$("#btn-srv-probe-rcon").onclick = probeServerRcon;
$("#btn-srv-probe-files").onclick = probeServerFiles;
$("#btn-srv-probe-query").onclick = probeServerQuery;
$("#btn-srv-probe-all").onclick = probeServerAll;
$("#srv-process").onchange = renderWizardCaps;
$("#server-form").onsubmit = (e) => submitServerForm(e, { draft: false });
$("#btn-srv-save-draft").onclick = (e) => submitServerForm(e, { draft: true });
$("#btn-profile-edit").onclick = () => editActiveProfile();
$("#btn-profile-delete").onclick = () => deleteActiveProfile();
$("#btn-onboarding-go").onclick = () => {
  $("#onboarding-modal")?.classList.add("hidden");
  openVpsSetupModal();
};
$("#vps-setup-form").onsubmit = submitVpsSetup;
$("#vps-setup-back").onclick = closeVpsSetupModal;
$("#mobile-server-picker").onclick = (e) => {
  e.stopPropagation();
  toggleServerPickerPopover();
};
$("#btn-bottom-add-server").onclick = () => openVpsSetupModal();
document.addEventListener("click", (e) => {
  const pop = $("#server-picker-popover");
  const picker = $("#mobile-server-picker");
  if (!pop || pop.classList.contains("hidden")) return;
  if (pop.contains(e.target) || picker?.contains(e.target)) return;
  pop.classList.add("hidden");
});
$("#vps-setup-modal")?.addEventListener("click", (e) => {
  if (e.target === $("#vps-setup-modal")) closeVpsSetupModal();
});
$("#btn-smoke-refresh").onclick = () => loadSmoke();
$("#btn-smoke-start").onclick = () => startSmoke();
$("#btn-smoke-stop").onclick = () => stopSmoke();
toggleServerFormKind();
document.querySelectorAll("[data-jump]").forEach((btn) => {
  btn.onclick = () => jumpView(btn.dataset.jump, btn.dataset.open);
});
$("#btn-bans-refresh").onclick = () => loadBans();
$("#btn-chat-refresh").onclick = () => loadChat();
$("#chat-channel").onchange = () => loadChat();
$("#chat-announce-form").onsubmit = submitChatAnnounce;
$("#btn-privates-refresh").onclick = () => loadPrivates();
$("#btn-wipe-preview").onclick = () => previewWipe();
$("#btn-city-wipe").onclick = () => triggerCityWipe();
$("#chk-hard-fs-wipe")?.addEventListener("change", (e) => {
  $("#hard-fs-wipe-panel")?.classList.toggle("hidden", !e.target.checked);
});
$("#btn-log-refresh").onclick = () => loadServerLog();
$("#log-kind").onchange = () => loadServerLog();
$("#btn-log-download").onclick = () => downloadText(state.serverLogContent, `${state.logKind || "log"}_${ts()}.txt`);
$("#log-autorefresh").onchange = (e) => { state.logAutoRefresh = e.target.checked; };
$("#btn-network-refresh").onclick = () => loadNetwork();
$("#btn-mods-refresh").onclick = () => loadMods();
$("#btn-mods-apply").onclick = () => applyModsIni();
$("#mod-add-form").onsubmit = submitModAdd;
$("#btn-mod-scaffold").onclick = () => scaffoldMod();
$("#btn-ws-refresh").onclick = () => loadWorkshop();
$("#btn-ws-download").onclick = () => startWorkshopDownload();
$("#btn-ws-steamcmd-install").onclick = () => installSteamcmd();
$("#btn-ws-check").onclick = () => checkWorkshopUpdates();
$("#btn-ws-graceful").onclick = () => startWorkshopGraceful();
$("#btn-ws-analyze").onclick = () => analyzeWorkshopPack();
$("#ws-compile-form").onsubmit = compileWorkshopPack;
$("#chk-ws-auto-restart").onchange = (e) => setWorkshopAutoRestart(e.target.checked);
$("#btn-mirror-pull").onclick = () => pullMirror();
$("#btn-mirror-verify").onclick = () => verifyMirror();
const hostWinsBox = $("#chk-host-wins");
if (hostWinsBox) hostWinsBox.onchange = (e) => setHostWins(e.target.checked);
$("#btn-local-start").onclick = () => startLocal();
$("#btn-local-stop").onclick = () => stopLocal();

setInterval(() => {
  if (state.ws?.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify({ type: "ping" }));
  if (state.eventWs?.readyState === WebSocket.OPEN) state.eventWs.send(JSON.stringify({ type: "ping" }));
  if (!eventWsConnected()) {
    if (state.logAutoRefresh && state.activeView === "logs") loadServerLog();
    pollStatus();
  }
}, 15000);
setInterval(tickUptime, 1000);

initTheme();
initEditor();
initNavigation();
$("#auth-form").onsubmit = submitAuthForm;
$("#auth-local-btn").onclick = () => enterLocalAuth();
$("#btn-logout").onclick = () => logoutUser();

initI18n().then(() => initAuth()).catch((e) => {
  console.error(e);
  initAuth();
});
