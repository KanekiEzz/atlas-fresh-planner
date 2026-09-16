const state = {
  view: "overview",
  plan: null,
  status: "No data",
  busy: false,
  error: null,
  validationErrors: [],
  filters: { farm: "ALL", segment: "ALL", client: "ALL", upgrade: "ALL" },
  assistant: { loading: false, answer: null, error: null },
};

const QUESTIONS = [
  "Which clients are at risk and why?",
  "Which farm/segment gaps matter most today?",
  "Why are 60 t going local and what is their estimated value?",
];

const app = document.getElementById("app");
const dataStatus = document.getElementById("dataStatus");

const fmtT = (value) => `${Number(value || 0).toFixed(1)} t`;
const fmtPct = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
const fmtEur = (value) => `EUR ${Number(value || 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const signedT = (value) => `${value > 0 ? "+" : ""}${Number(value || 0).toFixed(1)} t`;
const cssVar = (value) => (value < 0 ? "neg" : "pos");
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));

function setBusy(label) {
  state.busy = true;
  state.status = label;
  render();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.message || payload.error || "Server error");
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

async function loadWorkbook() {
  setBusy("Loading workbook");
  try {
    await api("/api/data/load", { method: "POST" });
    state.status = "Validated";
    state.error = null;
    state.validationErrors = [];
    await recalculatePlan();
  } catch (error) {
    state.busy = false;
    if (error.status === 422) {
      state.status = "Validation failed";
      state.validationErrors = error.payload.errors || [];
    } else {
      state.status = "Server error";
      state.error = error.message;
    }
    render();
  }
}

async function recalculatePlan() {
  setBusy("Calculating plan");
  try {
    const payload = await api("/api/plan", { method: "POST" });
    state.plan = payload.plan;
    state.status = "Plan calculated";
    state.error = null;
    state.validationErrors = [];
  } catch (error) {
    if (error.status === 422) {
      state.status = "Validation failed";
      state.validationErrors = error.payload.errors || [];
    } else {
      state.status = "Server error";
      state.error = error.message;
    }
  } finally {
    state.busy = false;
    render();
  }
}

function resetUi() {
  state.plan = null;
  state.error = null;
  state.validationErrors = [];
  state.assistant = { loading: false, answer: null, error: null };
  state.status = "No data";
  render();
}

function updateChrome() {
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.view === state.view));
  dataStatus.textContent = state.busy ? state.status : state.status;
  dataStatus.className = `status-dot ${state.status.includes("failed") || state.status.includes("error") ? "warn" : state.plan ? "good" : ""}`;
}

function render() {
  updateChrome();
  if (state.validationErrors.length) {
    app.innerHTML = renderValidationError();
    bindCommonActions();
    return;
  }
  if (state.error) {
    app.innerHTML = renderServerError();
    bindCommonActions();
    return;
  }
  if (!state.plan) {
    app.innerHTML = renderEmpty();
    bindCommonActions();
    return;
  }

  const views = {
    overview: renderOverview,
    production: renderProduction,
    commercial: renderCommercial,
    allocations: renderAllocations,
    assistant: renderAssistant,
  };
  app.innerHTML = views[state.view]();
  bindViewActions();
}

function pageHead(title, subtitle, right = "") {
  return `
    <div class="page-head">
      <div>
        <h1>${title}</h1>
        <p class="subtitle">${subtitle}</p>
      </div>
      <div class="warning-facts">${right}</div>
    </div>
  `;
}

function renderEmpty() {
  return `
    <section class="empty">
      <div>
        <span class="eyebrow">Initial state</span>
        <h1>Daily Export Plan</h1>
        <p class="subtitle">Production x Commercial decision workspace</p>
      </div>
      <p>Load and validate the supplied workbook, then calculate the deterministic export allocation.</p>
      <div class="toolbar">
        <button class="primary" data-action="load">Load Workbook</button>
        <button data-action="recalc">Recalculate Plan</button>
      </div>
    </section>
  `;
}

function renderValidationError() {
  return `
    <section class="error">
      <div>
        <span class="eyebrow">Data validation failed</span>
        <h1>Workbook rejected</h1>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Sheet</th><th>ID</th><th>Field</th><th>Problem</th></tr></thead>
          <tbody>${state.validationErrors.map((error) => `<tr><td>${esc(error.sheet)}</td><td>${esc(error.entity_id)}</td><td>${esc(error.field)}</td><td>${esc(error.problem)}</td></tr>`).join("")}</tbody>
        </table>
      </div>
      <div class="toolbar">
        <button class="primary" data-action="load">Retry</button>
        <button data-action="reset">Reset</button>
      </div>
    </section>
  `;
}

function renderServerError() {
  return `
    <section class="error">
      <span class="eyebrow">Server error</span>
      <h1>Calculation unavailable</h1>
      <p>${esc(state.error)}</p>
      <div class="toolbar">
        <button class="primary" data-action="recalc">Retry</button>
        <button data-action="reset">Reset</button>
      </div>
    </section>
  `;
}

function renderOverview() {
  const p = state.plan;
  const atRisk = p.clients.filter((client) => client.status !== "COMPLETE");
  return `
    ${pageHead("Daily Export Plan", "Production x Commercial decision workspace", `
      <span class="chip">Data health ${p.data_health}</span>
      <span class="chip">Last calculation ${state.status}</span>
      <span class="chip">${p.farms_count} farms</span>
      <span class="chip">${p.clients_count} clients</span>
    `)}
    <section class="grid kpis">
      ${metric("Planned", fmtT(p.expected_total_t))}
      ${metric("Actual received", fmtT(p.actual_total_t))}
      ${metric("Export capacity", fmtT(p.station_capacity_t))}
      ${metric("Exported", fmtT(p.exported_t))}
      ${metric("Export rate", fmtPct(p.export_rate))}
      ${metric("Local residual", fmtT(p.local_t), true)}
    </section>
    <section class="value-strip" aria-label="Value summary">
      <div><span>Export revenue</span><strong>${fmtEur(p.export_revenue_eur)}</strong></div>
      <div><span>Local value</span><strong>${fmtEur(p.local_value_eur)}</strong></div>
      <div><span>Total value</span><strong>${fmtEur(p.total_value_eur)}</strong></div>
    </section>
    <section class="local-warning">
      <span class="eyebrow">Local-market warning</span>
      <h2>${Number(p.local_t).toFixed(0)} t going to local market</h2>
      <div class="warning-facts">
        <span class="chip hot">${fmtT(p.local_t)} local</span>
        <span class="chip hot">${fmtEur(p.local_value_eur)} estimated local value</span>
        <span class="chip">10% of segment reference export price</span>
        <span class="chip">${p.exported_t >= p.station_capacity_t ? "Station capacity is the main constraint" : "Compatible export demand exhausted"}</span>
      </div>
      <p class="subtitle">Every remaining actual tonne is routed to local market after compatible demand and the ${fmtT(p.station_capacity_t)} export line are consumed.</p>
    </section>
    <section class="grid two">
      <div class="panel">
        <h2>Production vs actual</h2>
        <div class="warning-facts">
          <span class="chip">Expected ${fmtT(p.expected_total_t)}</span>
          <span class="chip hot">Variance ${signedT(p.production_variance_t)}</span>
          ${Object.entries(p.actual_by_segment_t).map(([seg, val]) => `<span class="chip">${seg}: ${fmtT(val)}</span>`).join("")}
        </div>
        <p class="subtitle"><strong>Segment A is below plan by ${Math.abs(p.segment_variance_t.A).toFixed(1)} t.</strong></p>
      </div>
      <div class="panel">
        <h2>Client risk</h2>
        <div class="warning-facts">
          <span class="chip">${p.clients.length} clients</span>
          <span class="chip hot">${atRisk.length} at risk</span>
        </div>
        ${atRisk.map((client) => `<p><strong>${client.client_id}</strong> - ${client.status} - ${client.shortage_reason}</p>`).join("")}
      </div>
    </section>
    <section class="panel" style="margin-top:14px">
      <h2>Allocation/value explanation</h2>
      <p class="subtitle">${fmtT(p.exported_t)} exported through traceable farm-segment allocations, protecting ${fmtEur(p.export_revenue_eur)}. ${fmtT(p.local_t)} remains local by farm and segment with ${fmtEur(p.local_value_eur)} estimated value.</p>
    </section>
  `;
}

function metric(label, value, warning = false) {
  return `<div class="panel metric ${warning ? "warning" : ""}"><span>${label}</span><strong>${value}</strong></div>`;
}

function renderProduction() {
  const p = state.plan;
  return `
    ${pageHead("Production", "What changed versus plan?", `
      <span class="chip">Expected ${fmtT(p.expected_total_t)}</span>
      <span class="chip">Actual ${fmtT(p.actual_total_t)}</span>
      <span class="chip hot">Variance ${signedT(p.production_variance_t)}</span>
    `)}
    <section class="panel">
      <h2>Production snapshot</h2>
      <div class="warning-facts">
        ${Object.entries(p.actual_by_segment_t).map(([seg, val]) => `<span class="chip">${seg}: actual ${fmtT(val)}</span>`).join("")}
        <span class="chip hot">Segment A below plan by ${Math.abs(p.segment_variance_t.A).toFixed(1)} t</span>
      </div>
    </section>
    <section class="panel" style="margin-top:14px">
      <h2>What matters today</h2>
      <div class="warning-facts">${p.production_alerts.map((alert) => `<button class="chip ${alert.severity === "important" ? "hot" : ""}" data-impact="${alert.farm_id ? `${alert.farm_id}:${alert.segment}` : ""}">${esc(alert.label)} | ${esc(alert.detail)}</button>`).join("")}</div>
    </section>
    <section style="margin-top:14px" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Farm</th><th class="num">Expected Capacity</th><th class="num">Actual Total</th><th class="num">Variance</th>
            ${["A", "B", "C", "D"].map((seg) => `<th class="num">Expected ${seg}</th><th class="num">Actual ${seg}</th><th class="num">${seg} Var</th>`).join("")}
            <th class="num">Local Residual</th>
          </tr>
        </thead>
        <tbody>
          ${p.farms.map((farm) => `
            <tr>
              <td><strong>${farm.farm_id}</strong><br><span class="muted">${esc(farm.farm_name)}</span></td>
              <td class="num">${fmtT(farm.expected_capacity_t)}</td>
              <td class="num">${fmtT(farm.actual_total_t)}</td>
              <td class="num ${cssVar(farm.variance_t)}">${signedT(farm.variance_t)}</td>
              ${["A", "B", "C", "D"].map((seg) => {
                const row = farm.segments[seg];
                return `<td class="num">${fmtT(row.expected_t)}</td><td class="num">${fmtT(row.actual_t)}</td><td class="num"><button class="click-var ${cssVar(row.variance_t)}" data-impact="${farm.farm_id}:${seg}">${signedT(row.variance_t)}</button></td>`;
              }).join("")}
              <td class="num ${farm.local_residual_t > 0 ? "neg" : ""}">${fmtT(farm.local_residual_t)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </section>
  `;
}

function renderCommercial() {
  const p = state.plan;
  const atRisk = p.clients.filter((client) => client.status !== "COMPLETE");
  return `
    ${pageHead("Commercial", "Which clients are at risk?", `<span class="chip">${p.clients.length} clients</span><span class="chip hot">${atRisk.length} at risk</span>`)}
    <section class="table-wrap">
      <table>
        <thead><tr><th>Client</th><th>Quality Rule</th><th class="num">Demand</th><th class="num">Allocated</th><th class="num">Remaining</th><th class="num">Revenue</th><th>Status</th><th>Shortage Reason</th></tr></thead>
        <tbody>
          ${p.clients.map((client) => `
            <tr>
              <td><strong>${client.client_id}</strong><br><span class="muted">${esc(client.client_name)}</span></td>
              <td>${client.acceptance_mode} ${client.requested_segment}</td>
              <td class="num">${fmtT(client.demand_t)}</td>
              <td class="num">${fmtT(client.allocated_t)}</td>
              <td class="num ${client.remaining_t > 0 ? "neg" : ""}">${fmtT(client.remaining_t)}</td>
              <td class="num">${fmtEur(client.export_revenue_eur)}</td>
              <td><span class="status ${client.status}">${client.status}</span></td>
              <td>${client.shortage_reason ? `<code>${client.shortage_reason}</code>` : "-"}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </section>
  `;
}

function renderAllocations() {
  const p = state.plan;
  const farms = [...new Set(p.allocations.map((row) => row.farm_id).concat(p.local_residuals.map((row) => row.farm_id)))].sort();
  const clients = [...new Set(p.allocations.map((row) => row.client_id))].sort();
  const rows = p.allocations.filter((row) =>
    (state.filters.farm === "ALL" || row.farm_id === state.filters.farm) &&
    (state.filters.segment === "ALL" || row.segment === state.filters.segment) &&
    (state.filters.client === "ALL" || row.client_id === state.filters.client) &&
    (state.filters.upgrade === "ALL" || row.quality_upgrade === state.filters.upgrade)
  );
  return `
    ${pageHead("Allocations", "Which farm and segment serves which client?", `<span class="chip">${fmtT(p.exported_t)} exported</span><span class="chip hot">${fmtT(p.local_t)} local residual</span>`)}
    <div class="toolbar">
      ${select("farm", farms)}
      ${select("segment", ["A", "B", "C", "D"])}
      ${select("client", clients)}
      ${select("upgrade", ["EXACT", "UPGRADED"], "Exact / Upgraded")}
    </div>
    <section class="panel">
      <h2>Export allocations</h2>
      <div class="table-wrap" style="margin-top:12px">
        <table>
          <thead><tr><th>Farm ID</th><th>Segment</th><th>Client ID</th><th class="num">Tonnes</th><th>Quality Upgrade</th><th class="num">Export Price</th><th class="num">Export Revenue</th></tr></thead>
          <tbody>${rows.map((row) => `<tr><td>${row.farm_id}</td><td>${row.segment}</td><td>${row.client_id}</td><td class="num">${fmtT(row.tonnes)}</td><td>${row.quality_upgrade}</td><td class="num">${fmtEur(row.export_price_per_t_eur)}</td><td class="num">${fmtEur(row.export_revenue_eur)}</td></tr>`).join("")}</tbody>
        </table>
      </div>
    </section>
    <section class="panel" style="margin-top:14px">
      <h2>Local residual</h2>
      <div class="table-wrap" style="margin-top:12px">
        <table>
          <thead><tr><th>Farm</th><th>Segment</th><th class="num">Tonnes</th><th class="num">Reference price</th><th class="num">Local value</th></tr></thead>
          <tbody>${p.local_residuals.map((row) => `<tr><td>${row.farm_id}</td><td>${row.segment}</td><td class="num neg">${fmtT(row.tonnes)}</td><td class="num">${fmtEur(row.reference_price_per_t_eur)}</td><td class="num">${fmtEur(row.local_value_eur)}</td></tr>`).join("")}</tbody>
        </table>
      </div>
    </section>
  `;
}

function select(name, options, label) {
  return `
    <label>
      <span class="eyebrow">${label || name[0].toUpperCase() + name.slice(1)}</span>
      <select data-filter="${name}">
        <option value="ALL">All</option>
        ${options.map((option) => `<option value="${option}" ${state.filters[name] === option ? "selected" : ""}>${option}</option>`).join("")}
      </select>
    </label>
  `;
}

function renderAssistant() {
  const response = state.assistant.answer;
  return `
    ${pageHead("Planning Assistant", "Grounded explanation of the calculated plan")}
    <section class="assistant-shell">
      <div class="panel">
        <h2>Suggested questions</h2>
        <div class="question-list" style="margin-top:12px">
          ${QUESTIONS.map((question) => `<button data-question="${esc(question)}">${question}</button>`).join("")}
        </div>
        <div class="toolbar">
          <input id="customQuestion" placeholder="Ask from current planning data" />
          <button data-action="ask-custom">Ask</button>
        </div>
      </div>
      <div class="panel answer">
        ${state.assistant.loading ? `<h2>Thinking from calculated data...</h2>` : ""}
        ${state.assistant.error ? `<div class="error" style="margin:0"><h2>${esc(state.assistant.error.title)}</h2><p>${esc(state.assistant.error.message)}</p><button data-action="assistant-retry">Retry</button></div>` : ""}
        ${response ? `
          <div>
            <span class="eyebrow">${esc(response.provider_state || "Deterministic summary")}</span>
            <h2>${response.mode === "deterministic" ? "Deterministic summary" : "Assistant response"}</h2>
          </div>
          <p>${esc(response.answer)}</p>
          <div class="warning-facts">${(response.evidence || []).map((item) => `<span class="chip ${String(item).startsWith("C0") || String(item).includes("Segment A") ? "hot" : ""}">${esc(item)}</span>`).join("")}</div>
        ` : ""}
        ${!state.assistant.loading && !state.assistant.error && !response ? `<p class="subtitle">No AI provider configured. Deterministic summaries are generated from server-calculated results.</p>` : ""}
      </div>
    </section>
  `;
}

async function askAssistant(question) {
  state.assistant = { loading: true, answer: null, error: null, lastQuestion: question };
  render();
  try {
    const answer = await api("/api/assistant", { method: "POST", body: JSON.stringify({ question }) });
    state.assistant = { loading: false, answer, error: null, lastQuestion: question };
  } catch (error) {
    const payload = error.payload || {};
    const titles = {
      provider_timeout: "Assistant timeout",
      invalid_model_output: "Invalid model output",
      unsupported_question: "Unsupported question",
      bad_json: "Assistant request failed",
    };
    state.assistant = {
      loading: false,
      answer: null,
      error: { title: titles[payload.error] || "Assistant unavailable", message: payload.message || "This information is not available in the current planning data." },
      lastQuestion: question,
    };
  }
  render();
}

function bindCommonActions() {
  document.querySelectorAll("[data-action='load']").forEach((button) => button.addEventListener("click", loadWorkbook));
  document.querySelectorAll("[data-action='recalc']").forEach((button) => button.addEventListener("click", recalculatePlan));
  document.querySelectorAll("[data-action='reset']").forEach((button) => button.addEventListener("click", resetUi));
}

function bindViewActions() {
  bindCommonActions();
  document.querySelectorAll("[data-impact]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.impact;
      if (key) openImpact(key);
    });
  });
  document.querySelectorAll("[data-filter]").forEach((selectEl) => {
    selectEl.addEventListener("change", () => {
      state.filters[selectEl.dataset.filter] = selectEl.value;
      render();
    });
  });
  document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => askAssistant(button.dataset.question)));
  document.querySelectorAll("[data-action='ask-custom']").forEach((button) => button.addEventListener("click", () => askAssistant(document.getElementById("customQuestion").value)));
  document.querySelectorAll("[data-action='assistant-retry']").forEach((button) => button.addEventListener("click", () => askAssistant(state.assistant.lastQuestion || QUESTIONS[0])));
}

function openImpact(key) {
  const item = state.plan.impact[key];
  if (!item) return;
  document.getElementById("drawerTitle").textContent = `${item.farm_id} | Segment ${item.segment}`;
  document.getElementById("drawerBody").innerHTML = `
    <div class="stack">
      <div class="mini-grid">
        <div class="mini"><span>Farm / segment gap</span><strong class="${cssVar(item.variance_t)}">${signedT(item.variance_t)}</strong></div>
        <div class="mini"><span>Available compatible supply</span><strong>${fmtT(item.actual_t)}</strong></div>
        <div class="mini"><span>Allocated volume</span><strong>${fmtT(item.allocated_t)}</strong></div>
        <div class="mini"><span>Local residual</span><strong class="${item.local_t > 0 ? "neg" : ""}">${fmtT(item.local_t)}</strong></div>
      </div>
      <div class="panel">
        <h3>Affected client(s)</h3>
        <div class="warning-facts">${item.affected_clients.length ? item.affected_clients.map((client) => `<span class="chip hot">${client.client_id} | allocated ${fmtT(client.allocated_t)} | remaining ${fmtT(client.remaining_t)} | ${client.shortage_reason}</span>`).join("") : `<span class="chip">No at-risk client directly tied to this farm segment</span>`}</div>
      </div>
      <div class="panel">
        <h3>Trace allocations</h3>
        <div class="warning-facts">${item.allocations.length ? item.allocations.map((allocation) => `<span class="chip">${allocation.client_id} | ${fmtT(allocation.tonnes)} | ${allocation.quality_upgrade}</span>`).join("") : `<span class="chip">No export allocation</span>`}</div>
      </div>
    </div>
  `;
  document.getElementById("drawer").classList.add("open");
  document.getElementById("drawer").setAttribute("aria-hidden", "false");
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    state.view = tab.dataset.view;
    render();
  });
});
document.getElementById("loadBtn").addEventListener("click", loadWorkbook);
document.getElementById("recalcBtn").addEventListener("click", recalculatePlan);
document.getElementById("drawerClose").addEventListener("click", () => {
  document.getElementById("drawer").classList.remove("open");
  document.getElementById("drawer").setAttribute("aria-hidden", "true");
});
document.getElementById("drawer").addEventListener("click", (event) => {
  if (event.target.id === "drawer") {
    document.getElementById("drawerClose").click();
  }
});

render();
