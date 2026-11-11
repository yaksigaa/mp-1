
// ── State ──────────────────────────────────────────────────────────────────
let STATE = { data: null, source: "demo", dismissed: new Set() };
let WHATIF_CHART = null;
let MONTHLY_CHART = null;
let CATEGORY_CHART = null;
let ROLLING_CHART = null;

const CAT_COLORS = [
  "#6366f1", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b",
  "#ef4444", "#f97316", "#ec4899", "#14b8a6", "#84cc16"
];

// ── DOM helpers ────────────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const show = (el) => el && (el.style.display = "");
const hide = (el) => el && (el.style.display = "none");
const setText = (sel, txt) => { const el = $(sel); if (el) el.textContent = txt; };
const setHTML = (sel, html) => { const el = $(sel); if (el) el.innerHTML = html; };

// ── Navigation ─────────────────────────────────────────────────────────────
function navigate(page) {
  $$(".page").forEach(p => p.classList.remove("active"));
  $$(".nav-link").forEach(l => l.classList.remove("active"));
  const pg = document.getElementById("page-" + page);
  const lnk = document.getElementById("nav-" + page);
  if (pg) pg.classList.add("active");
  if (lnk) lnk.classList.add("active");
  const titles = {
    dashboard: ["Dashboard", "Overview of your financial health"],
    upload: ["Upload Statement", "Import your bank statement"],
    spending: ["Spending Overview", "Category and monthly breakdown"],
    anomalies: ["Anomaly Detection", ""],
    timeline: ["Financial Stories – Recent Two Months", "Month-over-month narrative analysis of your spending"],
    insights: ["Insights & Recommendations", "Smart actions to save more"],
    history: ["Upload History", "Manage and inspect your previously uploaded statements"],
  };
  if (titles[page]) {
    setText("#topbar-title", titles[page][0]);
    setText("#topbar-sub", titles[page][1]);
    const topbarSub = $("#topbar-sub");
    if (topbarSub) {
      topbarSub.style.display = titles[page][1] ? "block" : "none";
    }
  }
  if (page === "dashboard" && STATE.data) {
    renderDashboard();
    renderSidebarInfo();
  }
  if (page === "spending" && STATE.data) renderSpending();
  if (page === "anomalies" && STATE.data) renderAnomalies();
  if (page === "timeline") loadStories();
  if (page === "insights" && STATE.data) renderInsights();
  if (page === "history") loadHistory();
  // close mobile sidebar
  $("#sidebar").classList.remove("open");
}

// ── Loading ────────────────────────────────────────────────────────────────
function showLoading(msg = "Analysing your transactions…") {
  $("#loading-overlay").classList.add("active");
  setText("#loading-msg", msg);
}
function hideLoading() { $("#loading-overlay").classList.remove("active"); }

// ── Alert ──────────────────────────────────────────────────────────────────
function showAlert(containerId, type, msg) {
  const icons = { info: "ℹ️", warn: "⚠️", error: "❌", success: "✅" };
  setHTML("#" + containerId, `<div class="alert-banner ${type}">${icons[type] || "ℹ️"} ${msg}</div>`);
}
function clearAlert(containerId) { setHTML("#" + containerId, ""); }

// ── Load demo data ─────────────────────────────────────────────────────────
async function loadDemo() {
  showLoading("Loading demo dataset…");
  try {
    const z = $("#z-slider") ? $("#z-slider").value : 3;
    const drift = $("#drift-slider") ? $("#drift-slider").value : 4;
    const res = await fetch(`/api/demo?z=${z}&drift=${drift}`);
    const json = await res.json();
    if (!json.ok) throw new Error(json.error);
    STATE.data = json.data;
    STATE.source = "demo";
    STATE.dismissed = new Set();
    renderAll();
    navigate("dashboard");
    showAlert("upload-alert", "info", "Showing built-in demo data with injected anomalies. Upload your CSV to use your own data.");
  } catch (e) {
    showAlert("upload-alert", "error", "Failed to load demo: " + e.message);
  } finally { hideLoading(); }
}

// ── Upload ──────────────────────────────────────────────────────────────────
async function uploadFile(file) {
  clearAlert("upload-alert");
  const name = file.name.toLowerCase();
  if (!name.endsWith(".csv") && !name.endsWith(".pdf")) {
    showAlert("upload-alert", "error", "Only CSV and PDF files are supported.");
    return;
  }
  if (file.size > 16 * 1024 * 1024) {
    showAlert("upload-alert", "error", "File too large (maximum 16 MB allowed).");
    return;
  }

  showLoading("Uploading and analysing " + file.name + "…");
  try {
    const z = $("#z-slider") ? $("#z-slider").value : (STATE.z || 3);
    const drift = $("#drift-slider") ? $("#drift-slider").value : (STATE.drift || 4);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("z", z);
    fd.append("drift", drift);

    let res;
    try {
      res = await fetch("/api/upload", { method: "POST", body: fd });
    } catch (netErr) {
      throw new Error("Unable to connect to Flask server. Please ensure python app.py is running on http://127.0.0.1:5000.");
    }

    let json;
    try {
      json = await res.json();
    } catch (parseErr) {
      throw new Error(`Server returned status ${res.status}: ${res.statusText || 'Non-JSON response'}.`);
    }

    if (!res.ok || !json.ok) {
      throw new Error(json.error || `Server error (${res.status})`);
    }

    STATE.data = json.data;
    STATE.source = "upload";
    STATE.dismissed = new Set();
    STATE.z = z;
    STATE.drift = drift;
    renderAll();
    navigate("dashboard");
    showAlert("upload-alert", "success", `Successfully stored in AWS S3 (<code>${json.data.s3_key || 'uploads/'}</code>) & analysed <strong>${file.name}</strong> (${json.data.summary.tx_count} transactions parsed)!`);
    showToast(`☁️ Stored in S3 & analysed ${file.name}`);
    loadHistory();
  } catch (e) {
    showAlert("upload-alert", "error", "Upload failed: " + e.message);
  } finally {
    hideLoading();
    const fi = $("#file-input");
    if (fi) fi.value = "";
  }
}

// ── Render all sections ────────────────────────────────────────────────────
function renderAll() {
  if (!STATE.data) return;
  renderDashboard();
  renderSidebarInfo();
  renderSpending();
  renderAnomalies();
  renderInsights();
}

function renderSidebarInfo() {
  const s = STATE.data.summary;
  const el = $("#sidebar-data-info");
  if (!el) return;
  el.innerHTML = `
    <div class="data-badge">
      <div style="margin-bottom:4px;font-weight:700;color:#e2e8f0">${STATE.source === "demo" ? "📊 Demo Data" : "📁 " + (STATE.data.filename || "Uploaded")}</div>
      <div><span>${s.tx_count}</span> transactions</div>
      <div>${s.date_from} → ${s.date_to}</div>
    </div>`;
}

// ── Dashboard ──────────────────────────────────────────────────────────────
function renderDashboard() {
  const d = STATE.data; const s = d.summary;
  setText("#m-total-spend", s.total_spend_fmt);
  setText("#m-alerts", s.alert_count);
  setText("#m-tx-count", s.tx_count);
  setText("#m-date-range", s.date_from + " → " + s.date_to);

  // Python-generated Rolling 30d chart
  const rollingImg = document.getElementById("rolling-chart");

  if (rollingImg && d.charts && d.charts.rolling) {
    rollingImg.src = d.charts.rolling + "?v=" + Date.now();
  }

  // Top transactions table
  const tbody = $("#top-tx-body");
  if (tbody && d.top_transactions) {
    tbody.innerHTML = d.top_transactions.map(tx => `
      <tr>
        <td>${tx.date}</td>
        <td>${tx.merchant}</td>
        <td>${catBadge(tx.category)}</td>
        <td class="amount-cell">₹${fmt(tx.amount)}</td>
      </tr>`).join("");
  }

  // Recent transactions table
  const rtbody = $("#recent-tx-body");
  if (rtbody && d.all_transactions) {
    rtbody.innerHTML = d.all_transactions.slice(0, 20).map(tx => `
      <tr>
        <td>${tx.date}</td>
        <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${tx.description}">${tx.merchant}</td>
        <td>${catBadge(tx.category)}</td>
        <td class="amount-cell">₹${fmt(tx.amount)}</td>
      </tr>`).join("");
  }
}

// ── Spending page ──────────────────────────────────────────────────────────
function renderSpending() {
  const d = STATE.data;

  // Python-generated Monthly chart
  const monthlyImg = document.getElementById("monthly-chart");

  if (monthlyImg && d.charts && d.charts.monthly) {
    if (monthlyImg.tagName === "CANVAS") {
      const img = document.createElement("img");
      img.id = "monthly-chart";
      img.alt = "Monthly Spending Trend Graph";
      img.style.width = "100%";
      img.style.height = "100%";
      img.style.objectFit = "contain";
      img.src = d.charts.monthly + "?v=" + Date.now();
      monthlyImg.parentNode.replaceChild(img, monthlyImg);
    } else {
      monthlyImg.src = d.charts.monthly + "?v=" + Date.now();
    }
  }

  // Python-generated Category chart
  const categoryImg = document.getElementById("category-chart");

  if (categoryImg && d.charts && d.charts.category) {
    categoryImg.src = d.charts.category + "?v=" + Date.now();
  }

  // Python-generated What-If chart
  const whatifImg = document.getElementById("whatif-chart");
  if (whatifImg && d.charts && d.charts.whatif) {
    whatifImg.src = d.charts.whatif + "?v=" + Date.now();
  }

  // Category legend
  const legend = $("#cat-legend");

  if (legend && d.category_data) {
    legend.innerHTML = d.category_data.map((c, i) => `
    <div class="legend-item">
      <div class="legend-dot" style="background:${CAT_COLORS[i % CAT_COLORS.length]}"></div>
      <span class="legend-label">${c.category}</span>
      <span class="legend-pct">${c.pct}%</span>
      <span class="legend-val">₹${fmt(c.total)}</span>
    </div>`).join("");
  }

  // Category table
  const ctbody = $("#cat-table-body");
  if (ctbody && d.category_data) {
    const total = d.summary.total_spend;
    ctbody.innerHTML = d.category_data.map((c, i) => `
      <tr>
        <td><span class="legend-dot" style="display:inline-block;background:${CAT_COLORS[i % CAT_COLORS.length]};width:10px;height:10px;border-radius:50%;margin-right:8px"></span>${c.category}</td>
        <td class="amount-cell">₹${fmt(c.total)}</td>
        <td>${c.pct}%</td>
        <td style="width:160px">
          <div class="progress-bar"><div class="progress-fill" style="width:${c.pct}%;background:${CAT_COLORS[i % CAT_COLORS.length]}"></div></div>
        </td>
      </tr>`).join("");
  }

  // Recurring Subscriptions & What-If
  renderSubscriptions();
}

// ── Anomalies page — actionable flagged alerts ─────────────────────────────
function renderAnomalies() {
  const d = STATE.data;
  const container = $("#anomalies-container");
  if (!container || !d) return;

  // Transaction-level anomalies, spending increases, and unusual spikes
  const anomalyKinds = new Set(["dup", "spike", "creep", "new", "drift"]);
  const all_events = (d.events || []).filter(e => anomalyKinds.has(e.kind));
  const visible = all_events.filter(e => !STATE.dismissed.has(e.title + "|" + e.date));

  const totalDups = all_events.filter(e => e.kind === "dup").length;
  const totalSpikes = all_events.filter(e => e.kind === "spike").length;
  const totalCreeps = all_events.filter(e => e.kind === "creep" || e.kind === "new").length;
  const totalDrifts = all_events.filter(e => e.kind === "drift").length;

  const currentZNum = STATE.z !== undefined ? Number(STATE.z) : 2.5;
  const currentDriftNum = STATE.drift !== undefined ? Number(STATE.drift) : 4.0;
  const currentZ = currentZNum.toFixed(1);
  const currentDrift = currentDriftNum.toFixed(1) + "%";
  const modeName = getSensitivityMode(currentZNum, currentDriftNum);

  const badgeEl = $("#sensitivity-badge");
  if (badgeEl) {
    badgeEl.textContent = `Mode: ${modeName} (z=${currentZ})`;
    if (modeName === "Strict") {
      badgeEl.style.background = "rgba(239,68,68,0.15)";
      badgeEl.style.color = "#fca5a5";
      badgeEl.style.borderColor = "rgba(239,68,68,0.3)";
    } else if (modeName === "Relaxed") {
      badgeEl.style.background = "rgba(16,185,129,0.15)";
      badgeEl.style.color = "#6ee7b7";
      badgeEl.style.borderColor = "rgba(16,185,129,0.3)";
    } else {
      badgeEl.style.background = "rgba(99,102,241,0.15)";
      badgeEl.style.color = "#818cf8";
      badgeEl.style.borderColor = "rgba(99,102,241,0.3)";
    }
  }

  // Summary bar
  const summaryEl = $("#anomaly-summary");
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">
        <div style="background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.25);border-radius:10px;padding:12px 16px;flex:1;min-width:120px">
          <div style="font-size:22px;font-weight:800;color:#818cf8">${all_events.length}</div>
          <div style="font-size:12px;color:#94a3b8;margin-top:4px">🔍 Total Anomalies</div>
        </div>
        <div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.25);border-radius:10px;padding:12px 16px;flex:1;min-width:120px">
          <div style="font-size:22px;font-weight:800;color:#fca5a5">${totalDups}</div>
          <div style="font-size:12px;color:#94a3b8;margin-top:4px">👯 Duplicates</div>
        </div>
        <div style="background:rgba(139,92,246,.1);border:1px solid rgba(139,92,246,.25);border-radius:10px;padding:12px 16px;flex:1;min-width:120px">
          <div style="font-size:22px;font-weight:800;color:#c4b5fd">${totalSpikes}</div>
          <div style="font-size:12px;color:#94a3b8;margin-top:4px">⚡ Spending Spikes</div>
        </div>
        <div style="background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.25);border-radius:10px;padding:12px 16px;flex:1;min-width:120px">
          <div style="font-size:22px;font-weight:800;color:#fcd34d">${totalCreeps}</div>
          <div style="font-size:12px;color:#94a3b8;margin-top:4px">🔺 Creep / New</div>
        </div>
        <div style="background:rgba(236,72,153,.1);border:1px solid rgba(236,72,153,.25);border-radius:10px;padding:12px 16px;flex:1;min-width:120px">
          <div style="font-size:22px;font-weight:800;color:#f472b6">${totalDrifts}</div>
          <div style="font-size:12px;color:#94a3b8;margin-top:4px">📈 Spending Drift</div>
        </div>
      </div>`;
  }

  if (!visible.length) {
    container.innerHTML = `<div class="empty-state"><div class="es-icon">✅</div><h3>No anomalies detected</h3><p>No unusual spikes, price creep, or duplicates found in ${modeName} mode (threshold z=${currentZ}, drift=${currentDrift}).</p></div>`;
    setText("#anomaly-count", `0 anomalies flagged · ${modeName} Mode (z=${currentZ}, drift=${currentDrift})`);
    return;
  }

  setText("#anomaly-count", `${visible.length} unusual item${visible.length === 1 ? "" : "s"} flagged · ${modeName} Mode (z=${currentZ}, drift=${currentDrift})`);
  const kindLabels = {
    dup: "👯 DUPLICATE",
    spike: "⚡ SPIKE",
    creep: "🔺 PRICE CREEP",
    new: "🆕 NEW CHARGE",
    drift: "📈 SPENDING DRIFT"
  };

  container.innerHTML = visible.map((e, i) => `
    <div class="anomaly-card" id="anom-${i}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
        <div style="flex:1">
          <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
            <span class="anomaly-tag tag-${e.kind}">${kindLabels[e.kind] || e.kind.toUpperCase()}</span>
            <span class="sev-badge sev${e.severity}">${e.sev_label}</span>
            <span style="font-size:11px;color:#64748b">${e.date}</span>
          </div>
          <div style="font-size:15px;font-weight:700;margin-bottom:8px">${e.icon} ${e.title}</div>
          <div style="font-size:13px;color:#94a3b8;line-height:1.6">${e.why}</div>
          ${e.kind === "dup" ? `<div style="margin-top:10px;padding:10px 14px;background:rgba(239,68,68,.08);border-radius:8px;border-left:3px solid #ef4444;font-size:13px;color:#fca5a5">⚠️ Action: Check your bank statement and contact your bank if this is an error. You may be owed a refund.</div>` : ""}
          ${e.yearly ? `<div style="margin-top:8px;font-size:13px;color:#6ee7b7;font-weight:700">💰 Estimated yearly impact: ₹${fmt(e.yearly)}</div>` : ""}
        </div>
        ${e.series && e.series.length > 1 ? `<div style="width:130px;height:65px;flex-shrink:0"><img src="${d.charts.anomalies}?v=${Date.now()}&item=${i}" style="width:100%;height:100%;object-fit:contain;" alt="Anomaly graph"></div>` : ""}
      </div>
      <div style="margin-top:12px;display:flex;gap:8px">
        <button class="dismiss-btn" onclick="dismissEvent('${e.title}', '${e.date}', 'anom-${i}')">Dismiss</button>
        <button class="dismiss-btn" style="border-color:#10b981;color:#6ee7b7" onclick="dismissEvent('${e.title}', '${e.date}', 'anom-${i}')">Expected ✓</button>
      </div>
    </div>`).join("");
}

function dismissEvent(title, date, cardId) {
  STATE.dismissed.add(title + "|" + date);
  const card = document.getElementById(cardId);
  if (card) { card.style.opacity = "0"; card.style.transform = "translateX(20px)"; setTimeout(() => card.remove(), 300); }
}

// ── Financial Stories — Recent Two Months ───────────────────────────────────
async function loadStories() {
  const container = $("#timeline-container");
  if (!container) return;
  container.innerHTML = `
    <div class="empty-state">
      <div class="spinner" style="margin:0 auto 12px"></div>
      <h3>Generating your 2-month financial stories…</h3>
      <p style="color:#64748b;font-size:13px">Comparing your latest two months of transactions…</p>
    </div>`;

  try {
    const res = await fetch("/api/stories");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || "Failed to generate stories");

    const data = json.data;
    if (!data || !data.has_enough_data) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="es-icon">📖</div>
          <h3>Insufficient Data for 2-Month Comparison</h3>
          <p style="color:#94a3b8;font-size:14px;max-width:520px;margin:10px auto;line-height:1.6">
            ${(data && data.message) ? data.message : "Upload statements covering at least two months to unlock month-over-month Financial Stories and spending comparison."}
          </p>
          <button class="btn btn-primary btn-sm" style="margin-top:14px" onclick="navigate('upload')">📤 Upload Statements</button>
        </div>`;
      return;
    }

    const months = data.months || [];
    const stories = data.stories || [];

    const diffSign = data.diff_total > 0 ? "+" : "";
    const trendColor = data.diff_total > 0 ? "#fca5a5" : data.diff_total < 0 ? "#6ee7b7" : "#94a3b8";

    let html = `
      <div style="background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px 24px;margin-bottom:24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px">
        <div>
          <div style="font-size:12px;color:var(--text3);text-transform:uppercase;letter-spacing:0.06em;font-weight:700">Recent 2-Month Comparison</div>
          <div style="font-size:20px;font-weight:800;color:#e2e8f0;margin-top:4px">${months[0] || "Month 1"} → ${months[1] || "Month 2"}</div>
        </div>
        <div style="display:flex;gap:24px;align-items:center;flex-wrap:wrap">
          <div>
            <div style="font-size:12px;color:var(--text3)">${months[0] || "Month 1"} Spend</div>
            <div style="font-size:17px;font-weight:700;color:#94a3b8">₹${fmt(data.total_prev || 0)}</div>
          </div>
          <div style="font-size:18px;color:#64748b">→</div>
          <div>
            <div style="font-size:12px;color:var(--text3)">${months[1] || "Month 2"} Spend</div>
            <div style="font-size:17px;font-weight:700;color:#e2e8f0">₹${fmt(data.total_curr || 0)}</div>
          </div>
          <div style="padding:6px 14px;background:rgba(255,255,255,0.04);border-radius:8px;border:1px solid var(--border)">
            <div style="font-size:12px;color:var(--text3)">MoM Shift</div>
            <div style="font-size:17px;font-weight:800;color:${trendColor}">${diffSign}₹${fmt(Math.abs(data.diff_total || 0))} (${diffSign}${data.pct_total || 0}%)</div>
          </div>
        </div>
      </div>
      <div class="stories-grid" style="display:grid;grid-template-columns:1fr;gap:16px">`;

    const kindLabels = {
      trend: "SPENDING TREND",
      spike: "UNUSUAL EXPENSE",
      category: "HIGH SPEND CATEGORY",
      creep: "SUBSCRIPTION CREEP",
      drift: "GRADUAL SPENDING DRIFT",
      savings: "SAVINGS OPPORTUNITY"
    };

    stories.forEach((s) => {
      const sevClass = s.severity === 2 ? "sev2" : "sev1";
      html += `
        <div class="story-card ${sevClass}" style="margin-bottom:0">
          <div class="story-card-header" style="align-items:flex-start">
            <div class="story-icon" style="font-size:24px;width:44px;height:44px;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,0.05);border-radius:10px">${s.icon}</div>
            <div style="flex:1">
              <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
                <span class="anomaly-tag tag-${s.kind}">${kindLabels[s.kind] || s.kind.toUpperCase()}</span>
                <span style="font-size:11px;padding:2px 8px;border-radius:6px;background:rgba(99,102,241,0.12);color:#a5b4fc;font-weight:600">${s.category}</span>
                <span style="font-size:11px;color:#64748b">📅 ${s.date}</span>
              </div>
              <div class="story-title" style="font-size:16px;font-weight:700;margin-bottom:6px">${s.title}</div>
              <div class="story-why" style="font-size:13px;line-height:1.6;color:#94a3b8">${s.description}</div>
            </div>
            ${s.amount_fmt ? `
              <div style="text-align:right;flex-shrink:0;padding-left:12px">
                <div style="font-size:11px;color:#64748b">Amount Impact</div>
                <div style="font-size:18px;font-weight:800;color:#e2e8f0">${s.amount_fmt}</div>
              </div>` : ""}
          </div>
        </div>`;
    });

    html += `</div>`;
    container.innerHTML = html;

  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="es-icon">❌</div><h3>Failed to load stories</h3><p>${e.message}</p></div>`;
  }
}
const renderTimeline = loadStories;

// ── User Profile ────────────────────────────────────────────────────────────
async function loadCurrentUser() {
  try {
    const res = await fetch("/api/me");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    if (json.ok && json.user) {
      STATE.user = json.user;
      setText("#user-name-text", json.user.name || json.user.email);
      const av = $("#user-avatar");
      if (av && json.user.name) av.textContent = json.user.name.charAt(0).toUpperCase();
    }
  } catch (e) {
    console.error("Failed to load user info:", e);
  }
}

// ── Statement Upload History ────────────────────────────────────────────────
async function loadHistory() {
  const tbody = $("#history-table-body");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#94a3b8;padding:24px"><div class="spinner" style="margin:0 auto 12px"></div>Loading statement history…</td></tr>`;

  try {
    const res = await fetch("/api/history");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || "Failed to load history");

    const stmts = json.statements || [];
    if (!stmts.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7">
            <div class="empty-state" style="padding:28px 16px">
              <div class="es-icon">📜</div>
              <h3>No statements uploaded yet</h3>
              <p style="color:#64748b;font-size:13px;margin-top:4px">Upload a CSV or PDF bank statement to start tracking your financial history.</p>
              <button class="btn btn-primary btn-sm" style="margin-top:12px" onclick="navigate('upload')">📤 Upload Statement</button>
            </div>
          </td>
        </tr>`;
      return;
    }

    tbody.innerHTML = stmts.map(s => {
      const uploadDt = s.upload_date ? s.upload_date.slice(0, 16).replace("T", " ") : "—";
      const period = (s.date_from && s.date_to) ? `${s.date_from} → ${s.date_to}` : "—";
      return `
        <tr>
          <td><strong style="color:#e2e8f0">📁 ${s.filename}</strong></td>
          <td style="color:#94a3b8;font-size:12px">${uploadDt}</td>
          <td><span style="font-weight:600">${s.tx_count}</span> txns</td>
          <td style="color:#94a3b8;font-size:12px">${period}</td>
          <td class="amount-cell">₹${fmt(s.total_spend)}</td>
          <td><span style="font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;background:rgba(16,185,129,.15);color:#6ee7b7">🟢 PROCESSED</span></td>
          <td>
            <div style="display:flex;gap:6px">
              <button class="btn btn-outline btn-sm" onclick="viewStatementTransactions(${s.id})">🔍 Transactions</button>
              <button class="btn btn-primary btn-sm" onclick="loadStatementAnalysis(${s.id})">📊 Dashboard</button>
            </div>
          </td>
        </tr>`;
    }).join("");

  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#fca5a5;padding:20px">Error loading history: ${e.message}</td></tr>`;
  }
}

async function viewStatementTransactions(statementId) {
  const card = $("#history-details-card");
  const txBody = $("#history-tx-body");
  if (!card || !txBody) return;

  card.style.display = "block";
  card.scrollIntoView({ behavior: "smooth" });
  txBody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#94a3b8;padding:20px">Loading transaction details…</td></tr>`;

  try {
    const res = await fetch(`/api/history/${statementId}`);
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || "Failed to fetch statement details");

    const s = json.statement;
    const txs = json.transactions || [];

    setText("#history-detail-title", `Transactions · ${s.filename}`);
    setText("#history-detail-sub", `${txs.length} transactions · Total ₹${fmt(s.total_spend)} · Period: ${s.date_from || "—"} to ${s.date_to || "—"}`);

    const loadBtn = $("#load-analysis-btn");
    if (loadBtn) {
      loadBtn.onclick = () => loadStatementAnalysis(statementId);
    }

    if (!txs.length) {
      txBody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#64748b;padding:20px">No transactions recorded for this statement.</td></tr>`;
      return;
    }

    txBody.innerHTML = txs.map(tx => `
      <tr>
        <td style="white-space:nowrap">${tx.date}</td>
        <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${tx.description}">${tx.description}</td>
        <td><strong>${tx.merchant}</strong></td>
        <td>${catBadge(tx.category)}</td>
        <td class="amount-cell">₹${fmt(tx.amount)}</td>
      </tr>`).join("");

  } catch (e) {
    txBody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#fca5a5;padding:20px">Failed to load transactions: ${e.message}</td></tr>`;
  }
}

async function loadStatementAnalysis(statementId) {
  showLoading("Loading statement analysis into dashboard…");
  try {
    const res = await fetch(`/api/history/${statementId}/load`, { method: "POST" });
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || "Failed to load statement analysis");

    STATE.data = json.data;
    STATE.source = "history";
    STATE.dismissed = new Set();
    renderAll();
    navigate("dashboard");
    showToast(`✅ Loaded analysis for ${json.data.filename || "statement"}`);
  } catch (e) {
    showAlert("upload-alert", "error", "Failed to load analysis: " + e.message);
    showToast("❌ Could not load statement");
  } finally {
    hideLoading();
  }
}

// ── Subscriptions ──────────────────────────────────────────────────────────
function renderSubscriptions() {
  const d = STATE.data; if (!d) return;
  const container = $("#subs-container");
  if (!container) return;
  const subs = d.subscriptions || [];
  if (!subs.length) {
    setText("#subs-summary", "No recurring subscriptions");
    container.innerHTML = `
      <div class="empty-state">
        <div class="es-icon">📋</div>
        <h3>No recurring subscriptions detected</h3>
        <p style="color:#64748b;font-size:13px;margin-top:6px">No recurring monthly charges found in this statement.</p>
      </div>`;
    renderWhatif();
    return;
  }
  const active = subs.filter(s => s.active);
  setText("#subs-summary", active.length + " active · ₹" + fmt(active.reduce((a, s) => a + s.amount, 0)) + "/month");
  container.innerHTML = subs.map(s => `
  <div class="sub-card ${s.active ? "active-sub" : "inactive-sub"}">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div class="sub-name">${s.merchant}</div>
      <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px;background:${s.active ? "rgba(16,185,129,.15)" : "rgba(100,116,139,.15)"};color:${s.active ? "#6ee7b7" : "#94a3b8"}">${s.active ? "🟢 ACTIVE" : "⚪ ENDED"}</span>
    </div>
    <div class="sub-amount">₹${fmt(s.amount)}<span style="font-size:13px;color:#94a3b8;font-weight:400">/mo</span></div>
    <div class="sub-meta">
      <div>Since ${s.first} · ${s.charges} charge${s.charges > 1 ? "s" : ""}</div>
      <div>₹${fmt(s.yearly)} / year</div>
      ${s.amount !== s.first_amount ? `<div style="color:#fca5a5">Was ₹${fmt(s.first_amount)}/mo → ₹${fmt(s.amount)}/mo</div>` : ""}
    </div>
  </div>`).join("");

  // Populate what-if checklist
  renderWhatif();
}

// ── What-if ────────────────────────────────────────────────────────────────
function renderWhatif() {
  const d = STATE.data; if (!d) return;
  const subs = (d.subscriptions || []).filter(s => s.active);
  const list = $("#whatif-list");
  if (!list) return;

  const whatifImg = document.getElementById("whatif-chart");
  if (whatifImg && d.charts && d.charts.whatif && (!whatifImg.src || whatifImg.src.endsWith("/") || whatifImg.getAttribute("src") === "")) {
    whatifImg.src = d.charts.whatif + "?v=" + Date.now();
  }

  if (!subs.length) {
    list.innerHTML = `
      <div class="empty-state" style="padding:24px 16px">
        <div class="es-icon" style="font-size:24px;margin-bottom:8px">🎚️</div>
        <h3 style="font-size:14px;color:#e2e8f0;margin-bottom:4px">No active subscriptions detected</h3>
        <p style="color:#64748b;font-size:12px">Upload statements spanning 2+ months with recurring charges to simulate cancellation savings.</p>
      </div>`;
    setText("#wi-saved-year", "₹0");
    setText("#wi-saved-month", "₹0/mo");
    setText("#wi-new-monthly", "₹0/mo");
    updateWhatif();
    return;
  }
  list.innerHTML = subs.map(s => {
    const safeName = (s.merchant || "").replace(/'/g, "\\'").replace(/"/g, "&quot;");
    return `
    <div class="cancel-item" onclick="toggleCancel(event, this, '${safeName}')">
      <input type="checkbox" class="cancel-check" data-merchant="${safeName}">
      <span class="cancel-name">${s.merchant}</span>
      <span class="cancel-amt">₹${fmt(s.amount)}/mo</span>
    </div>`;
  }).join("");
  updateWhatif();
}

function toggleCancel(event, el, merchant) {
  if (event && event.target && event.target.tagName === "INPUT") {
    el.classList.toggle("selected", event.target.checked);
  } else {
    el.classList.toggle("selected");
    const cb = el.querySelector("input");
    if (cb) cb.checked = el.classList.contains("selected");
  }
  updateWhatif();
}

async function updateWhatif() {
  const d = STATE.data; if (!d) return;
  const subs = d.subscriptions || [];
  const cancel = Array.from($$(".cancel-item.selected")).map(el => {
    const inp = el.querySelector("input");
    return inp ? inp.dataset.merchant : null;
  }).filter(Boolean);
  try {
    const res = await fetch("/api/whatif", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subscriptions: subs, cancel })
    });
    const json = await res.json();
    if (!json.ok) return;
    setText("#wi-saved-year", "₹" + fmt(json.saved_yearly));
    setText("#wi-saved-month", "₹" + fmt(json.saved_monthly) + "/mo");
    setText("#wi-new-monthly", "₹" + fmt(json.new_monthly) + "/mo");

    // Update Python-generated What-if chart
    const whatifImg = document.getElementById("whatif-chart");
    if (whatifImg && json.chart_url) {
      whatifImg.src = json.chart_url + "?v=" + Date.now();
    }
  } catch (e) {
    console.error("What-If update error:", e);
  }
}

// ── Insights ────────────────────────────────────────────────────────────────
function renderInsights() {
  const d = STATE.data; if (!d) return;
  const container = $("#insights-container");
  if (!container) return;

  const insights = [];
  const s = d.summary;

  if (s.leak_year > 1000) {
    insights.push({ icon: "💧", color: "rgba(239,68,68,0.15)", title: "Spending Leak Detected", text: `Your leak score is ${s.leak_score}/100. We estimate ₹${fmt(s.leak_year)} per year is going to subscription creep, category drift, or new recurring charges.`, savings: "Potential savings: ₹" + fmt(s.leak_year) + "/year" });
  }
  (d.subscriptions || []).filter(s => s.active && s.amount !== s.first_amount).forEach(sub => {
    insights.push({ icon: "🔺", color: "rgba(249,115,22,0.15)", title: `${sub.merchant} price increased`, text: `Started at ₹${fmt(sub.first_amount)}/mo, now ₹${fmt(sub.amount)}/mo. That is ₹${fmt((sub.amount - sub.first_amount) * 12)} extra per year.`, savings: null });
  });
  const drifts = (d.events || []).filter(e => e.kind === "drift");
  drifts.forEach(e => {
    insights.push({ icon: "📈", color: "rgba(245,158,11,0.15)", title: e.title, text: e.why, savings: e.yearly ? "Yearly overspend: ₹" + fmt(e.yearly) : null });
  });
  const dups = (d.events || []).filter(e => e.kind === "dup");
  if (dups.length) {
    insights.push({ icon: "👯", color: "rgba(139,92,246,0.15)", title: `${dups.length} possible duplicate charge${dups.length > 1 ? "s" : ""}`, text: "Review these transactions — they may be accidental double charges.", savings: null });
  }
  const activeSubs = (d.subscriptions || []).filter(s => s.active);
  if (activeSubs.length >= 4) {
    const monthly = activeSubs.reduce((a, s) => a + s.amount, 0);
    insights.push({ icon: "📋", color: "rgba(6,182,212,0.15)", title: "Subscription audit recommended", text: `You have ${activeSubs.length} active subscriptions costing ₹${fmt(monthly)}/month. Consider reviewing which ones you actually use.`, savings: null });
  }
  if (!insights.length) {
    insights.push({ icon: "🌟", color: "rgba(16,185,129,0.15)", title: "Your finances look healthy!", text: "No major issues detected. Keep up the good work!", savings: null });
  }

  container.innerHTML = insights.map(ins => `
  <div class="insight-card">
    <div class="insight-icon" style="background:${ins.color}">${ins.icon}</div>
    <div class="insight-body">
      <h4>${ins.title}</h4>
      <p>${ins.text}</p>
      ${ins.savings ? `<div class="insight-savings">${ins.savings}</div>` : ""}
    </div>
  </div>`).join("");
}

// ── Chart options ──────────────────────────────────────────────────────────
function chartOpts(title, showLegend) {
  return {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { display: showLegend, labels: { color: "#94a3b8", boxWidth: 12, padding: 16, font: { size: 12 } } },
      tooltip: { backgroundColor: "#1a2235", borderColor: "#1e2d45", borderWidth: 1, titleColor: "#e2e8f0", bodyColor: "#94a3b8", callbacks: { label: ctx => ` ₹${fmt(ctx.parsed.y || ctx.parsed)}` } }
    },
    scales: {
      x: { grid: { color: "rgba(30,45,69,0.6)" }, ticks: { color: "#64748b", font: { size: 11 } } },
      y: { grid: { color: "rgba(30,45,69,0.6)" }, ticks: { color: "#64748b", font: { size: 11 }, callback: v => "₹" + (v >= 1000 ? (v / 1000).toFixed(0) + "k" : v) } }
    }
  };
}

// ── Utilities ──────────────────────────────────────────────────────────────
function fmt(n) { return Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 }); }

function catBadge(cat) {
  const colors = {
    "Food": "#f97316",
    "Food Delivery": "#f97316",
    "Groceries": "#10b981",
    "Transport": "#06b6d4",
    "Shopping": "#6366f1",
    "Bills": "#eab308",
    "Entertainment": "#ec4899",
    "Healthcare": "#14b8a6",
    "Subscriptions": "#8b5cf6",
    "Others": "#64748b",
    "Other": "#64748b"
  };
  const c = colors[cat] || "#64748b";
  return `<span class="cat-badge" style="background:${c}22;color:${c};border:1px solid ${c}44">${cat}</span>`;
}

// ── Settings Modal Controller ──────────────────────────────────────────────
function getSensitivityMode(z, drift) {
  const numZ = parseFloat(z);
  if (Math.abs(numZ - 1.5) < 0.3) return "Strict";
  if (Math.abs(numZ - 2.5) < 0.3) return "Normal";
  if (Math.abs(numZ - 3.5) < 0.3) return "Relaxed";
  return numZ <= 1.8 ? "Strict" : (numZ >= 3.2 ? "Relaxed" : "Normal");
}

function openSettings() {
  const modal = $("#settings-modal");
  if (!modal) return;
  const currentZ = STATE.z || 2.5;
  const currentDrift = STATE.drift || 4.0;
  const mz = $("#modal-z-slider");
  const md = $("#modal-drift-slider");
  if (mz) { mz.value = currentZ; setText("#modal-z-val", Number(currentZ).toFixed(1)); }
  if (md) { md.value = currentDrift; setText("#modal-drift-val", Number(currentDrift).toFixed(1) + "%"); }

  // Highlight active preset if matches
  updatePresetButtons(currentZ, currentDrift);
  modal.classList.add("open");
}

function closeSettings() {
  const modal = $("#settings-modal");
  if (modal) modal.classList.remove("open");
}

function updatePresetButtons(z, drift) {
  const mode = getSensitivityMode(z, drift);
  $$(".preset-btn").forEach(btn => {
    const p = btn.dataset.preset;
    let isActive = false;
    if (p === "strict" && mode === "Strict") isActive = true;
    else if ((p === "normal" || p === "balanced") && mode === "Normal") isActive = true;
    else if (p === "relaxed" && mode === "Relaxed") isActive = true;
    btn.classList.toggle("active", isActive);
  });
}

async function applySettings() {
  const mz = $("#modal-z-slider");
  const md = $("#modal-drift-slider");
  const pz = $("#z-slider");
  const pd = $("#drift-slider");

  const modal = $("#settings-modal");
  const modalIsOpen = modal && modal.classList.contains("open");

  let z = 2.5;
  let drift = 4.0;

  if (modalIsOpen && mz && md) {
    z = parseFloat(mz.value);
    drift = parseFloat(md.value);
  } else if (pz && pd) {
    z = parseFloat(pz.value);
    drift = parseFloat(pd.value);
  } else if (mz && md) {
    z = parseFloat(mz.value);
    drift = parseFloat(md.value);
  } else {
    z = STATE.z || 3.0;
    drift = STATE.drift || 4.0;
  }

  // Sync all slider controls and labels
  if (pz) { pz.value = z; setText("#z-val", z); }
  if (pd) { pd.value = drift; setText("#drift-val", drift); }
  if (mz) { mz.value = z; setText("#modal-z-val", Number(z).toFixed(1)); }
  if (md) { md.value = drift; setText("#modal-drift-val", Number(drift).toFixed(1) + "%"); }
  updatePresetButtons(z, drift);

  showLoading("Re-analysing transactions with new settings…");
  try {
    const res = await fetch(`/api/reanalyse?z=${z}&drift=${drift}`);
    let json;
    try {
      json = await res.json();
    } catch (e) {
      throw new Error(`Server returned HTTP ${res.status}`);
    }
    if (!res.ok || !json.ok) throw new Error(json.error || "Re-analysis failed.");

    STATE.data = json.data;
    STATE.z = z;
    STATE.drift = drift;
    STATE.dismissed = new Set();
    renderAll();
    closeSettings();
    const modeName = getSensitivityMode(z, drift);
    showToast(`⚙️ Sensitivity updated to ${modeName} (z=${z.toFixed(1)}, drift=${drift.toFixed(1)}%)`);
  } catch (err) {
    alert("Could not update settings: " + err.message);
  } finally {
    hideLoading();
  }
}

function showToast(msg) {
  const toast = $("#toast");
  if (!toast) return;
  toast.innerHTML = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3500);
}

// ── Event listeners ────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Page sensitivity sliders
  const zSlider = $("#z-slider");
  const driftSlider = $("#drift-slider");
  if (zSlider) {
    zSlider.addEventListener("input", () => {
      setText("#z-val", zSlider.value);
      const mz = $("#modal-z-slider");
      if (mz) { mz.value = zSlider.value; setText("#modal-z-val", Number(zSlider.value).toFixed(1)); }
    });
  }
  if (driftSlider) {
    driftSlider.addEventListener("input", () => {
      setText("#drift-val", driftSlider.value);
      const md = $("#modal-drift-slider");
      if (md) { md.value = driftSlider.value; setText("#modal-drift-val", Number(driftSlider.value).toFixed(1) + "%"); }
    });
  }
  const pageApplyBtn = $("#page-apply-btn");
  if (pageApplyBtn) pageApplyBtn.addEventListener("click", applySettings);

  // Modal sensitivity sliders
  const modalZ = $("#modal-z-slider");
  const modalDrift = $("#modal-drift-slider");
  if (modalZ) modalZ.addEventListener("input", () => {
    setText("#modal-z-val", Number(modalZ.value).toFixed(1));
    updatePresetButtons(parseFloat(modalZ.value), modalDrift ? parseFloat(modalDrift.value) : 4.0);
  });
  if (modalDrift) modalDrift.addEventListener("input", () => {
    setText("#modal-drift-val", Number(modalDrift.value).toFixed(1) + "%");
    updatePresetButtons(modalZ ? parseFloat(modalZ.value) : 3.0, parseFloat(modalDrift.value));
  });

  // Modal Presets
  const presets = {
    strict: { z: 1.5, drift: 2.0 },
    normal: { z: 2.5, drift: 4.0 },
    balanced: { z: 2.5, drift: 4.0 },
    relaxed: { z: 3.5, drift: 6.0 }
  };
  $$(".preset-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const cfg = presets[btn.dataset.preset];
      if (cfg) {
        if (modalZ) { modalZ.value = cfg.z; setText("#modal-z-val", cfg.z.toFixed(1)); }
        if (modalDrift) { modalDrift.value = cfg.drift; setText("#modal-drift-val", cfg.drift.toFixed(1) + "%"); }
        const pz = $("#z-slider");
        const pd = $("#drift-slider");
        if (pz) { pz.value = cfg.z; setText("#z-val", cfg.z.toFixed(1)); }
        if (pd) { pd.value = cfg.drift; setText("#drift-val", cfg.drift.toFixed(1)); }
        $$(".preset-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
      }
    });
  });

  // Settings triggers
  const rerunBtn = $("#rerun-btn");
  if (rerunBtn) rerunBtn.addEventListener("click", openSettings);
  const settingsBtn = $("#settings-btn");
  if (settingsBtn) settingsBtn.addEventListener("click", openSettings);
  const navSettings = $("#nav-settings");
  if (navSettings) navSettings.addEventListener("click", openSettings);
  const closeSettingsBtn = $("#close-settings-btn");
  if (closeSettingsBtn) closeSettingsBtn.addEventListener("click", closeSettings);
  const modalCancelBtn = $("#modal-cancel-btn");
  if (modalCancelBtn) modalCancelBtn.addEventListener("click", closeSettings);
  const modalApplyBtn = $("#modal-apply-btn");
  if (modalApplyBtn) modalApplyBtn.addEventListener("click", applySettings);

  const modalLoadDemoBtn = $("#modal-load-demo-btn");
  if (modalLoadDemoBtn) modalLoadDemoBtn.addEventListener("click", () => {
    closeSettings();
    loadDemo();
    showToast("🎲 Reset to Demo Data");
  });

  const modalUploadNavBtn = $("#modal-upload-nav-btn");
  if (modalUploadNavBtn) modalUploadNavBtn.addEventListener("click", () => {
    closeSettings();
    navigate("upload");
  });

  // Close modal when clicking backdrop
  const settingsModal = $("#settings-modal");
  if (settingsModal) {
    settingsModal.addEventListener("click", e => {
      if (e.target === settingsModal) closeSettings();
    });
  }

  // Close on Escape key
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeSettings();
  });

  // File input
  const fileInput = $("#file-input");
  if (fileInput) fileInput.addEventListener("change", e => { if (e.target.files[0]) uploadFile(e.target.files[0]); });

  // Drag-drop
  const dropArea = $("#drop-area");
  if (dropArea) {
    ["dragenter", "dragover"].forEach(ev => dropArea.addEventListener(ev, e => { e.preventDefault(); dropArea.classList.add("drag"); }));
    ["dragleave", "drop"].forEach(ev => dropArea.addEventListener(ev, e => { e.preventDefault(); dropArea.classList.remove("drag"); }));
    dropArea.addEventListener("drop", e => { const f = e.dataTransfer.files[0]; if (f) uploadFile(f); });
    dropArea.addEventListener("click", () => fileInput && fileInput.click());
  }

  // Mobile menu
  const menuToggle = $("#menu-toggle");
  if (menuToggle) menuToggle.addEventListener("click", () => $("#sidebar").classList.toggle("open"));

  // Nav links
  $$(".nav-link").forEach(link => {
    link.addEventListener("click", () => {
      const page = link.dataset.page;
      if (!page) return; // ignore buttons like nav-settings that don't have data-page
      if (page === "subscriptions") { navigate("spending"); renderSubscriptions(); return; }
      navigate(page);
    });
  });

  // Load user and initial data on start
  async function initApp() {
    await loadCurrentUser();
    try {
      const aRes = await fetch("/api/analyse");
      if (aRes.ok) {
        const aJson = await aRes.json();
        if (aJson.ok && aJson.data && aJson.data.source !== "demo") {
          STATE.data = aJson.data;
          STATE.source = aJson.data.source || "upload";
          STATE.dismissed = new Set();
          renderAll();
          return;
        }
      }
    } catch (e) {
      console.warn("Could not check active dataset on startup:", e);
    }

    try {
      const res = await fetch("/api/history");
      if (res.ok) {
        const json = await res.json();
        if (json.ok && json.statements && json.statements.length > 0) {
          await loadStatementAnalysis(json.statements[0].id);
          return;
        }
      }
    } catch (e) {
      console.warn("Could not check history on startup:", e);
    }
    loadDemo();
  }

  initApp();
});

