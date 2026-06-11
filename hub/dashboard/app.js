const STATUS_INTERVAL_MS = 15000;
const NEWS_INTERVAL_MS = 5 * 60 * 1000;

let registry = { hub_name: "Mission Control", modules: [] };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

function renderModules(statusById) {
  const container = document.getElementById("modules");
  container.innerHTML = "";

  for (const mod of registry.modules) {
    const status = statusById[mod.id];
    const state = status ? status.state : "unknown";

    const card = el("div", "module-card");

    const head = el("div", "module-head");
    head.appendChild(el("span", "module-name", mod.name));
    head.appendChild(el("span", `dot ${state}`));
    card.appendChild(head);

    card.appendChild(el("div", "module-tagline", mod.tagline));
    card.appendChild(el("div", "module-desc", mod.description));

    if (status) {
      for (const svc of status.services) {
        const row = el("div", "service-row");
        row.appendChild(el("span", null, svc.name));
        row.appendChild(
          el(
            "span",
            svc.online ? "up" : "down",
            svc.online ? `UP ${svc.latency_ms}ms` : "DOWN"
          )
        );
        card.appendChild(row);
      }
    }

    const tags = el("div", "tags");
    for (const tag of mod.tags || []) tags.appendChild(el("span", "tag", tag));
    card.appendChild(tags);

    const actions = el("div", "module-actions");
    const open = el("a", "btn", "OPEN");
    open.href = mod.url;
    open.target = "_blank";
    actions.appendChild(open);
    if (mod.repo) {
      const repo = el("a", "btn secondary", "REPO");
      repo.href = mod.repo;
      repo.target = "_blank";
      actions.appendChild(repo);
    }
    card.appendChild(actions);

    container.appendChild(card);
  }
}

function renderOverall(statuses) {
  const pill = document.getElementById("overall-status");
  const states = statuses.map((s) => s.state);
  let overall = "offline";
  if (states.every((s) => s === "online")) overall = "online";
  else if (states.some((s) => s !== "offline")) overall = "degraded";
  pill.textContent =
    overall === "online" ? "ALL SYSTEMS GO" : overall.toUpperCase();
  pill.className = `pill ${overall}`;
  document.getElementById("last-check").textContent =
    `last check ${new Date().toLocaleTimeString()}`;
}

async function refreshStatus() {
  try {
    const data = await fetchJson("/api/status");
    const byId = Object.fromEntries(data.modules.map((m) => [m.id, m]));
    renderModules(byId);
    renderOverall(data.modules);
  } catch {
    renderModules({});
  }
}

function timeAgo(ts) {
  if (!ts) return "";
  const minutes = Math.floor((Date.now() / 1000 - ts) / 60);
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h`;
  return `${Math.floor(minutes / 1440)}d`;
}

async function refreshNews() {
  const container = document.getElementById("news");
  try {
    const data = await fetchJson("/api/news");
    container.innerHTML = "";
    if (!data.items.length) {
      container.appendChild(el("p", "muted", "No feed items (check network/feeds in modules.json)."));
      return;
    }
    for (const item of data.items.slice(0, 40)) {
      const link = el("a", "news-item");
      link.href = item.link;
      link.target = "_blank";
      link.appendChild(el("div", "news-title", item.title));
      const meta = el("div", "news-meta");
      meta.appendChild(el("span", "src", item.source));
      meta.appendChild(el("span", null, ` · ${timeAgo(item.published)}`));
      link.appendChild(meta);
      container.appendChild(link);
    }
  } catch {
    container.innerHTML = "";
    container.appendChild(el("p", "muted", "Feed fetch failed."));
  }
}

function tickClock() {
  document.getElementById("clock").textContent =
    new Date().toLocaleTimeString([], { hour12: false });
}

async function init() {
  tickClock();
  setInterval(tickClock, 1000);

  try {
    const data = await fetchJson("/api/modules");
    registry = data;
    document.getElementById("hub-name").textContent =
      data.hub_name.toUpperCase();
  } catch {
    document.getElementById("modules").innerHTML =
      '<p class="muted">Gateway unreachable.</p>';
    return;
  }

  renderModules({});
  refreshStatus();
  refreshNews();
  setInterval(refreshStatus, STATUS_INTERVAL_MS);
  setInterval(refreshNews, NEWS_INTERVAL_MS);
}

init();
