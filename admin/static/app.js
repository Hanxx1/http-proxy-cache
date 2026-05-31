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
  aclMeta: document.querySelector("#acl-meta"),
  aclBlacklist: document.querySelector("#acl-blacklist"),
  aclWhitelist: document.querySelector("#acl-whitelist"),
  aclIp: document.querySelector("#acl-ip"),
};

let refreshTimer = null;
let latestLogs = [];

function text(value) {
  return value === undefined || value === null || value === "" ? "-" : String(value);
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

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

function renderList(listEl, values) {
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
    li.textContent = value;
    listEl.appendChild(li);
  });
}

function render(data) {
  const { status, summary, logs, cache, acl } = data;
  latestLogs = logs || [];

  els.statusLine.textContent =
    `Proxy ${status.proxy_host}:${status.proxy_port} | Admin ${status.admin_host}:${status.admin_port}`;

  els.metricTotal.textContent = summary.total;
  els.metricRate.textContent = `${summary.hit_rate.toFixed(2)}%`;
  els.metricCache.textContent = cache.size;
  els.metricAcl.textContent = acl.mode;

  els.topUrlCount.textContent = `${summary.top_urls.length} items`;
  setRows(els.topUrlBody, summary.top_urls, renderTopUrl, "No URL data");

  els.cacheMeta.textContent = `${cache.size} / ${cache.max_items} | TTL ${cache.ttl_seconds}s`;
  setRows(els.cacheBody, cache.entries, renderCache, "No cached responses");

  renderFilteredLogs();

  els.aclMeta.textContent = `Mode ${acl.mode}`;
  renderList(els.aclBlacklist, acl.blacklist);
  renderList(els.aclWhitelist, acl.whitelist);
  renderList(els.aclIp, acl.ip_blacklist);
}

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

els.refreshButton.addEventListener("click", loadDashboard);
els.autoRefresh.addEventListener("change", configureAutoRefresh);
els.methodFilter.addEventListener("change", renderFilteredLogs);
els.cacheFilter.addEventListener("change", renderFilteredLogs);
els.hideConnect.addEventListener("change", renderFilteredLogs);

configureAutoRefresh();
loadDashboard();
