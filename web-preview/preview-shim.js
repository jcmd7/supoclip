// Preview shim — makes the dashboard fully interactive on a static host
// (e.g. Vercel) with zero backend. Intercepts every /api/* fetch and returns
// bundled sample data, simulating stage-runs and generation client-side.
// Loaded before app.js / storyboard.js. Real hub ignores this file.
(function () {
  const now = Date.now() / 1000;

  const MODULES = [
    { id: "supoclip", name: "SupoClip", tagline: "AI video clipping", tags: ["content", "video", "ai"], url: "#", repo: "https://github.com/FujiwaraChoki/supoclip", description: "Turn long-form video into viral 9:16 clips.", services: [{ name: "frontend" }, { name: "api" }] },
    { id: "flowsint", name: "Flowsint", tagline: "Graph-based OSINT", tags: ["intel", "graph"], url: "#", description: "Visual entity-graph investigations.", services: [{ name: "frontend" }] },
    { id: "mirofish", name: "MiroFish", tagline: "Swarm prediction engine", tags: ["simulation"], url: "#", description: "Agent societies simulate how events unfold.", services: [{ name: "frontend" }, { name: "api" }] },
    { id: "changedetection", name: "changedetection.io", tagline: "Watch anything", tags: ["alerts"], url: "#", description: "Monitor pages/prices for changes.", services: [{ name: "app" }] },
    { id: "rsshub", name: "RSSHub", tagline: "RSS for everything", tags: ["feeds"], url: "#", description: "Feeds for sources without them.", services: [{ name: "app" }] },
    { id: "openbb", name: "OpenBB", tagline: "Open-source terminal", tags: ["markets"], url: "#", description: "Equities/crypto/macro research.", services: [{ name: "api" }] },
    { id: "comfyui", name: "ComfyUI", tagline: "Local video generation", tags: ["ai", "video"], url: "#", description: "Local Wan/LTX generation for /clip.", services: [{ name: "app" }] },
    { id: "ntfy", name: "ntfy", tagline: "Phone push", tags: ["alerts"], url: "#", description: "Watcher pushes alerts here.", services: [{ name: "server" }] },
    { id: "storyboard", name: "Storyboard", tagline: "Idea → film", tags: ["ai", "video"], url: "/storyboard.html", description: "Guided idea→world→script→shots pipeline.", services: [{ name: "tool" }] },
  ];

  const MARKETS = [
    { source: "polymarket", question: "Will the Fed cut rates in July 2026?", yes_pct: 72, volume_24h: 2845000, delta_24h: 9, url: "#" },
    { source: "kalshi", question: "June CPI above 3.0%?", yes_pct: 61, volume_24h: 1250000, delta_24h: -4, url: "#" },
    { source: "polymarket", question: "Will Bitcoin close above $150k in June?", yes_pct: 18, volume_24h: 1920000, delta_24h: 6, url: "#" },
    { source: "polymarket", question: "GPT-6 released before September 2026?", yes_pct: 41, volume_24h: 860500, delta_24h: 11, url: "#" },
  ];

  const HN = [
    { title: "Show HN: I built an open-source OpusClip alternative", points: 847, comments: 231, url: "#", hn_url: "#" },
    { title: "FFmpeg 7.0 adds native AI scene detection", points: 612, comments: 189, url: "#", hn_url: "#" },
    { title: "Why prediction markets keep beating polls", points: 445, comments: 302, url: "#", hn_url: "#" },
  ];

  const NEWS = HN.map((h) => ({ source: "Signal", title: h.title, link: "#", published: now - 3600 }));

  const EVENTS = [
    { id: "e1", kind: "market", title: "▲ 11pt move", body: "GPT-6 released before September 2026? → 41% (polymarket)", url: "#", priority: "high", ts: now - 600 },
    { id: "e2", kind: "market", title: "▲ 9pt move", body: "Will the Fed cut rates in July 2026? → 72% (polymarket)", url: "#", priority: "default", ts: now - 1800 },
    { id: "e3", kind: "hn", title: "HN 847↑", body: "Show HN: open-source OpusClip alternative (231 comments)", url: "#", priority: "default", ts: now - 5400 },
  ];

  const CLIPS = [
    { id: "c1", title: "THIS CHANGED EVERYTHING", file: "c1.mp4", poster: "c1.jpg", virality: 87, published: false },
    { id: "c2", title: "The one tip nobody tells you", file: "c2.mp4", poster: "c2.jpg", virality: 72, published: true },
    { id: "c3", title: "Wait until the end", file: "c3.mp4", poster: "c3.jpg", virality: 64, published: false },
  ];

  const PROJECT = {
    id: "demo", title: "A HEIST ON A MIDNIGHT FERRY", idea: "a heist on a midnight ferry",
    settings: { style: "cinematic, dramatic low-key lighting, film grain, photorealistic", negative: "blurry, low quality, watermark, text, deformed", aspect: "16:9", t2i_provider: "comfyui", i2v_provider: "comfyui" },
    world: "A rain-soaked 1990s river port. Sodium-orange light, VHS grain, anamorphic flares, perpetual drizzle.",
    ideas: ["arrival on the river road", "the empty ferry", "descent into the hold"],
    script: "Night. A car eases down the river road toward the dark ferry slip. Rain streaks the windshield...",
    shots: [
      { id: "s1", name: "river road", shot_type: "POV 24mm, shaky 90s low-light", visible_context: "a wet riverside road at night, headlights on tarmac", image: "s1_image.png", video: null, panorama: null, sheet: null, status: "generated" },
      { id: "s2", name: "ferry stop", shot_type: "wide first-person from stopped car", visible_context: "empty ferry slip ahead, rusted gantry, black water", image: null, video: null, panorama: null, sheet: null, status: "draft" },
    ],
  };

  const BRIEF = {
    headline: "Since yesterday: 3 market moves, 3 new clips.",
    lines: [
      { kind: "market", text: "GPT-6 release market moved up 11 pts to 41%", url: "#" },
      { kind: "hn", text: "HN: open-source OpusClip alternative (847 pts)", url: "#" },
      { kind: "clips", text: "3 clip(s) made in the last 24h, 1 published", url: null },
    ],
  };

  function json(data) {
    return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
  }

  const realFetch = window.fetch.bind(window);

  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : input.url;
    const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
    const method = (init && init.method) || "GET";

    // GET endpoints
    if (path === "/api/modules") return Promise.resolve(json({ hub_name: "Mission Control (preview)", modules: MODULES }));
    if (path === "/api/status") return Promise.resolve(json({ checked_at: now, modules: MODULES.map((m) => ({ id: m.id, state: "online", services: m.services.map((s) => ({ name: s.name, online: true, latency_ms: 40 + Math.floor(Math.random() * 30) })) })) }));
    if (path === "/api/markets") return Promise.resolve(json({ items: MARKETS }));
    if (path === "/api/hn") return Promise.resolve(json({ items: HN }));
    if (path === "/api/news") return Promise.resolve(json({ items: NEWS }));
    if (path === "/api/events") return Promise.resolve(json({ items: EVENTS }));
    if (path === "/api/clips") return Promise.resolve(json({ items: CLIPS }));
    if (path === "/api/brief") return Promise.resolve(json({ generated_at: now, headline: BRIEF.headline, lines: BRIEF.lines }));
    if (path === "/api/storyboard/projects" && method === "GET")
      return Promise.resolve(json({ items: [{ id: PROJECT.id, title: PROJECT.title, idea: PROJECT.idea, shots: PROJECT.shots.length, updated_at: now }] }));
    if (path.match(/^\/api\/storyboard\/projects\/[^/]+$/) && method === "GET")
      return Promise.resolve(json(PROJECT));

    // Simulated mutations
    if (path === "/api/storyboard/projects" && method === "POST")
      return Promise.resolve(json(PROJECT));
    if (path.match(/\/stage\/(world|ideas|script|shots)$/)) {
      return Promise.resolve(json(PROJECT)); // canned content already populated
    }
    if (path.match(/\/shots\/[^/]+\/generate$/)) {
      const shotId = path.split("/shots/")[1].split("/")[0];
      const kind = (url.split("kind=")[1] || "image").split("&")[0];
      const shot = PROJECT.shots.find((s) => s.id === shotId) || PROJECT.shots[0];
      shot[kind] = `${shotId}_${kind}.png`;
      shot.status = "generated";
      return Promise.resolve(json({ shot, prompt: { prompt: "(preview)", negative: "" } }));
    }
    if (path.match(/^\/api\/storyboard\/projects\/[^/]+$/) && method === "PATCH")
      return Promise.resolve(json(PROJECT));

    return realFetch(input, init);
  };

  // Preview banner
  window.addEventListener("DOMContentLoaded", function () {
    const b = document.createElement("div");
    b.textContent = "◷ PREVIEW — sample data. Live module health, alerts, history & real generation run when you self-host the hub.";
    b.style.cssText = "background:#1d2735;color:#35c9dd;font:12px/1.6 monospace;text-align:center;padding:6px;border-bottom:1px solid #35c9dd;letter-spacing:1px;";
    document.body.insertBefore(b, document.body.firstChild);
  });
})();
