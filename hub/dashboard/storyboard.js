// Storyboard Conceptor — staged UI over the gateway's /api/storyboard endpoints.
let project = null;

const $ = (id) => document.getElementById(id);
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.status);
  return res.json();
}
function setStatus(s) { $("sb-status").textContent = s; }

const TEXT_STAGES = { world: "// WORLD", ideas: "// IDEAS", script: "// SCRIPT" };
let currentStage = "settings";

function showPanel(name) {
  document.querySelectorAll(".sb-panel").forEach((p) =>
    p.classList.toggle("hidden", p.dataset.panel !== name));
}

function selectStage(stage) {
  currentStage = stage;
  document.querySelectorAll(".stage").forEach((s) =>
    s.classList.toggle("active", s.dataset.stage === stage));
  if (stage === "settings") return showPanel("settings");
  if (stage === "shots") { showPanel("shots"); return renderShots(); }
  // text stages
  showPanel("text");
  $("text-title").textContent = TEXT_STAGES[stage];
  const val = project ? project[stage] : "";
  $("stage-text").value = stage === "ideas"
    ? (Array.isArray(val) ? val.join("\n") : "")
    : (val || "");
}

function readSettings() {
  return {
    style: $("style").value, negative: $("negative").value,
    aspect: $("aspect").value, t2i_provider: $("t2i").value,
    i2v_provider: $("i2v").value,
  };
}

async function refreshProjects() {
  const data = await api("/api/storyboard/projects");
  const picker = $("project-picker");
  picker.innerHTML = '<option value="">— load project —</option>';
  for (const p of data.items) {
    const o = el("option", null, `${p.title} (${p.shots} shots)`);
    o.value = p.id;
    picker.appendChild(o);
  }
}

async function loadProject(id) {
  project = await api(`/api/storyboard/projects/${id}`);
  $("idea").value = project.idea;
  const s = project.settings;
  $("style").value = s.style; $("negative").value = s.negative;
  $("aspect").value = s.aspect; $("t2i").value = s.t2i_provider; $("i2v").value = s.i2v_provider;
  $("btn-export").href = `/api/storyboard/projects/${id}/export`;
  setStatus(project.title.toUpperCase());
  selectStage("world");
}

// ---- shots ----
function renderShots() {
  const grid = $("shots");
  grid.innerHTML = "";
  if (!project || !project.shots.length) {
    grid.appendChild(el("p", "muted", "No shots yet — GENERATE SHOT LIST."));
    return;
  }
  project.shots.forEach((shot, i) => {
    const card = el("div", "sb-shot");
    const head = el("div", "sb-shot-head");
    head.appendChild(el("span", "num", `SHOT ${String(i + 1).padStart(2, "0")}`));
    head.appendChild(el("span", null, shot.name));
    card.appendChild(head);

    if (shot.image) {
      const img = el("img", "sb-shot-img");
      img.src = `/storyboard-assets/${project.id}/assets/${shot.image}`;
      card.appendChild(img);
    } else {
      card.appendChild(el("div", "sb-shot-img placeholder", "no image — generate"));
    }

    const body = el("div", "sb-shot-body");
    const ctx = el("textarea");
    ctx.value = `${shot.shot_type}\n${shot.visible_context}`;
    ctx.dataset.shot = shot.id;
    body.appendChild(ctx);

    const actions = el("div", "sb-shot-actions");
    for (const [label, kind, primary] of [
      ["⟳ Image", "image", true], ["▶ I2V", "video", false],
      ["360°", "panorama", false], ["3×3 sheet", "sheet", false],
    ]) {
      const b = el("button", primary ? "primary" : null, label);
      b.addEventListener("click", () => generateShot(shot.id, kind, b));
      actions.appendChild(b);
    }
    body.appendChild(actions);
    card.appendChild(body);
    grid.appendChild(card);
  });
}

async function generateShot(shotId, kind, btn) {
  btn.textContent = "…"; setStatus(`GENERATING ${kind.toUpperCase()}`);
  try {
    const res = await api(
      `/api/storyboard/projects/${project.id}/shots/${shotId}/generate?kind=${kind}`,
      { method: "POST" });
    const idx = project.shots.findIndex((s) => s.id === shotId);
    project.shots[idx] = res.shot;
    renderShots();
    setStatus("IDLE");
  } catch (e) {
    setStatus("ERR");
    alert(`Generation failed: ${e.message}\n\nIs ComfyUI running (make gpu) with a workflow?`);
  }
}

async function saveShotEdits() {
  if (!project) return;
  document.querySelectorAll("[data-shot]").forEach((ta) => {
    const shot = project.shots.find((s) => s.id === ta.dataset.shot);
    if (shot) {
      const [type, ...rest] = ta.value.split("\n");
      shot.shot_type = type.trim();
      shot.visible_context = rest.join(" ").trim();
    }
  });
  project = await api(`/api/storyboard/projects/${project.id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ shots: project.shots }),
  });
}

// ---- wiring ----
function init() {
  // defaults
  $("style").value = "cinematic, dramatic low-key lighting, film grain, photorealistic";
  $("negative").value = "blurry, low quality, watermark, text, deformed";

  document.querySelectorAll(".stage").forEach((s) =>
    s.addEventListener("click", () => selectStage(s.dataset.stage)));

  $("btn-create").addEventListener("click", async () => {
    if (!$("idea").value.trim()) return alert("Write an idea first.");
    setStatus("CREATING");
    project = await api("/api/storyboard/projects", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idea: $("idea").value, settings: readSettings() }),
    });
    $("btn-export").href = `/api/storyboard/projects/${project.id}/export`;
    await refreshProjects();
    setStatus(project.title.toUpperCase());
    selectStage("world");
  });

  $("project-picker").addEventListener("change", (e) => {
    if (e.target.value) loadProject(e.target.value);
  });

  $("btn-generate-stage").addEventListener("click", async () => {
    if (!project) return alert("Create a project first.");
    setStatus(`GENERATING ${currentStage.toUpperCase()}`);
    try {
      project = await api(
        `/api/storyboard/projects/${project.id}/stage/${currentStage}`, { method: "POST" });
      selectStage(currentStage);
      setStatus("IDLE");
    } catch (e) { setStatus("ERR"); alert(`Stage failed: ${e.message}`); }
  });

  $("btn-save-stage").addEventListener("click", async () => {
    if (!project) return;
    const v = $("stage-text").value;
    const patch = currentStage === "ideas" ? { ideas: v.split("\n").filter(Boolean) } : { [currentStage]: v };
    project = await api(`/api/storyboard/projects/${project.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
    setStatus("SAVED");
  });

  $("btn-gen-shots").addEventListener("click", async () => {
    if (!project) return;
    setStatus("GENERATING SHOTS");
    try {
      project = await api(`/api/storyboard/projects/${project.id}/stage/shots`, { method: "POST" });
      renderShots(); setStatus("IDLE");
    } catch (e) { setStatus("ERR"); alert(`Shots failed: ${e.message}`); }
  });

  $("btn-gen-all").addEventListener("click", async () => {
    if (!project) return;
    await saveShotEdits();
    for (const shot of project.shots.filter((s) => !s.image)) {
      await generateShot(shot.id, "image", { textContent: "" });
    }
  });

  refreshProjects().catch(() => {});
  selectStage("settings");
}

init();
