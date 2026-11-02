"use strict";

/* THERMAL//DOTS - front-end.  All image work happens in Python; this file only
   collects controls, debounces previews and renders the returned 1-bit PNG. */

const DITHERS = [
  ["bayer4", "bayer 4×4", "crisp matrix · default"],
  ["bayer8", "bayer 8×8", "finer matrix"],
  ["atkinson", "atkinson", "blown highlights"],
  ["fs", "floyd–steinberg", "photographic"],
  ["halftone", "halftone", "newsprint dots"],
  ["mean", "threshold", "auto / line art"],
  ["none", "none", "passthrough"],
];

const FORMAT_LABELS = {
  png: "1-bit PNG",
  bmp: "1-bit BMP",
  bin: "ESC/POS raw (.bin)",
  txt: "text dot-matrix",
};

/* Must match MAX_SOURCES in ui/app.py: Python drops the oldest upload, so the
   list has to drop it too or old entries would report "handle expired". */
const MAX_ITEMS = 8;

const el = (id) => document.getElementById(id);
const ui = {
  version: el("version"),
  paperSwitch: el("paperSwitch"),
  customWidth: el("customWidth"),
  preset: el("preset"),
  crtToggle: el("crtToggle"),
  dropzone: el("dropzone"),
  fileInput: el("fileInput"),
  browseBtn: el("browseBtn"),
  fileList: el("fileList"),
  clearBtn: el("clearBtn"),
  paper: el("paper"),
  preview: el("preview"),
  empty: el("empty"),
  stats: el("stats"),
  zoomBtn: el("zoomBtn"),
  simBtn: el("simBtn"),
  modes: el("modes"),
  gamma: el("gamma"),
  gammaOut: el("gammaOut"),
  contrast: el("contrast"),
  contrastOut: el("contrastOut"),
  brightness: el("brightness"),
  brightnessOut: el("brightnessOut"),
  threshold: el("threshold"),
  thresholdOut: el("thresholdOut"),
  scale: el("scale"),
  rotate: el("rotate"),
  margin: el("margin"),
  maxHeight: el("maxHeight"),
  invert: el("invert"),
  border: el("border"),
  format: el("format"),
  upscale: el("upscale"),
  render: el("render"),
  exportBtn: el("exportBtn"),
  escposOpts: el("escposOpts"),
  escInit: el("escInit"),
  escFeed: el("escFeed"),
  escCut: el("escCut"),
  sidecar: el("sidecar"),
  status: el("status"),
  statusIcon: el("statusIcon"),
  bar: el("bar"),
  progress: el("bar").parentElement,
  logBtn: el("logBtn"),
  toast: el("toast"),
};

const state = {
  api: null,
  boot: null,
  items: [],
  active: null,
  paper: "58mm",
  dither: "bayer4",
  actualSize: false,
  sim: true,
  busy: false,
  timer: null,
  previewSeq: 0,
  toastTimer: null,
};

/* -------------------------------------------------------------------------- */
/* helpers                                                                    */
/* -------------------------------------------------------------------------- */

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function fmtBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / 1048576).toFixed(2)} MB`;
}

function setStatus(text, kind = "") {
  ui.status.textContent = text;
  ui.status.className = kind;
}

function setBusy(busy, label = "") {
  state.busy = busy;
  ui.progress.classList.toggle("busy", busy);
  ui.exportBtn.disabled = busy || !state.active;
  if (busy) {
    ui.statusIcon.textContent = "#";
    if (label) setStatus(label);
  } else {
    ui.statusIcon.textContent = ">";
  }
}

function toast(message, hint) {
  ui.toast.innerHTML = "";
  const main = document.createElement("div");
  main.textContent = "! " + message;
  ui.toast.appendChild(main);
  if (hint) {
    const note = document.createElement("span");
    note.className = "hint";
    note.textContent = "  " + hint;
    ui.toast.appendChild(note);
  }
  ui.toast.hidden = false;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => {
    ui.toast.hidden = true;
  }, 6000);
}

function fail(payload, fallback = "Something went wrong.") {
  const message = payload && payload.message ? payload.message : fallback;
  const hint = payload && payload.hint ? payload.hint : null;
  setStatus(message, "err");
  toast(message, hint);
}

function readAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error || new Error("read failed"));
    reader.readAsDataURL(file);
  });
}

/* -------------------------------------------------------------------------- */
/* options                                                                    */
/* -------------------------------------------------------------------------- */

function readOptions() {
  const custom = state.paper === "custom";
  const width = Number.parseInt(ui.customWidth.value, 10);
  const maxHeight = Number.parseInt(ui.maxHeight.value, 10);
  const raster = ui.format.value === "png" || ui.format.value === "bmp";
  const item = state.items.find((entry) => entry.handle === state.active);
  let renderWidth = null;
  if (raster) {
    if (ui.render.value === "native") {
      renderWidth = item ? item.source.width : null;
    } else if (ui.render.value !== "print") {
      renderWidth = Number.parseInt(ui.render.value, 10) || null;
    }
  }
  return {
    paper: state.paper,
    width_dots: custom && Number.isFinite(width) ? width : null,
    dither: state.dither,
    threshold: Number.parseInt(ui.threshold.value, 10),
    auto_threshold: Number.parseInt(ui.threshold.value, 10) === 128,
    gamma: Number.parseFloat(ui.gamma.value),
    brightness: Number.parseInt(ui.brightness.value, 10),
    contrast: Number.parseFloat(ui.contrast.value),
    invert: ui.invert.checked,
    scale: ui.scale.value,
    rotate: Number.parseInt(ui.rotate.value, 10),
    margin: Math.max(0, Number.parseInt(ui.margin.value, 10) || 0),
    border: ui.border.checked,
    max_height_dots: Number.isFinite(maxHeight) && maxHeight >= 8 ? maxHeight : null,
    max_source_pixels: 120000000,
    render_width: renderWidth,
  };
}

function escposSettings() {
  return {
    init: ui.escInit.checked,
    feed: Math.max(0, Number.parseInt(ui.escFeed.value, 10) || 0),
    cut: ui.escCut.checked,
  };
}

function syncOutputs() {
  ui.gammaOut.textContent = Number.parseFloat(ui.gamma.value).toFixed(2);
  ui.contrastOut.textContent = Number.parseFloat(ui.contrast.value).toFixed(2);
  ui.brightnessOut.textContent = ui.brightness.value;
  ui.thresholdOut.textContent = ui.threshold.value;
  ui.threshold.disabled = state.dither === "fs";
  ui.threshold.title =
    state.dither === "mean" ? "128 = auto (Otsu)" : state.dither === "fs" ? "Pillow FS is fixed at 128" : "";
}

function applyOptions(options) {
  if (options.paper) setPaper(options.paper, false);
  if (options.dither) setDither(options.dither, false);
  if (options.render) ui.render.value = options.render;
  if (options.gamma !== undefined) ui.gamma.value = options.gamma;
  if (options.contrast !== undefined) ui.contrast.value = options.contrast;
  if (options.threshold !== undefined) ui.threshold.value = options.threshold;
  if (options.scale) ui.scale.value = options.scale;
  syncOutputs();
  schedulePreview();
}

/* Any manual tweak means "no longer exactly that preset". */
function markCustom() {
  if (ui.preset.value) ui.preset.value = "";
}

/* -------------------------------------------------------------------------- */
/* paper + dither                                                             */
/* -------------------------------------------------------------------------- */

function setPaper(paper, preview = true) {
  state.paper = paper;
  for (const button of ui.paperSwitch.querySelectorAll("button")) {
    button.classList.toggle("on", button.dataset.paper === paper);
  }
  ui.customWidth.classList.toggle("hidden", paper !== "custom");
  if (preview) schedulePreview();
}

function setDither(name, preview = true) {
  state.dither = name;
  for (const button of ui.modes.querySelectorAll("button")) {
    button.classList.toggle("on", button.dataset.dither === name);
  }
  syncOutputs();
  if (preview) schedulePreview();
}

function buildModes() {
  ui.modes.innerHTML = "";
  for (const [id, label, note] of DITHERS) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.dither = id;
    const name = document.createElement("b");
    name.textContent = label;
    const small = document.createElement("small");
    small.textContent = note;
    button.append(name, small);
    button.addEventListener("click", () => setDither(id));
    ui.modes.appendChild(button);
  }
  setDither(state.dither, false);
}

function buildFormats() {
  const formats = state.boot.formats || ["png", "bmp", "bin", "txt"];
  ui.format.innerHTML = "";
  for (const value of formats) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = FORMAT_LABELS[value] || value;
    ui.format.appendChild(option);
  }
  ui.format.value = "png";
  updateEscposVisibility();
}

function updateEscposVisibility() {
  ui.escposOpts.classList.toggle("hidden", ui.format.value !== "bin");
  const raster = ui.format.value === "png" || ui.format.value === "bmp";
  ui.upscale.disabled = !raster;
  ui.upscale.title = raster
    ? "repeat each dot to enlarge the file; auto matches the source width"
    : "only png and bmp can be enlarged";
  ui.render.disabled = !raster;
  ui.render.title = raster
    ? "print keeps the paper dot grid; native renders at the source image's pixel width"
    : "only png and bmp can render above the paper width";
}

function buildPresets() {
  ui.preset.innerHTML = "";
  const custom = document.createElement("option");
  custom.value = "";
  custom.textContent = "preset: custom";
  ui.preset.appendChild(custom);
  for (const name of Object.keys(state.boot.presets || {})) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = "preset: " + name;
    ui.preset.appendChild(option);
  }
}

/* -------------------------------------------------------------------------- */
/* file list                                                                  */
/* -------------------------------------------------------------------------- */

function renderList() {
  ui.fileList.innerHTML = "";
  for (const item of state.items) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.name;
    button.title = `${item.name} · ${item.source.width}×${item.source.height}`;
    button.classList.toggle("on", item.handle === state.active);
    if (item.error) button.classList.add("failed");
    button.addEventListener("click", () => select(item.handle));
    li.appendChild(button);
    ui.fileList.appendChild(li);
  }
  ui.exportBtn.disabled = state.busy || !state.active;
}

async function addFiles(files) {
  const list = Array.from(files || []).filter((file) =>
    file.type.startsWith("image/") || /\.(png|jpe?g|bmp|gif|webp|tiff?|heic|avif)$/i.test(file.name)
  );
  if (!list.length) {
    toast("No image files in that drop.", "Supported: PNG, JPEG, BMP, GIF, WEBP, TIFF.");
    return;
  }

  setBusy(true, `loading ${list.length} file(s)…`);
  let firstNew = null;
  for (const file of list) {
    try {
      const dataUrl = await readAsDataURL(file);
      const response = await state.api.load_image(dataUrl, file.name);
      if (!response.ok) {
        fail(response, `Could not load ${file.name}.`);
        continue;
      }
      const item = {
        handle: response.handle,
        name: response.name,
        source: response.source,
      };
      state.items.push(item);
      if (!firstNew) firstNew = item.handle;
    } catch (error) {
      fail({ message: `Could not read ${file.name}.`, hint: String(error) });
    }
  }
  setBusy(false);
  while (state.items.length > MAX_ITEMS) {
    const gone = state.items.shift();
    if (state.active === gone.handle) state.active = null;
  }
  renderList();
  const keep =
    firstNew && state.items.some((item) => item.handle === firstNew)
      ? firstNew
      : state.items.length
        ? state.items[state.items.length - 1].handle
        : null;
  if (!state.active && keep) select(keep);
  else setStatus(`${state.items.length} image(s) loaded.`, "ok");
}

function select(handle) {
  state.active = handle;
  const item = state.items.find((entry) => entry.handle === handle);
  renderList();
  if (!item) {
    ui.preview.hidden = true;
    ui.empty.hidden = false;
    return;
  }
  setStatus(`${item.name} · ${item.source.width}×${item.source.height} px`);
  schedulePreview(true);
}

function clearAll() {
  state.items = [];
  state.active = null;
  ui.preview.hidden = true;
  ui.preview.removeAttribute("src");
  ui.empty.hidden = false;
  ui.stats.textContent = "—";
  renderList();
  setStatus("ready.");
}

/* -------------------------------------------------------------------------- */
/* preview                                                                    */
/* -------------------------------------------------------------------------- */

function schedulePreview(immediate = false) {
  clearTimeout(state.timer);
  if (!state.active) {
    ui.preview.hidden = true;
    ui.empty.hidden = false;
    return;
  }
  state.timer = setTimeout(runPreview, immediate ? 0 : 110);
}

async function runPreview() {
  if (!state.active) return;
  const seq = ++state.previewSeq;
  const options = readOptions();
  setStatus("dithering…");
  const started = performance.now();
  try {
    const response = await state.api.preview(state.active, options);
    if (seq !== state.previewSeq) return; // a newer request already won
    if (!response.ok) {
      fail(response);
      return;
    }
    ui.preview.src = response.image;
    ui.preview.hidden = false;
    ui.empty.hidden = true;
    renderStats(response);
    const elapsed = Math.round(performance.now() - started);
    const unit = response.screen ? "px screen" : "dots";
    setStatus(`ok · ${response.width}×${response.height} ${unit} · ${response.ms} ms engine / ${elapsed} ms round-trip`, "ok");
  } catch (error) {
    if (seq === state.previewSeq) fail({ message: "Preview failed.", hint: String(error) });
  }
}

function renderStats(data) {
  ui.stats.innerHTML = "";
  const parts = [
    ["dots", `${data.width}×${data.height}`],
    ["raster", `${data.row_bytes} B/row · ${fmtBytes(data.raster_bytes)}`],
    ["ink", `${(data.ink_ratio * 100).toFixed(1)}%`],
  ];
  if (data.screen) {
    parts.push(["mode", "screen export"]);
  } else {
    parts.push(["size", `${data.mm[0]}×${data.mm[1]} mm`]);
    parts.push(["bt", `≈${data.print_seconds}s @ 40 kbit/s`]);
  }
  parts.push(["engine", `${data.ms} ms`]);
  for (const [key, value] of parts) {
    const span = document.createElement("span");
    span.innerHTML = `${key} <b>${value}</b>`;
    ui.stats.appendChild(span);
  }
}

/* -------------------------------------------------------------------------- */
/* export                                                                     */
/* -------------------------------------------------------------------------- */

async function exportCurrent() {
  if (!state.active || state.busy) return;
  setBusy(true, "exporting…");
  try {
    const raster = ui.format.value === "png" || ui.format.value === "bmp";
    const response = await state.api.export(
      state.active,
      readOptions(),
      ui.format.value,
      ui.sidecar.checked,
      escposSettings(),
      raster ? ui.upscale.value : "1"
    );
    if (response.cancelled) {
      setStatus("export cancelled.");
    } else if (!response.ok) {
      fail(response, "Export failed.");
    } else {
      const pixels =
        response.upscale > 1
          ? ` · ${response.pixel_width}x${response.pixel_height} px`
          : "";
      setStatus(`✓ wrote ${response.path} (${fmtBytes(response.bytes)}${pixels})`, "ok");
    }
  } catch (error) {
    fail({ message: "Export failed.", hint: String(error) });
  } finally {
    setBusy(false);
  }
}

/* -------------------------------------------------------------------------- */
/* wiring                                                                     */
/* -------------------------------------------------------------------------- */

function wire() {
  ui.browseBtn.addEventListener("click", () => ui.fileInput.click());
  ui.fileInput.addEventListener("change", async () => {
    await addFiles(ui.fileInput.files);
    ui.fileInput.value = "";
  });

  ui.dropzone.addEventListener("click", (event) => {
    if (event.target === ui.dropzone) ui.fileInput.click();
  });
  ui.dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    ui.dropzone.classList.add("over");
  });
  ui.dropzone.addEventListener("dragleave", () => ui.dropzone.classList.remove("over"));
  ui.dropzone.addEventListener("drop", async (event) => {
    event.preventDefault();
    ui.dropzone.classList.remove("over");
    await addFiles(event.dataTransfer.files);
  });

  // Stop WebView2 from navigating when a file is dropped anywhere else.
  document.addEventListener("dragover", (event) => event.preventDefault());
  document.addEventListener("drop", (event) => event.preventDefault());

  ui.paperSwitch.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-paper]");
    if (button) setPaper(button.dataset.paper);
  });

  ui.customWidth.addEventListener("input", () => schedulePreview());

  for (const control of [ui.gamma, ui.contrast, ui.brightness, ui.threshold]) {
    control.addEventListener("input", () => {
      markCustom();
      syncOutputs();
      schedulePreview();
    });
  }
  for (const control of [ui.scale, ui.rotate, ui.margin, ui.maxHeight, ui.invert, ui.border]) {
    control.addEventListener("input", () => {
      markCustom();
      schedulePreview();
    });
    control.addEventListener("change", () => {
      markCustom();
      schedulePreview();
    });
  }

  ui.format.addEventListener("change", updateEscposVisibility);
  ui.render.addEventListener("change", () => {
    markCustom();
    schedulePreview();
  });
  ui.exportBtn.addEventListener("click", exportCurrent);
  ui.clearBtn.addEventListener("click", clearAll);

  ui.preset.addEventListener("change", () => {
    const name = ui.preset.value;
    if (!name) return;
    const preset = (state.boot.presets || {})[name];
    if (preset) applyOptions(preset);
    setStatus(`preset: ${name}`);
  });

  ui.zoomBtn.addEventListener("click", () => {
    state.actualSize = !state.actualSize;
    ui.paper.classList.toggle("actual", state.actualSize);
    ui.zoomBtn.textContent = state.actualSize ? "fit" : "1:1";
  });

  ui.simBtn.addEventListener("click", () => {
    state.sim = !state.sim;
    ui.paper.classList.toggle("sim", state.sim);
    ui.simBtn.textContent = state.sim ? "dark" : "paper";
  });

  ui.crtToggle.addEventListener("click", () => {
    document.body.classList.toggle("no-crt");
    document.body.classList.toggle("crt");
  });

  ui.logBtn.addEventListener("click", async () => {
    const response = await state.api.reveal_logs();
    if (response.ok) setStatus(`logs: ${response.path}`);
    else fail(response, "Could not open the log folder.");
  });

  window.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.key.toLowerCase() === "o") {
      event.preventDefault();
      ui.fileInput.click();
    } else if (event.ctrlKey && event.key.toLowerCase() === "e") {
      event.preventDefault();
      exportCurrent();
    } else if (/^[1-7]$/.test(event.key) && !event.ctrlKey && event.target === document.body) {
      const mode = DITHERS[Number.parseInt(event.key, 10) - 1];
      if (mode) setDither(mode[0]);
    }
  });
}

async function boot() {
  if (!window.pywebview || !window.pywebview.api) {
    document.body.innerHTML =
      '<div style="padding:40px;font-family:monospace;color:#79ffb2">' +
      "This UI must run inside the desktop app.<br>Start it with: <b>tdots gui</b></div>";
    return;
  }
  state.api = window.pywebview.api;
  try {
    state.boot = await state.api.bootstrap();
  } catch (error) {
    document.body.innerHTML =
      '<div style="padding:40px;font-family:monospace;color:#ff6b61">' +
      "Could not talk to the conversion engine.<br><br>" +
      String(error) +
      '<br><br>Start it with <b>tdots gui --debug</b> and check the logs.</div>';
    return;
  }
  ui.version.textContent = "v" + state.boot.version;
  ui.paper.classList.add("sim");

  buildModes();
  buildFormats();
  buildPresets();
  wire();
  syncOutputs();
  setStatus("ready. drop an image or press ctrl+o");
}

window.addEventListener("pywebviewready", boot, { once: true });
