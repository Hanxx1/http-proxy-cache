const els = {
  statusLine: document.querySelector("#status-line"),
  refreshButton: document.querySelector("#refresh-button"),
  autoRefresh: document.querySelector("#auto-refresh"),
  methodFilter: document.querySelector("#method-filter"),
  cacheFilter: document.querySelector("#cache-filter"),
  hideConnect: document.querySelector("#hide-connect"),
  metricTotal: document.querySelector("#metric-total"),
  metricRate: document.querySelector("#metric-rate"),
  metricCache: document.querySelector("#metric-cache"),
  metricAcl: document.querySelector("#metric-acl"),
  topUrlBody: document.querySelector("#top-url-body"),
  topUrlCount: document.querySelector("#top-url-count"),
  cacheBody: document.querySelector("#cache-body"),
  cacheMeta: document.querySelector("#cache-meta"),
  logBody: document.querySelector("#log-body"),
  logCount: document.querySelector("#log-count"),
  aclModeLabel: document.querySelector("#acl-mode-label"),
  aclSaveBtn: document.querySelector("#acl-save-btn"),
  aclMetaMsg: document.querySelector("#acl-meta-msg"),
  aclBlacklist: document.querySelector("#acl-blacklist"),
  aclWhitelist: document.querySelector("#acl-whitelist"),
  aclIp: document.querySelector("#acl-ip"),
  chartHitMiss: document.querySelector("#chart-hitmiss"),
  chartTops: document.querySelector("#chart-tops"),
};

let refreshTimer = null;
let latestLogs = [];
let hitMissChart = null;
let topUrlsChart = null;

/* ─── Helpers ──────────────────────────────── */

function text(value) {
  return value === undefined || value === null || value === "" ? "-" : String(value);
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function td(content, className) {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  if (content instanceof Node) {
    cell.appendChild(content);
  } else {
    cell.textContent = text(content);
  }
  return cell;
}

function badge(value) {
  const el = document.createElement("span");
  const normalized = String(value || "").toLowerCase();
  el.className = `badge ${normalized}`;
  el.textContent = text(value);
  return el;
}

/* ─── Tables ───────────────────────────────── */

function setRows(tbody, rows, renderRow, emptyMessage) {
  tbody.innerHTML = "";
  if (!rows || rows.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.className = "empty";
    cell.colSpan = 10;
    cell.textContent = emptyMessage;
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }
  rows.forEach((item) => tbody.appendChild(renderRow(item)));
}

function renderTopUrl(row) {
  const tr = document.createElement("tr");
  tr.appendChild(td(row.url, "url-cell"));
  tr.appendChild(td(row.count, "num"));
  return tr;
}

function renderCache(row) {
  const tr = document.createElement("tr");
  tr.appendChild(td(row.url, "url-cell"));
  tr.appendChild(td(formatBytes(row.size), "num"));
  tr.appendChild(td(row.hit_count, "num"));
  tr.appendChild(td(row.expires_at));
  return tr;
}

function renderLog(row) {
  const tr = document.createElement("tr");
  const status = Number(row.status || 0);
  const statusBadge = badge(row.status);
  if (status >= 400) statusBadge.classList.add("error");

  tr.appendChild(td(row.time));
  tr.appendChild(td(row.ip));
  tr.appendChild(td(row.method));
  tr.appendChild(td(statusBadge));
  tr.appendChild(td(badge(row.cache)));
  tr.appendChild(td(row.url, "url-cell"));
  return tr;
}

/* ─── ACL Lists (editable) ─────────────────── */

function renderAclList(listEl, values) {
  listEl.innerHTML = "";
  if (!values || values.length === 0) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No entries";
    listEl.appendChild(li);
    return;
  }
  values.forEach((value) => {
    const li = document.createElement("li");
    li.className = "acl-entry";
    const span = document.createElement("span");
    span.textContent = value;
    span.className = "acl-entry-text";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "mini-btn remove-btn";
    btn.textContent = "×";
    btn.title = "Remove";
    btn.addEventListener("click", () => {
      li.remove();
      if (listEl.querySelectorAll("li:not(.empty)").length === 0) {
        renderAclList(listEl, []);
      }
    });
    li.appendChild(span);
    li.appendChild(btn);
    listEl.appendChild(li);
  });
}

function collectAclItems(listEl) {
  const items = [];
  listEl.querySelectorAll(".acl-entry-text").forEach((span) => {
    const val = span.textContent.trim();
    if (val) items.push(val);
  });
  return items;
}

function insertAclInput(listEl) {
  // Remove any existing input row first
  const existing = listEl.querySelector(".acl-input-row");
  if (existing) existing.remove();

  const emptyEl = listEl.querySelector("li.empty");
  if (emptyEl) emptyEl.remove();

  const li = document.createElement("li");
  li.className = "acl-input-row";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "acl-inline-input";
  input.placeholder = "Enter value, press Enter to confirm";

  const confirmBtn = document.createElement("button");
  confirmBtn.type = "button";
  confirmBtn.className = "mini-btn confirm-btn";
  confirmBtn.textContent = "✓";

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "mini-btn cancel-btn";
  cancelBtn.textContent = "✕";

  function commit() {
    const val = input.value.trim();
    if (!val) { cleanup(); return; }
    const entry = createAclEntry(val, listEl);
    li.replaceWith(entry);
  }

  function cleanup() {
    li.remove();
    if (listEl.querySelectorAll("li:not(.empty)").length === 0) {
      const noop = document.createElement("li");
      noop.className = "empty";
      noop.textContent = "No entries";
      listEl.appendChild(noop);
    }
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); commit(); }
    if (e.key === "Escape") { e.preventDefault(); cleanup(); }
  });
  confirmBtn.addEventListener("click", commit);
  cancelBtn.addEventListener("click", cleanup);

  li.appendChild(input);
  li.appendChild(confirmBtn);
  li.appendChild(cancelBtn);
  listEl.insertBefore(li, listEl.firstChild);
  input.focus();
}

function createAclEntry(value, listEl) {
  const li = document.createElement("li");
  li.className = "acl-entry";
  const span = document.createElement("span");
  span.textContent = value;
  span.className = "acl-entry-text";
  const rmBtn = document.createElement("button");
  rmBtn.type = "button";
  rmBtn.className = "mini-btn remove-btn";
  rmBtn.textContent = "×";
  rmBtn.title = "Remove";
  rmBtn.addEventListener("click", () => {
    li.remove();
    if (listEl.querySelectorAll("li:not(.empty)").length === 0) {
      const noop = document.createElement("li");
      noop.className = "empty";
      noop.textContent = "No entries";
      listEl.appendChild(noop);
    }
  });
  li.appendChild(span);
  li.appendChild(rmBtn);
  return li;
}

function setupAclAddButtons() {
  document.querySelectorAll(".mini-btn[data-action='add']").forEach((btn) => {
    btn.addEventListener("click", () => {
      const map = { blacklist: els.aclBlacklist, whitelist: els.aclWhitelist, ip_blacklist: els.aclIp };
      const listEl = map[btn.dataset.list];
      if (!listEl) return;
      insertAclInput(listEl);
    });
  });
}

async function saveAcl() {
  const blacklist = collectAclItems(els.aclBlacklist);
  const whitelist = collectAclItems(els.aclWhitelist);
  const ip_blacklist = collectAclItems(els.aclIp);

  els.aclSaveBtn.disabled = true;
  els.aclMetaMsg.textContent = "Saving...";
  try {
    const resp = await fetch("/api/acl", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ blacklist, whitelist, ip_blacklist }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    els.aclMetaMsg.textContent = "Saved OK";
    els.aclModeLabel.textContent = data.mode;
    els.metricAcl.textContent = data.mode;
    renderAclList(els.aclBlacklist, data.blacklist);
    renderAclList(els.aclWhitelist, data.whitelist);
    renderAclList(els.aclIp, data.ip_blacklist);
  } catch (err) {
    els.aclMetaMsg.textContent = `Error: ${err.message}`;
  } finally {
    els.aclSaveBtn.disabled = false;
    setTimeout(() => { els.aclMetaMsg.textContent = ""; }, 3000);
  }
}

/* ─── Charts ───────────────────────────────── */

function initHitMissChart(data) {
  const ctx = els.chartHitMiss.getContext("2d");
  if (hitMissChart) hitMissChart.destroy();
  hitMissChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["HIT", "MISS"],
      datasets: [{
        data: [data.hits, data.misses],
        backgroundColor: ["#126c61", "#e0e0e0"],
        borderColor: "#fff",
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
      },
    },
  });
}

function initTopUrlsChart(data) {
  const ctx = els.chartTops.getContext("2d");
  if (topUrlsChart) topUrlsChart.destroy();
  const urls = data.top_urls || [];
  topUrlsChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: urls.map((u) => {
        try { return new URL(u.url).hostname; } catch (_) { return u.url; }
      }),
      datasets: [{
        label: "Requests",
        data: urls.map((u) => u.count),
        backgroundColor: "#126c61",
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { precision: 0 },
        },
      },
    },
  });
}

/* ─── Render ───────────────────────────────── */

function render(data) {
  const { status, summary, logs, cache, acl } = data;
  latestLogs = logs || [];

  els.statusLine.textContent =
    `Proxy ${status.proxy_host}:${status.proxy_port} | Admin ${status.admin_host}:${status.admin_port}`;

  els.metricTotal.textContent = summary.total;
  els.metricRate.textContent = `${summary.hit_rate.toFixed(2)}%`;
  els.metricCache.textContent = cache.size;
  els.metricAcl.textContent = acl.mode;
  els.aclModeLabel.textContent = acl.mode;

  els.topUrlCount.textContent = `${summary.top_urls.length} items`;
  setRows(els.topUrlBody, summary.top_urls, renderTopUrl, "No URL data");

  els.cacheMeta.textContent = `${cache.size} / ${cache.max_items} | TTL ${cache.ttl_seconds}s`;
  setRows(els.cacheBody, cache.entries, renderCache, "No cached responses");

  renderFilteredLogs();

  renderAclList(els.aclBlacklist, acl.blacklist);
  renderAclList(els.aclWhitelist, acl.whitelist);
  renderAclList(els.aclIp, acl.ip_blacklist);

  initHitMissChart(summary);
  initTopUrlsChart(summary);
}

/* ─── Log filters ──────────────────────────── */

function getFilteredLogs() {
  const method = els.methodFilter.value;
  const cache = els.cacheFilter.value;
  return latestLogs.filter((row) => {
    if (els.hideConnect.checked && row.method === "CONNECT") return false;
    if (method !== "all" && row.method !== method) return false;
    if (cache !== "all" && row.cache !== cache) return false;
    return true;
  });
}

function renderFilteredLogs() {
  const filtered = getFilteredLogs();
  els.logCount.textContent = `${filtered.length} shown / ${latestLogs.length} total`;
  setRows(els.logBody, filtered.slice().reverse(), renderLog, "No matching request logs");
}

/* ─── Data loading ─────────────────────────── */

async function loadDashboard() {
  els.refreshButton.disabled = true;
  try {
    const response = await fetch("/api/dashboard?limit=100", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    els.statusLine.textContent = `Dashboard unavailable: ${error.message}`;
  } finally {
    els.refreshButton.disabled = false;
  }
}

function configureAutoRefresh() {
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
  if (els.autoRefresh.checked) {
    refreshTimer = window.setInterval(loadDashboard, 3000);
  }
}

/* ─── Event wiring ─────────────────────────── */

els.refreshButton.addEventListener("click", loadDashboard);
els.autoRefresh.addEventListener("change", configureAutoRefresh);
els.methodFilter.addEventListener("change", renderFilteredLogs);
els.cacheFilter.addEventListener("change", renderFilteredLogs);
els.hideConnect.addEventListener("change", renderFilteredLogs);
els.aclSaveBtn.addEventListener("click", saveAcl);

setupAclAddButtons();
configureAutoRefresh();
loadDashboard();
