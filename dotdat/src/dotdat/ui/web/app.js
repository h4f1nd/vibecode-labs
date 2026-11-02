"use strict";

/*
 * DOTDAT GUI controller.
 *
 * The Python bridge exposes a small, positionally called API:
 *   initial_state()
 *   load(path, encoding)
 *   close()
 *   page(offset, limit, include_deleted, filters, sort, desc)
 *   export(fmt, path, include_deleted, filters, fields, sort, desc)
 *   cancel()
 *   pick_file()
 *   export_dialog(suggested)
 */

const state = {
  ready: false,
  info: null,
  fields: [],
  keys: [],
  page: null,
  offset: 0,
  limit: 100,
  filters: [],
  includeDeleted: false,
  dateFields: new Set(),
  showDates: true,
  sort: null,
  desc: false,
  busy: false,
  exporting: false,
  seq: 0,
};

const el = {};
let toastTimer = null;
let filterTimer = null;

function byId(id) {
  return document.getElementById(id);
}

function cacheElements() {
  const ids = [
    "empty",
    "workspace",
    "encoding",
    "open-btn",
    "open-btn-2",
    "file-name",
    "file-meta",
    "encoding-badge",
    "cards",
    "overview-table",
    "structure-table",
    "keys-table",
    "filter",
    "include-deleted",
    "show-dates",
    "page-size",
    "export-format",
    "export-btn",
    "cancel-btn",
    "prev",
    "next",
    "page-info",
    "jump",
    "jump-btn",
    "status",
    "record-badge",
    "version-badge",
    "toast",
    "data-table",
  ];
  for (const id of ids) {
    el[id.replaceAll("-", "_")] = byId(id);
  }
  el.tabs = Array.from(document.querySelectorAll(".tab"));
  el.panels = {
    overview: byId("tab-overview"),
    structure: byId("tab-structure"),
    data: byId("tab-data"),
  };
  el.dataHead = el.data_table.querySelector("thead");
  el.dataBody = el.data_table.querySelector("tbody");
  el.structureBody = el.structure_table.querySelector("tbody");
  el.keysBody = el.keys_table.querySelector("tbody");
}

/* ------------------------------------------------------------------ utils */

function num(value) {
  if (value === null || value === undefined || value === "") return "—";
  return Number(value).toLocaleString("en-US");
}

function bytes(value) {
  if (!Number.isFinite(value)) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const digits = unit === 0 ? 0 : size >= 100 ? 0 : 1;
  return `${size.toFixed(digits)} ${units[unit]}`;
}

function text(value) {
  if (value === null || value === undefined) return "";
  return String(value);
}

/* Clarion day counts are days since 1800-12-28. The GUI offers to show them
 * as dates; exports always keep the stored number. */
const CLARION_EPOCH_MS = Date.UTC(1800, 11, 28);
const DAY_MS = 86_400_000;

function clarionDate(days) {
  const value = CLARION_EPOCH_MS + Number(days) * DAY_MS;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString().slice(0, 10);
}

function toast(message, hint = "", kind = "error") {
  const node = el.toast;
  node.textContent = "";
  const main = document.createElement("div");
  main.textContent = message;
  node.appendChild(main);
  if (hint) {
    const extra = document.createElement("div");
    extra.className = "hint";
    extra.textContent = hint;
    node.appendChild(extra);
  }
  node.classList.toggle("ok", kind === "ok");
  node.classList.remove("hidden");
  if (toastTimer) window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => node.classList.add("hidden"), kind === "ok" ? 3500 : 9000);
}

function status(message) {
  el.status.textContent = message;
}

function setBusy(value) {
  state.busy = value;
  el.filter.disabled = value;
  el.include_deleted.disabled = value;
  el.page_size.disabled = value;
  el.prev.disabled = value || state.offset <= 0;
  el.next.disabled = value;
  el.jump.disabled = value;
  el.jump_btn.disabled = value;
  el.export_btn.disabled = value || state.exporting;
}

function api(name, ...args) {
  const bridge = window.pywebview && window.pywebview.api;
  if (!bridge || typeof bridge[name] !== "function") {
    return Promise.reject(new Error("The DOTDAT bridge is not ready."));
  }
  return Promise.resolve(bridge[name](...args));
}

async function call(name, ...args) {
  try {
    return await api(name, ...args);
  } catch (error) {
    toast(`Bridge call ${name} failed.`, text(error && error.message ? error.message : error));
    return { ok: false };
  }
}

/* ------------------------------------------------------------------- boot */

function installListeners() {
  el.open_btn.addEventListener("click", pickFile);
  el.open_btn_2.addEventListener("click", pickFile);

  for (const tab of el.tabs) {
    tab.addEventListener("click", () => selectTab(tab.dataset.tab));
  }

  el.filter.addEventListener("input", () => {
    if (filterTimer) window.clearTimeout(filterTimer);
    filterTimer = window.setTimeout(applyFilters, 320);
  });
  el.filter.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (filterTimer) window.clearTimeout(filterTimer);
      applyFilters();
    }
    if (event.key === "Escape") {
      el.filter.value = "";
      applyFilters();
    }
  });

  el.include_deleted.addEventListener("change", () => {
    state.includeDeleted = el.include_deleted.checked;
    state.offset = 0;
    refreshPage();
  });

  el.show_dates.addEventListener("change", () => {
    state.showDates = el.show_dates.checked;
    renderHead();
    renderRows((state.page && state.page.rows) || []);
  });

  el.page_size.addEventListener("change", () => {
    state.limit = Number(el.page_size.value) || 100;
    state.offset = 0;
    refreshPage();
  });

  el.prev.addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - state.limit);
    refreshPage();
  });

  el.next.addEventListener("click", () => {
    state.offset += state.limit;
    refreshPage();
  });

  el.jump_btn.addEventListener("click", jumpToRecord);
  el.jump.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      jumpToRecord();
    }
  });

  el.export_btn.addEventListener("click", startExport);
  el.cancel_btn.addEventListener("click", () => {
    status("cancelling export…");
    api("cancel").catch(() => {});
  });
}

function selectTab(name) {
  for (const tab of el.tabs) {
    tab.classList.toggle("active", tab.dataset.tab === name);
  }
  for (const [key, panel] of Object.entries(el.panels)) {
    panel.classList.toggle("hidden", key !== name);
  }
}

async function boot() {
  cacheElements();
  installListeners();
  status("waiting for the bridge…");

  const initial = await call("initial_state");
  state.ready = true;

  if (initial && initial.encoding) {
    const hasOption = Array.from(el.encoding.options).some((item) => item.value === initial.encoding);
    if (hasOption) el.encoding.value = initial.encoding;
  }
  if (initial && initial.version) {
    el.version_badge.textContent = `v${initial.version}`;
  }

  if (initial && initial.path) {
    await loadFile(initial.path);
  } else {
    status("ready");
  }
}

function waitForBridge() {
  if (window.pywebview && window.pywebview.api) {
    boot();
    return;
  }
  window.addEventListener("pywebviewready", boot, { once: true });
  // A plain browser preview never fires pywebviewready; say so instead of
  // leaving the spinner running forever.
  window.setTimeout(() => {
    if (!state.ready) {
      status("bridge unavailable — launch through dotdat.exe or `dotdat gui`");
    }
  }, 4000);
}

/* ------------------------------------------------------------------- open */

async function pickFile() {
  const path = await call("pick_file");
  if (typeof path === "string" && path) {
    await loadFile(path);
  }
}

async function loadFile(path) {
  if (!path) return;
  setBusy(true);
  status(`opening ${path}…`);
  const encoding = el.encoding.value || "cp437";
  const result = await call("load", path, encoding);
  if (!result || !result.ok) {
    setBusy(false);
    status("open failed");
    toast(result && result.error ? result.error : "The file could not be opened.", result && result.hint ? result.hint : "");
    return;
  }

  state.info = result.info;
  state.fields = result.info.fields || [];
  state.keys = result.info.keys || [];
  state.dateFields = new Set(result.info.date_fields || []);
  state.page = result.page;
  state.offset = 0;
  state.limit = Number(el.page_size.value) || 100;
  state.filters = [];
  state.includeDeleted = el.include_deleted.checked;
  state.sort = null;
  state.desc = false;
  el.filter.value = "";

  el.empty.classList.add("hidden");
  el.workspace.classList.remove("hidden");
  el.encoding_badge.textContent = state.info.encoding || "cp437";

  renderInfo();
  renderPage(result.page);
  selectTab("overview");
  setBusy(false);
  status(`opened ${state.info.file_name}`);
}

/* ----------------------------------------------------------------- render */

function card(label, value, tone = "") {
  const box = document.createElement("div");
  box.className = "card";
  const caption = document.createElement("div");
  caption.className = "label";
  caption.textContent = label;
  const figure = document.createElement("div");
  figure.className = `value ${tone}`.trim();
  figure.textContent = value;
  box.append(caption, figure);
  return box;
}

function renderInfo() {
  const info = state.info;
  const header = info.header;

  el.file_name.textContent = info.file_name;
  el.file_meta.textContent =
    `${bytes(info.size)}  ·  ${num(header.record_count)} records  ·  ` +
    `${num(header.field_count)} fields  ·  ${info.path}`;

  el.cards.textContent = "";
  el.cards.append(
    card("records", num(header.record_count), "green"),
    card("active", num(header.active_count)),
    card("deleted", num(header.deleted_count), header.deleted_count ? "amber" : ""),
    card("fields", num(header.field_count)),
    card("keys", num(header.key_count)),
    card("record", `${num(header.record_length)} B`),
  );

  const rows = [
    ["file", info.path],
    ["size", `${num(info.size)} bytes`],
    ["signature", header.signature_hex],
    ["attributes", `${header.attributes} (${hex4(header.attributes)})`],
    ["records", num(header.record_count)],
    ["deleted", num(header.deleted_count)],
    ["active", num(header.active_count)],
    ["fields", num(header.field_count)],
    ["keys", num(header.key_count)],
    ["pictures", num(header.picture_count)],
    ["arrays", num(header.array_count)],
    ["record length", `${num(header.record_length)} bytes (${num(header.payload_size)} payload)`],
    ["data offset", num(header.data_offset)],
    ["logical eof", num(header.logical_eof)],
    ["logical bof", num(header.logical_bof)],
    ["record name", header.record_name || "(none)"],
    ["memo name", header.memo_name || "(none)"],
    ["memo size", `${num(header.memo_length)} / ${num(header.memo_width)}`],
    ["file prefix", header.file_prefix || "(none)"],
    ["record prefix", header.record_prefix || "(none)"],
    ["last change", info.last_change || "not recorded"],
    ["encoding", info.encoding],
  ];
  const body = el.overview_table;
  body.textContent = "";
  for (const [label, value] of rows) {
    const tr = document.createElement("tr");
    const th = document.createElement("td");
    th.textContent = label;
    const td = document.createElement("td");
    td.textContent = value;
    tr.append(th, td);
    body.appendChild(tr);
  }

  renderStructure();
  renderKeys();
  el.record_badge.textContent = `${num(header.active_count)} rows`;
}

function hex4(value) {
  return `0x${Number(value).toString(16).toUpperCase().padStart(4, "0")}`;
}

function renderStructure() {
  el.structureBody.textContent = "";
  for (const field of state.fields) {
    const tr = document.createElement("tr");
    const cells = [
      [field.index, "num"],
      [field.name, ""],
      [field.type, ""],
      [field.offset, "num"],
      [field.length, "num"],
      [fieldFormat(field), "num"],
      [field.decimals, "num"],
      [field.array_number || "", "num"],
    ];
    for (const [value, cls] of cells) {
      const td = document.createElement("td");
      if (cls) td.className = cls;
      td.textContent = value;
      tr.appendChild(td);
    }
    el.structureBody.appendChild(tr);
  }
}

function fieldFormat(field) {
  if (!field.significant) return "";
  return `${field.significant}.${field.decimals}`;
}

function renderKeys() {
  el.keysBody.textContent = "";
  if (!state.keys.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.className = "muted";
    td.textContent = "No key definitions in this file.";
    tr.appendChild(td);
    el.keysBody.appendChild(tr);
    return;
  }
  const byNumber = new Map(state.fields.map((field) => [field.index, field]));
  for (const key of state.keys) {
    const tr = document.createElement("tr");
    const parts = key.parts
      .map((part) => {
        const field = byNumber.get(part.field_number);
        return field ? `${field.name} (${field.type})` : `field ${part.field_number}`;
      })
      .join(", ");
    const cells = [
      [key.index, "num"],
      [key.name, ""],
      [key.components, "num"],
      [hex4(key.composite_type), "num"],
      [parts, ""],
    ];
    for (const [value, cls] of cells) {
      const td = document.createElement("td");
      if (cls) td.className = cls;
      td.textContent = value;
      tr.appendChild(td);
    }
    el.keysBody.appendChild(tr);
  }
}

function renderPage(page) {
  if (!page) return;
  state.page = page;
  renderHead();
  renderRows(page.rows || []);
  renderPager();
}

function renderHead() {
  el.dataHead.textContent = "";
  const tr = document.createElement("tr");

  const rec = document.createElement("th");
  rec.className = "num";
  rec.textContent = "rec";
  tr.appendChild(rec);

  for (const field of state.fields) {
    const th = document.createElement("th");
    th.textContent = field.name;
    th.title = `${field.type_name} · ${field.length} bytes · offset ${field.offset}`;
    if (state.dateFields.has(field.name)) {
      th.title += " · Clarion date (days since 1800-12-28)";
    }
    if (state.sort === field.name) {
      th.textContent = `${field.name} ${state.desc ? "▼" : "▲"}`;
      th.classList.add("sorted");
    }
    th.addEventListener("click", () => toggleSort(field.name));
    tr.appendChild(th);
  }

  el.dataHead.appendChild(tr);
}

function renderRows(rows) {
  el.dataBody.textContent = "";
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = state.fields.length + 1;
    td.className = "muted";
    td.textContent = state.filters.length
      ? "No records match the current filter."
      : "No records on this page.";
    tr.appendChild(td);
    el.dataBody.appendChild(tr);
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const row of rows) {
    const tr = document.createElement("tr");
    if (row.deleted) tr.className = "deleted";

    const rec = document.createElement("td");
    rec.className = "num rec";
    rec.textContent = row.record;
    tr.appendChild(rec);

    for (const field of state.fields) {
      const td = document.createElement("td");
      const value = row.values[field.name];
      const asDate =
        state.showDates &&
        state.dateFields.has(field.name) &&
        typeof value === "number" &&
        value > 0
          ? clarionDate(value)
          : null;
      td.textContent = asDate || text(value);
      if (asDate) td.className = "date";
      if (!asDate && !text(value)) td.classList.add("muted");
      td.title = text(value);
      tr.appendChild(td);
    }
    fragment.appendChild(tr);
  }
  el.dataBody.appendChild(fragment);
}

function renderPager() {
  const page = state.page;
  const shown = page.rows.length;
  const first = shown ? state.offset + 1 : 0;
  const last = state.offset + shown;
  let label;
  if (page.total === null || page.total === undefined) {
    label = `${num(first)}–${num(last)} · total unknown (filtered)`;
  } else if (page.total === 0) {
    label = "0 records";
  } else {
    label = `${num(first)}–${num(last)} of ${num(page.total)}`;
  }
  if (state.includeDeleted && state.info) {
    label += " · including deleted";
  }
  el.page_info.textContent = label;

  el.prev.disabled = state.busy || state.offset <= 0;
  el.next.disabled = state.busy || !page.has_more;
  el.record_badge.textContent = `${num(page.total !== null && page.total !== undefined ? page.total : shown)} rows`;
}

/* ---------------------------------------------------------------- reading */

function applyFilters() {
  const raw = el.filter.value || "";
  state.filters = raw
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean);
  state.offset = 0;
  state.sort = null;
  state.desc = false;
  refreshPage();
}

async function refreshPage() {
  if (!state.info) return;
  const seq = ++state.seq;
  setBusy(true);
  status("reading…");

  const result = await call(
    "page",
    state.offset,
    state.limit,
    state.includeDeleted,
    state.filters,
    state.sort,
    state.desc,
  );

  if (seq !== state.seq) return;
  setBusy(false);

  if (!result || !result.ok) {
    status("read failed");
    if (result && result.error) toast(result.error, result.hint || "");
    return;
  }

  renderPage(result.page);
  const suffix = state.filters.length ? ` · ${state.filters.length} filter(s)` : "";
  status(`records ${num(state.offset + 1)}–${num(state.offset + result.page.rows.length)}${suffix}`);
}

function toggleSort(name) {
  if (state.sort === name) {
    if (state.desc) {
      state.sort = null;
      state.desc = false;
    } else {
      state.desc = true;
    }
  } else {
    state.sort = name;
    state.desc = false;
  }
  state.offset = 0;
  refreshPage();
}

function jumpToRecord() {
  const record = Number(el.jump.value);
  if (!Number.isFinite(record) || record < 1) {
    toast("Enter a record number of 1 or greater.");
    return;
  }
  state.offset = Math.floor(record) - 1;
  state.offset -= state.offset % state.limit;
  refreshPage();
}

/* --------------------------------------------------------------- exporting */

function extensionFor(fmt) {
  return {
    csv: "csv",
    txt: "txt",
    json: "json",
    jsonl: "jsonl",
    html: "html",
    xml: "xml",
    sql: "sql",
    xlsx: "xlsx",
  }[fmt] || "dat";
}

function suggestedName(fmt) {
  const stem = (state.info && state.info.file_name ? state.info.file_name : "export").replace(/\.[^.]+$/, "");
  return `${stem}.${extensionFor(fmt)}`;
}

async function startExport() {
  if (!state.info || state.exporting) return;

  const fmt = el.export_format.value;
  const suggested = suggestedName(fmt);
  const path = await call("export_dialog", suggested);
  if (typeof path !== "string" || !path) return;

  state.exporting = true;
  setBusy(true);
  el.cancel_btn.classList.remove("hidden");
  status(`exporting to ${path}…`);
  const started = Date.now();

  const result = await call(
    "export",
    fmt,
    path,
    state.includeDeleted,
    state.filters,
    null,
    state.sort,
    state.desc,
  );

  state.exporting = false;
  setBusy(false);
  el.cancel_btn.classList.add("hidden");

  if (!result || !result.ok) {
    status("export failed");
    renderPager();
    return;
  }

  const seconds = Math.max(1, Math.round((Date.now() - started) / 1000));
  renderPager();
  status(`exported ${num(result.count)} rows to ${result.path}`);
  toast(`Exported ${num(result.count)} rows in ${seconds}s.`, result.path, "ok");
}

window.addEventListener("DOMContentLoaded", waitForBridge);
