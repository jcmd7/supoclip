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

let marketItems = [];

function renderMarkets() {
  const container = document.getElementById("markets");
  const needle = document.getElementById("market-search").value.toLowerCase();
  const items = marketItems.filter((m) =>
    m.question.toLowerCase().includes(needle)
  );
  container.innerHTML = "";
  if (!items.length) {
    container.appendChild(el("p", "muted", "No markets (check network)."));
    return;
  }
  for (const m of items.slice(0, 25)) {
    const link = el("a", "news-item market-row");
    link.href = m.url;
    link.target = "_blank";
    const q = el("div", "market-q");
    q.appendChild(el("div", "news-title", m.question));
    const meta = el("div", "news-meta");
    const tag = el("span", "src-tag", m.source);
    meta.appendChild(tag);
    meta.appendChild(
      el("span", null, ` $${Number(m.volume_24h).toLocaleString()} 24h`)
    );
    q.appendChild(meta);
    link.appendChild(q);
    const pctClass = m.yes_pct >= 70 ? "pct high" : m.yes_pct <= 30 ? "pct low" : "pct";
    const pctBox = el("div", "pct-box");
    pctBox.appendChild(el("span", pctClass, m.yes_pct !== null ? `${m.yes_pct}%` : "—"));
    if (m.delta_24h !== null && m.delta_24h !== undefined && m.delta_24h !== 0) {
      const up = m.delta_24h > 0;
      pctBox.appendChild(
        el("span", `delta ${up ? "up" : "down"}`,
           `${up ? "▲" : "▼"}${Math.abs(m.delta_24h)}`)
      );
    }
    link.appendChild(pctBox);
    container.appendChild(link);
  }
}

async function refreshMarkets() {
  try {
    const data = await fetchJson("/api/markets");
    marketItems = data.items;
    renderMarkets();
  } catch {
    marketItems = [];
    renderMarkets();
  }
}

async function refreshHN() {
  const container = document.getElementById("hn");
  try {
    const data = await fetchJson("/api/hn");
    container.innerHTML = "";
    if (!data.items.length) {
      container.appendChild(el("p", "muted", "No stories (check network)."));
      return;
    }
    for (const item of data.items) {
      const link = el("a", "news-item");
      link.href = item.url;
      link.target = "_blank";
      link.appendChild(el("div", "news-title", item.title));
      const meta = el("div", "news-meta");
      meta.appendChild(el("span", "src", `▲ ${item.points}`));
      const comments = el("a", null, ` · ${item.comments} comments`);
      comments.href = item.hn_url;
      comments.target = "_blank";
      comments.style.color = "inherit";
      meta.appendChild(comments);
      link.appendChild(meta);
      container.appendChild(link);
    }
  } catch {
    container.innerHTML = "";
    container.appendChild(el("p", "muted", "HN fetch failed."));
  }
}

async function refreshBrief() {
  try {
    const data = await fetchJson("/api/brief");
    document.getElementById("brief-headline").textContent = data.headline;
    const container = document.getElementById("brief-lines");
    container.innerHTML = "";
    for (const line of data.lines) {
      const node = line.url ? el("a", "brief-line") : el("span", "brief-line");
      if (line.url) {
        node.href = line.url;
        node.target = "_blank";
      }
      node.appendChild(el("span", "k", line.kind));
      node.appendChild(document.createTextNode(line.text));
      container.appendChild(node);
    }
  } catch {
    document.getElementById("brief-headline").textContent = "Briefing unavailable.";
  }
}

function openClip(file) {
  const modal = document.getElementById("clip-modal");
  const player = document.getElementById("clip-player");
  player.src = `/clips/${file}`;
  modal.classList.remove("hidden");
  player.play().catch(() => {});
}

async function refreshClips() {
  const container = document.getElementById("clips");
  try {
    const data = await fetchJson("/api/clips");
    document.getElementById("clip-count").textContent =
      data.items.length ? `${data.items.length} clips` : "";
    if (!data.items.length) return; // keep the empty-state hint
    container.innerHTML = "";
    for (const clip of data.items) {
      const card = el("div", "clip-card");
      card.addEventListener("click", () => openClip(clip.file));
      if (clip.poster) {
        const img = el("img", "clip-thumb");
        img.src = `/clips/${clip.poster}`;
        img.loading = "lazy";
        card.appendChild(img);
      } else {
        card.appendChild(el("div", "clip-thumb-blank", "▶"));
      }
      const info = el("div", "clip-info");
      info.appendChild(el("div", "clip-title", clip.title));
      const meta = el("div", "clip-meta");
      meta.appendChild(el("span", "virality", clip.virality != null ? `${clip.virality}` : ""));
      meta.appendChild(
        el("span", `pub-dot ${clip.published ? "yes" : "no"}`,
           clip.published ? "● live" : "○ draft")
      );
      info.appendChild(meta);
      card.appendChild(info);
      container.appendChild(card);
    }
  } catch {
    /* leave existing content */
  }
}

function eventAgo(ts) {
  const mins = Math.floor((Date.now() / 1000 - ts) / 60);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h`;
  return `${Math.floor(mins / 1440)}d`;
}

async function refreshEvents() {
  const container = document.getElementById("events");
  try {
    const data = await fetchJson("/api/events");
    if (!data.items.length) return; // keep idle hint
    container.innerHTML = "";
    for (const ev of data.items) {
      const node = ev.url ? el("a", "news-item event-item") : el("div", "news-item event-item");
      if (ev.url) {
        node.href = ev.url;
        node.target = "_blank";
      }
      if (ev.priority === "high") node.classList.add("event-high");
      const top = el("div", "news-title");
      top.appendChild(el("span", "event-kind", ev.title));
      top.appendChild(document.createTextNode(" " + ev.body));
      node.appendChild(top);
      node.appendChild(el("div", "news-meta", eventAgo(ev.ts)));
      container.appendChild(node);
    }
  } catch {
    /* leave idle hint */
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
  refreshMarkets();
  refreshHN();
  refreshBrief();
  refreshClips();
  refreshEvents();
  document.getElementById("market-search").addEventListener("input", renderMarkets);

  const modal = document.getElementById("clip-modal");
  const player = document.getElementById("clip-player");
  const closeModal = () => {
    modal.classList.add("hidden");
    player.pause();
    player.src = "";
  };
  document.getElementById("clip-close").addEventListener("click", closeModal);
  modal.querySelector(".modal-backdrop").addEventListener("click", closeModal);

  setInterval(refreshStatus, STATUS_INTERVAL_MS);
  setInterval(refreshNews, NEWS_INTERVAL_MS);
  setInterval(refreshMarkets, 60 * 1000);
  setInterval(refreshHN, 2 * 60 * 1000);
  setInterval(refreshBrief, 5 * 60 * 1000);
  setInterval(refreshClips, 60 * 1000);
  setInterval(refreshEvents, 30 * 1000);
}

init();
