"use client";

import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, IconButton } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Sheet } from "@/components/ui/sheet";
import { Table, TableWrap } from "@/components/ui/table";
import { cn } from "@/lib/utils";

const QUESTIONS = [
  "Which clients are at risk and why?",
  "Which farm/segment gaps matter most today?",
  "Why are 60 t going local and what is their estimated value?",
  "What is the total revenue impact of Segment A deficit?",
];

const TABS = [
  { id: "overview", label: "Overview", icon: "dashboard" },
  { id: "production", label: "Production", icon: "agriculture" },
  { id: "commercial", label: "Commercial", icon: "groups" },
  { id: "allocations", label: "Allocations", icon: "conversion_path" },
  { id: "assistant", label: "Assistant", icon: "psychology" },
];

const SEGMENTS = ["A", "B", "C", "D"];

const initialAssistant = { loading: false, answer: null, error: null, lastQuestion: null };
const initialFilters = { farm: "ALL", segment: "ALL", client: "ALL", upgrade: "ALL", search: "" };

const fmtT = (value) => `${Number(value || 0).toFixed(1)} t`;
const fmtPct = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
const fmtEur = (value) =>
  `EUR ${Number(value || 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const signedT = (value) => `${value > 0 ? "+" : ""}${Number(value || 0).toFixed(1)} t`;
const cssVar = (value) => (Number(value || 0) < 0 ? "neg" : "pos");

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

function Icon({ name, className, style }) {
  return (
    <span className={cn("material-symbols-rounded", className)} style={style} aria-hidden="true">
      {name}
    </span>
  );
}

function ProgressBar({ value, max, variant = "good" }) {
  const pct = Math.min(100, Math.max(0, max > 0 ? (value / max) * 100 : 0));
  return (
    <div className="progress-bar-bg" title={`${pct.toFixed(1)}%`}>
      <div
        className={cn(
          "progress-bar-fill",
          variant === "warn" && "warn",
          variant === "danger" && "danger"
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function PlannerPage() {
  const [view, setView] = useState("overview");
  const [plan, setPlan] = useState(null);
  const [status, setStatus] = useState("No data");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [validationErrors, setValidationErrors] = useState([]);
  const [filters, setFilters] = useState(initialFilters);
  const [assistant, setAssistant] = useState(initialAssistant);
  const [customQuestion, setCustomQuestion] = useState("");
  const [impactKey, setImpactKey] = useState(null);
  const [selectedClientTrace, setSelectedClientTrace] = useState(null);
  // const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [globalSearch, setGlobalSearch] = useState("");

  const selectedImpact = impactKey && plan?.impact ? plan.impact[impactKey] : null;
  const statusTone =
    status.toLowerCase().includes("failed") || status.toLowerCase().includes("error")
      ? "warn"
      : plan
        ? "good"
        : "";

  async function loadWorkbook() {
    setBusy(true);
    setStatus("Loading workbook");
    try {
      await api("/api/data/load", { method: "POST" });
      setStatus("Validated");
      setError(null);
      setValidationErrors([]);
      await recalculatePlan();
    } catch (loadError) {
      setBusy(false);
      if (loadError.status === 422) {
        setStatus("Validation failed");
        setValidationErrors(loadError.payload.errors || []);
      } else {
        setStatus("Server error");
        setError(loadError.message);
      }
    }
  }

  async function recalculatePlan() {
    setBusy(true);
    setStatus("Calculating plan");
    try {
      const payload = await api("/api/plan", { method: "POST" });
      setPlan(payload.plan);
      setStatus("Plan calculated");
      setError(null);
      setValidationErrors([]);
    } catch (planError) {
      if (planError.status === 422) {
        setStatus("Validation failed");
        setValidationErrors(planError.payload.errors || []);
      } else {
        setStatus("Server error");
        setError(planError.message);
      }
    } finally {
      setBusy(false);
    }
  }

  function resetUi() {
    setPlan(null);
    setError(null);
    setValidationErrors([]);
    setAssistant(initialAssistant);
    setFilters(initialFilters);
    setStatus("No data");
    setImpactKey(null);
    setSelectedClientTrace(null);
  }

  async function askAssistant(question) {
    const cleanQuestion = question.trim();
    if (!cleanQuestion) return;
    setAssistant({ loading: true, answer: null, error: null, lastQuestion: cleanQuestion });
    try {
      const answer = await api("/api/assistant", {
        method: "POST",
        body: JSON.stringify({ question: cleanQuestion }),
      });
      setAssistant({ loading: false, answer, error: null, lastQuestion: cleanQuestion });
    } catch (assistantError) {
      const payload = assistantError.payload || {};
      const titles = {
        provider_timeout: "Assistant timeout",
        invalid_model_output: "Invalid model output",
        unsupported_question: "Unsupported question",
        bad_json: "Assistant request failed",
      };
      setAssistant({
        loading: false,
        answer: null,
        error: {
          title: titles[payload.error] || "Assistant unavailable",
          message:
            payload.message || "This information is not available in the current planning data.",
        },
        lastQuestion: cleanQuestion,
      });
    }
  }

  const atRiskCount = useMemo(
    () => (plan ? plan.clients.filter((c) => c.status !== "COMPLETE").length : 0),
    [plan]
  );
  const alertsCount = useMemo(
    () => (plan ? plan.production_alerts?.length || 0 : 0),
    [plan]
  );

  let content;
  if (validationErrors.length) {
    content = (
      <ValidationError
        errors={validationErrors}
        onLoad={loadWorkbook}
        onReset={resetUi}
      />
    );
  } else if (error) {
    content = <ServerError error={error} onRecalc={recalculatePlan} onReset={resetUi} />;
  } else if (!plan) {
    content = <EmptyState onLoad={loadWorkbook} onRecalc={recalculatePlan} busy={busy} />;
  } else {
    const props = {
      plan,
      status,
      filters,
      setFilters,
      assistant,
      customQuestion,
      setCustomQuestion,
      askAssistant,
      openImpact: setImpactKey,
      openClientTrace: setSelectedClientTrace,
      globalSearch,
    };
    content = {
      overview: <Overview {...props} />,
      production: <Production {...props} />,
      commercial: <Commercial {...props} />,
      allocations: <Allocations {...props} />,
      assistant: <AssistantView {...props} />,
    }[view];
  }

  return (
    <div className="app-shell">
      <aside className="app-sidebar" aria-label="Atlas Fresh workspace">
        <div className="sidebar-brand">
          <span className="brand-mark">AF</span>
          <div>
            <strong>Atlas Fresh</strong>
            <span>Daily Export Planner</span>
          </div>
        </div>
        <SidebarNav
          view={view}
          setView={setView}
          atRiskCount={atRiskCount}
          alertsCount={alertsCount}
          farmsCount={plan?.farms_count}
        />
        <Card size="sm" className="sidebar-support min-w-0 max-w-full">
          <CardTitle>Decision Support</CardTitle>
          <CardContent className="min-w-0 max-w-full">
            <p className="subtitle text-black max-w-full break-words">
              Deterministic farm-to-client allocation & residual analytics.
            </p>
          </CardContent>
        </Card>
        <div className="sidebar-account">
          <span className="avatar">AF</span>
          <div>
            <strong>Operations Team</strong>
            <span>Production x Commercial</span>
          </div>
          <Icon name="tune" />
        </div>
      </aside>
      <section className="app-main">
        <header className="topbar">
          <div className="topbar-left">
            {/* <IconButton
              label="Toggle navigation"
              icon="menu"
              className="mobile-menu-button"
              // onClick={() => setMobileNavOpen((open) => !open)}
            /> */}
            <div className="search-pill" aria-label="Current workspace">
              <Icon name="search" />
              <input
                type="text"
                placeholder="Search farms, clients, segments..."
                value={globalSearch}
                onChange={(e) => setGlobalSearch(e.target.value)}
              />
              <kbd>/</kbd>
            </div>
          </div>
          <div className="topbar-logo" aria-label="Atlas Fresh">
            <span className="brand-mark">AF</span>
            <div>
              <strong>Atlas Fresh</strong>
              <span>Daily Export Planner</span>
            </div>
          </div>
          <div className="actions">
            <span className={cn("status-dot", statusTone)}>
              {busy ? "Processing..." : status}
            </span>
            <Button variant="secondary" onClick={loadWorkbook} disabled={busy}>
              <Icon name="upload_file" />
              Load Data
            </Button>
            <Button onClick={recalculatePlan} disabled={busy}>
              <Icon name={busy ? "sync" : "refresh"} className={busy ? "spin" : ""} />
              Recalculate
            </Button>
          </div>
        </header>
        <main className="workspace" tabIndex={-1}>
          {content}
        </main>
      </section>

      {/* Farm Segment Impact Sheet */}
      <Sheet
        open={Boolean(selectedImpact)}
        onClose={() => setImpactKey(null)}
        eyebrow="Root Cause Analysis"
        title={
          selectedImpact
            ? `${selectedImpact.farm_id} | Segment ${selectedImpact.segment}`
            : "Farm Segment Impact"
        }
      >
        {selectedImpact ? <ImpactDrawer item={selectedImpact} /> : null}
      </Sheet>

      {/* Client Allocation Trace Sheet */}
      <Sheet
        open={Boolean(selectedClientTrace)}
        onClose={() => setSelectedClientTrace(null)}
        eyebrow="Commercial Fulfillment Trace"
        title={
          selectedClientTrace
            ? `${selectedClientTrace.client_id} (${selectedClientTrace.client_name})`
            : "Client Allocation"
        }
      >
        {selectedClientTrace ? (
          <ClientTraceDrawer client={selectedClientTrace} plan={plan} />
        ) : null}
      </Sheet>
    </div>
  );
}

function SidebarNav({ view, setView, atRiskCount, alertsCount, farmsCount, compact = false }) {
  return (
    <div className={cn("sidebar-nav", compact && "is-compact")}>
      <span className="sidebar-group-label">Workspace</span>
      <div className="sidebar-menu">
        {TABS.map((tab) => {
          let badge = null;
          if (tab.id === "production" && alertsCount > 0) {
            badge = `${alertsCount} alerts`;
          } else if (tab.id === "commercial" && atRiskCount > 0) {
            badge = `${atRiskCount} at risk`;
          } else if (tab.id === "assistant") {
            badge = "AI";
          }
          return (
            <button
              key={tab.id}
              className={cn("sidebar-item", view === tab.id && "is-active")}
              onClick={() => setView(tab.id)}
              type="button"
            >
              <div className="sidebar-item-label">
                <Icon name={tab.icon} />
                <span>{tab.label}</span>
              </div>
              {badge ? <span className="nav-badge">{badge}</span> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function PageHead({ title, subtitle, children }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        <p className="subtitle">{subtitle}</p>
      </div>
      {children ? <div className="warning-facts">{children}</div> : null}
    </div>
  );
}

function Metric({ label, value, subtext, icon, warning = false, progress = null }) {
  return (
    <Card className={cn("metric", warning && "warning")}>
      <div className="metric-header">
        <span>{label}</span>
        {icon ? <span className="metric-icon"><Icon name={icon} /></span> : null}
      </div>
      <strong>{value}</strong>
      {progress !== null ? (
        <div style={{ marginTop: 6 }}>
          <ProgressBar value={progress} max={100} variant={warning ? "warn" : "good"} />
        </div>
      ) : subtext ? (
        <span style={{ fontSize: 11, color: "var(--black)", fontWeight: 600, marginTop: 4 }}>{subtext}</span>
      ) : null}
    </Card>
  );
}

function EmptyState({ onLoad, onRecalc, busy }) {
  return (
    <section className="empty">
      <div>
        <span className="eyebrow">Decision Support Workspace</span>
        <h1>Daily Export Planner</h1>
        <p className="subtitle">Atlas Fresh Production x Commercial Daily Allocation Workspace</p>
      </div>
      <p>
        Load and validate the workbook, then calculate the deterministic farm-to-client export allocation
        and local residual distribution.
      </p>
      <div className="toolbar">
        <Button onClick={onLoad} disabled={busy}>
          <Icon name="upload_file" />
          Load Workbook Data
        </Button>
        <Button variant="secondary" onClick={onRecalc} disabled={busy}>
          <Icon name="refresh" />
          Recalculate Plan
        </Button>
      </div>
    </section>
  );
}

function ValidationError({ errors, onLoad, onReset }) {
  return (
    <section className="error-state">
      <div>
        <span className="eyebrow">Data Validation Error</span>
        <h1>Workbook Validation Failed</h1>
      </div>
      <TableWrap>
        <Table>
          <thead>
            <tr>
              <th>Sheet</th>
              <th>Entity ID</th>
              <th>Field</th>
              <th>Issue Description</th>
            </tr>
          </thead>
          <tbody>
            {errors.map((item, index) => (
              <tr key={`${item.sheet}-${item.entity_id}-${item.field}-${index}`}>
                <td><code>{item.sheet}</code></td>
                <td><strong>{item.entity_id}</strong></td>
                <td>{item.field}</td>
                <td className="neg">{item.problem}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </TableWrap>
      <div className="toolbar">
        <Button onClick={onLoad}>
          <Icon name="replay" />
          Re-validate Workbook
        </Button>
        <Button variant="secondary" onClick={onReset}>
          <Icon name="restart_alt" />
          Reset Workspace
        </Button>
      </div>
    </section>
  );
}

function ServerError({ error, onRecalc, onReset }) {
  return (
    <section className="error-state">
      <span className="eyebrow">Backend Service Error</span>
      <h1>Calculation Service Unavailable</h1>
      <p>{error}</p>
      <div className="toolbar">
        <Button onClick={onRecalc}>
          <Icon name="replay" />
          Retry Calculation
        </Button>
        <Button variant="secondary" onClick={onReset}>
          <Icon name="restart_alt" />
          Reset Workspace
        </Button>
      </div>
    </section>
  );
}

function Overview({ plan, status, openImpact, openClientTrace }) {
  const atRisk = plan.clients.filter((client) => client.status !== "COMPLETE");
  const exportPct = ((plan.exported_t / plan.actual_total_t) * 100).toFixed(1);
  const exportRevPct = (
    (plan.export_revenue_eur / (plan.total_value_eur || 1)) *
    100
  ).toFixed(1);

  return (
    <>
      <PageHead title="Daily Export Plan Overview" subtitle="Production x Commercial decision dashboard">
        <Badge variant="yellow">
          <Icon name="verified" /> Data Health: {plan.data_health}
        </Badge>
        <Badge variant="black">
          <Icon name="schedule" /> Status: {status}
        </Badge>

        <Badge variant="default">
          <Icon name="agriculture" /> {plan.farms_count} Farms
        </Badge>
        <Badge variant="default">
          <Icon name="groups" /> {plan.clients_count} Clients
        </Badge>
      </PageHead>

      <section className="grid kpis">
        <Metric
          label="Planned Total"
          value={fmtT(plan.expected_total_t)}
          icon="event_note"
          subtext="Expected harvest mix"
        />
        <Metric
          label="Actual Harvested"
          value={fmtT(plan.actual_total_t)}
          icon="agriculture"
          subtext={`Variance: ${signedT(plan.production_variance_t)}`}
        />
        <Metric
          label="Station Capacity"
          value={fmtT(plan.station_capacity_t)}
          icon="precision_manufacturing"
          subtext="Max daily throughput line"
        />
        <Metric
          label="Export Allocated"
          value={fmtT(plan.exported_t)}
          icon="local_shipping"
          subtext={`${exportPct}% of harvest exported`}
        />
        <Metric
          label="Export Fulfillment"
          value={fmtPct(plan.export_rate)}
          icon="speed"
          progress={plan.export_rate * 100}
        />
        <Metric
          label="Local Residual"
          value={fmtT(plan.local_t)}
          icon="storefront"
          warning
          subtext="Unexported surplus"
        />
      </section>

      {/* Financial Value Summary Card */}
      <section className="value-strip" aria-label="Value summary">
        <div>
          <span>
            <Icon name="payments" /> Export Revenue
          </span>
          <strong>{fmtEur(plan.export_revenue_eur)}</strong>
          <span style={{ fontSize: 11, marginTop: 4, color: "var(--black)", fontWeight: 700 }}>
            {exportRevPct}% of total daily value
          </span>
        </div>
        <div>
          <span>
            <Icon name="storefront" /> Local Market Value
          </span>
          <strong>{fmtEur(plan.local_value_eur)}</strong>
          <span style={{ fontSize: 11, marginTop: 4, color: "var(--black)", fontWeight: 700 }}>
            10% reference price estimate
          </span>
        </div>
        <div>
          <span>
            <Icon name="account_balance_wallet" /> Total Realized Value
          </span>
          <strong>{fmtEur(plan.total_value_eur)}</strong>
          <span style={{ fontSize: 11, marginTop: 4, color: "var(--muted)" }}>
            Export revenue + local value
          </span>
        </div>
      </section>

      {/* Revenue Distribution Bar */}
      <Card size="sm" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, fontWeight: 700 }}>
          <span>
            Export Revenue: {fmtEur(plan.export_revenue_eur)} ({exportRevPct}%)
          </span>
          <span>
            Local Market Value: {fmtEur(plan.local_value_eur)} ({(100 - exportRevPct).toFixed(1)}%)
          </span>
        </div>
        <div className="progress-bar-bg" style={{ height: 10 }}>
          <div
            className="progress-bar-fill"
            style={{ width: `${exportRevPct}%`, float: "left" }}
          />
        </div>
      </Card>

      {/* Local Market Residual Warning Banner */}
      <section className="local-warning">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="warning" style={{ fontSize: 24 }} />
          <h2>{Number(plan.local_t).toFixed(0)} Tonnes Rerouted to Local Market</h2>
        </div>
        <div className="warning-facts">
          <Badge variant="black">{fmtT(plan.local_t)} Local Residual</Badge>
          <Badge variant="black">{fmtEur(plan.local_value_eur)} Local Realized Value</Badge>
          <Badge variant="default">10% Segment Reference Export Price</Badge>
          <Badge variant="default">
            {plan.exported_t >= plan.station_capacity_t
              ? "Station 500 t/day capacity limit reached"
              : "Compatible export client demand exhausted"}
          </Badge>
        </div>
        <p className="subtitle" style={{ color: "var(--black)", fontWeight: 600 }}>
          Every remaining actual tonne is routed to local market after fulfilling compatible client demand
          and respecting the {fmtT(plan.station_capacity_t)} conditioning station line throughput.
        </p>
      </section>

      <section className="grid two">
        <Card>
          <CardHeader>
            <CardTitle>Production vs Plan Summary</CardTitle>
          </CardHeader>
          <div className="warning-facts">
            <Badge variant="default">Expected: {fmtT(plan.expected_total_t)}</Badge>
            <Badge variant="yellow">Variance: {signedT(plan.production_variance_t)}</Badge>
            {Object.entries(plan.actual_by_segment_t).map(([segment, value]) => (
              <Badge key={segment} variant={segment === "A" ? "yellow" : "default"}>
                Segment {segment}: {fmtT(value)}
              </Badge>
            ))}
          </div>
          <div
            style={{
              padding: 12,
              borderRadius: 10,
              background: "var(--yellow)",
              border: "2px solid var(--black)",
              marginTop: 10,
            }}
          >
            <span style={{ fontSize: 13, color: "var(--black)", fontWeight: 800 }}>
              <Icon name="info" style={{ verticalAlign: "middle", marginRight: 4 }} />
              Segment A is below plan by {Math.abs(plan.segment_variance_t.A).toFixed(1)} t.
            </span>
          </div>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Client Shortage Risk ({atRisk.length} At Risk)</CardTitle>
          </CardHeader>
          <div style={{ display: "grid", gap: 10 }}>
            {atRisk.map((client) => (
              <div
                key={client.client_id}
                onClick={() => openClientTrace(client)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: 10,
                  borderRadius: 10,
                  background: "var(--surface)",
                  cursor: "pointer",
                  border: "2px solid var(--black)",
                }}
              >
                <div>
                  <strong style={{ fontSize: 14 }}>{client.client_id}</strong>
                  <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 8 }}>
                    {client.client_name}
                  </span>
                  <div style={{ fontSize: 11, color: "var(--black)", fontWeight: 800, marginTop: 2 }}>
                    Shortage: {fmtT(client.remaining_t)} ({client.shortage_reason})
                  </div>
                </div>
                <Badge variant={client.status === "UNSERVED" ? "black" : "yellow"}>
                  {client.status}
                </Badge>
              </div>
            ))}
          </div>
        </Card>
      </section>

      <Card style={{ marginTop: 16 }}>
        <CardHeader>
          <CardTitle>Deterministic Allocation & Value Explanation</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="subtitle">
            {fmtT(plan.exported_t)} exported through traceable farm-segment allocations, generating{" "}
            {fmtEur(plan.export_revenue_eur)} export revenue. {fmtT(plan.local_t)} residual fruit remains
            for local distribution with {fmtEur(plan.local_value_eur)} estimated realization.
          </p>
        </CardContent>
      </Card>
    </>
  );
}

function Production({ plan, openImpact, globalSearch }) {
  const [search, setSearch] = useState("");
  const [filterMode, setFilterMode] = useState("ALL");

  const activeSearch = search || globalSearch;

  const filteredFarms = useMemo(() => {
    return plan.farms.filter((farm) => {
      const matchSearch =
        !activeSearch ||
        farm.farm_id.toLowerCase().includes(activeSearch.toLowerCase()) ||
        farm.farm_name.toLowerCase().includes(activeSearch.toLowerCase());

      if (!matchSearch) return false;
      if (filterMode === "DEFICIT") return farm.variance_t < 0;
      if (filterMode === "RESIDUAL") return farm.local_residual_t > 0;
      return true;
    });
  }, [plan.farms, activeSearch, filterMode]);

  return (
    <>
      <PageHead title="Production Snapshot & Farm Breakdown" subtitle="What changed versus pre-season plan?">
        <Badge variant="default">Expected: {fmtT(plan.expected_total_t)}</Badge>
        <Badge variant="default">Actual: {fmtT(plan.actual_total_t)}</Badge>
        <Badge variant="yellow">Production Variance: {signedT(plan.production_variance_t)}</Badge>
      </PageHead>

      {/* Segment Summary Cards */}
      <section className="grid kpis segment-kpis">
        {SEGMENTS.map((segment) => {
          const actual = plan.actual_by_segment_t[segment] || 0;
          const variance = plan.segment_variance_t[segment] || 0;
          return (
            <Card key={segment} size="sm">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="eyebrow">Segment {segment}</span>
                <Badge variant={variance < 0 ? "yellow" : "default"}>
                  {signedT(variance)}
                </Badge>
              </div>
              <strong style={{ fontSize: 24, marginTop: 4 }}>{fmtT(actual)}</strong>
              <span style={{ fontSize: 12, color: "var(--muted)" }}>Actual daily receipts</span>
            </Card>
          );
        })}
      </section>

      {/* Daily Production Alerts */}
      <Card style={{ marginTop: 16 }}>
        <CardHeader>
          <CardTitle>Daily Priority Alerts & Impact Triggers</CardTitle>
        </CardHeader>
        <div className="warning-facts">
          {plan.production_alerts.map((alert, index) => {
            const impactKey = alert.farm_id ? `${alert.farm_id}:${alert.segment}` : "";
            return (
              <Button
                key={`${alert.label}-${index}`}
                variant="outline"
                className={cn("ui-badge", alert.severity === "important" && "ui-badge-yellow")}
                onClick={() => impactKey && openImpact(impactKey)}
              >
                <Icon name="campaign" />
                {alert.label} | {alert.detail}
              </Button>
            );
          })}
        </div>
      </Card>

      {/* Toolbar & Filter Controls */}
      <div className="toolbar" style={{ marginTop: 16 }}>
        <div className="search-pill" style={{ width: 280 }}>
          <Icon name="search" />
          <input
            type="text"
            placeholder="Filter by farm name or ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <Button
            variant={filterMode === "ALL" ? "default" : "secondary"}
            size="sm"
            onClick={() => setFilterMode("ALL")}
          >
            All Farms ({plan.farms.length})
          </Button>
          <Button
            variant={filterMode === "DEFICIT" ? "default" : "secondary"}
            size="sm"
            onClick={() => setFilterMode("DEFICIT")}
          >
            Deficits Only
          </Button>
          <Button
            variant={filterMode === "RESIDUAL" ? "default" : "secondary"}
            size="sm"
            onClick={() => setFilterMode("RESIDUAL")}
          >
            Local Residuals Only
          </Button>
        </div>
      </div>

      {/* Production Matrix Table */}
      <TableWrap style={{ marginTop: 12 }}>
        <Table>
          <thead>
            <tr>
              <th>Farm</th>
              <th className="num">Expected Cap</th>
              <th className="num">Actual Total</th>
              <th className="num">Variance</th>
              {SEGMENTS.map((segment) => (
                <FarmSegmentHead key={segment} segment={segment} />
              ))}
              <th className="num">Local Residual</th>
            </tr>
          </thead>
          <tbody>
            {filteredFarms.map((farm) => (
              <tr key={farm.farm_id}>
                <td>
                  <strong>{farm.farm_id}</strong>
                  <br />
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>{farm.farm_name}</span>
                </td>
                <td className="num">{fmtT(farm.expected_capacity_t)}</td>
                <td className="num">{fmtT(farm.actual_total_t)}</td>
                <td className={cn("num", cssVar(farm.variance_t))}>
                  <strong>{signedT(farm.variance_t)}</strong>
                </td>
                {SEGMENTS.map((segment) => {
                  const row = farm.segments[segment];
                  return (
                    <FarmSegmentCells
                      key={`${farm.farm_id}-${segment}`}
                      farmId={farm.farm_id}
                      segment={segment}
                      row={row}
                      openImpact={openImpact}
                    />
                  );
                })}
                <td className={cn("num", farm.local_residual_t > 0 && "neg")}>
                  {farm.local_residual_t > 0 ? (
                    <Badge variant="yellow">{fmtT(farm.local_residual_t)}</Badge>
                  ) : (
                    "0.0 t"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </TableWrap>
    </>
  );
}

function FarmSegmentHead({ segment }) {
  return (
    <>
      <th className="num">Exp {segment}</th>
      <th className="num">Act {segment}</th>
      <th className="num">{segment} Var</th>
    </>
  );
}

function FarmSegmentCells({ farmId, segment, row, openImpact }) {
  return (
    <>
      <td className="num">{fmtT(row.expected_t)}</td>
      <td className="num">{fmtT(row.actual_t)}</td>
      <td className="num">
        <button
          className={cn("click-var", cssVar(row.variance_t))}
          onClick={() => openImpact(`${farmId}:${segment}`)}
          type="button"
          title={`Click to trace ${farmId} Segment ${segment}`}
        >
          {signedT(row.variance_t)}
        </button>
      </td>
    </>
  );
}

function Commercial({ plan, openClientTrace, globalSearch }) {
  const [search, setSearch] = useState("");
  const activeSearch = search || globalSearch;

  const atRisk = plan.clients.filter((client) => client.status !== "COMPLETE");

  const filteredClients = useMemo(() => {
    return plan.clients.filter(
      (c) =>
        !activeSearch ||
        c.client_id.toLowerCase().includes(activeSearch.toLowerCase()) ||
        c.client_name.toLowerCase().includes(activeSearch.toLowerCase())
    );
  }, [plan.clients, activeSearch]);

  return (
    <>
      <PageHead title="Commercial Program & Client Shortage Matrix" subtitle="Which export program orders are at risk?">
        <Badge variant="default">{plan.clients.length} Total Clients</Badge>
        <Badge variant="yellow">
          {plan.clients.length - atRisk.length} Fully Fulfilled
        </Badge>
        <Badge variant="black">{atRisk.length} Shortage at Risk</Badge>
      </PageHead>

      {/* At Risk Summary Card */}
      {atRisk.length > 0 ? (
        <Card style={{ marginBottom: 16, borderLeft: "8px solid var(--black)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Icon name="error" style={{ fontSize: 24 }} />
            <div>
              <h3>
                {atRisk.length} Clients Experiencing Volume Shortfalls
              </h3>
              <p className="subtitle">
                Segment A supply deficit directly restricts fulfillment for Segment A program clients.
              </p>
            </div>
          </div>
        </Card>
      ) : null}

      <div className="toolbar" style={{ marginBottom: 12 }}>
        <div className="search-pill" style={{ width: 300 }}>
          <Icon name="search" />
          <input
            type="text"
            placeholder="Search client ID or name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      <TableWrap>
        <Table>
          <thead>
            <tr>
              <th>Client Name</th>
              <th>Quality Rule</th>
              <th className="num">Demand</th>
              <th className="num">Allocated</th>
              <th style={{ width: 140 }}>Fulfillment %</th>
              <th className="num">Shortage</th>
              <th className="num">Revenue</th>
              <th>Status</th>
              <th>Shortage Reason</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredClients.map((client) => {
              const pct = (client.allocated_t / client.demand_t) * 100;
              return (
                <tr key={client.client_id}>
                  <td>
                    <strong>{client.client_id}</strong>
                    <br />
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>{client.client_name}</span>
                  </td>
                  <td>
                    <Badge variant="black">
                      {client.acceptance_mode} {client.requested_segment}
                    </Badge>
                  </td>
                  <td className="num">{fmtT(client.demand_t)}</td>
                  <td className="num">
                    <strong>{fmtT(client.allocated_t)}</strong>
                  </td>
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                      <span style={{ fontSize: 11, fontWeight: 700 }}>{pct.toFixed(1)}%</span>
                      <ProgressBar
                        value={client.allocated_t}
                        max={client.demand_t}
                        variant={client.status === "COMPLETE" ? "good" : "warn"}
                      />
                    </div>
                  </td>
                  <td className={cn("num", client.remaining_t > 0 && "neg")}>
                    {client.remaining_t > 0 ? signedT(-client.remaining_t) : "0.0 t"}
                  </td>
                  <td className="num">{fmtEur(client.export_revenue_eur)}</td>
                  <td>
                    <span className={cn("ui-badge", "status", client.status)}>
                      {client.status}
                    </span>
                  </td>
                  <td>{client.shortage_reason ? <code>{client.shortage_reason}</code> : "-"}</td>
                  <td>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openClientTrace(client)}
                    >
                      <Icon name="visibility" />
                      Trace
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </TableWrap>
    </>
  );
}

function Allocations({ plan, filters, setFilters, globalSearch }) {
  const [search, setSearch] = useState("");
  const activeSearch = search || globalSearch;

  const farms = useMemo(
    () =>
      [
        ...new Set(
          plan.allocations
            .map((row) => row.farm_id)
            .concat(plan.local_residuals.map((row) => row.farm_id))
        ),
      ].sort(),
    [plan]
  );
  const clients = useMemo(
    () => [...new Set(plan.allocations.map((row) => row.client_id))].sort(),
    [plan]
  );

  const rows = useMemo(() => {
    return plan.allocations.filter((row) => {
      const matchSearch =
        !activeSearch ||
        row.farm_id.toLowerCase().includes(activeSearch.toLowerCase()) ||
        row.client_id.toLowerCase().includes(activeSearch.toLowerCase()) ||
        row.segment.toLowerCase().includes(activeSearch.toLowerCase());

      if (!matchSearch) return false;
      return (
        (filters.farm === "ALL" || row.farm_id === filters.farm) &&
        (filters.segment === "ALL" || row.segment === filters.segment) &&
        (filters.client === "ALL" || row.client_id === filters.client) &&
        (filters.upgrade === "ALL" || row.quality_upgrade === filters.upgrade)
      );
    });
  }, [plan.allocations, filters, activeSearch]);

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  const totalFilteredTonnes = useMemo(
    () => rows.reduce((acc, r) => acc + r.tonnes, 0),
    [rows]
  );
  const totalFilteredRevenue = useMemo(
    () => rows.reduce((acc, r) => acc + r.export_revenue_eur, 0),
    [rows]
  );

  return (
    <>
      <PageHead title="Traceable Export Allocations & Local Residuals" subtitle="Exact farm-to-client match matrix">
        <Badge variant="yellow">{fmtT(plan.exported_t)} Export Allocated</Badge>
        <Badge variant="black">{fmtT(plan.local_t)} Local Residual</Badge>
        <Badge variant="default">{rows.length} Allocation Lines</Badge>
      </PageHead>

      {/* Filter Toolbar */}
      <div className="toolbar" style={{ background: "var(--white)", padding: 14, borderRadius: 12, border: "2px solid var(--black)" }}>
        <div className="search-pill" style={{ width: 220 }}>
          <Icon name="search" />
          <input
            type="text"
            placeholder="Search farm/client..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <FilterSelect label="Farm" value={filters.farm} options={farms} onChange={(value) => updateFilter("farm", value)} />
        <FilterSelect label="Segment" value={filters.segment} options={SEGMENTS} onChange={(value) => updateFilter("segment", value)} />
        <FilterSelect label="Client" value={filters.client} options={clients} onChange={(value) => updateFilter("client", value)} />
        <FilterSelect label="Quality Match" value={filters.upgrade} options={["EXACT", "UPGRADED"]} onChange={(value) => updateFilter("upgrade", value)} />

        {(filters.farm !== "ALL" || filters.segment !== "ALL" || filters.client !== "ALL" || filters.upgrade !== "ALL" || search) ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setFilters(initialFilters);
              setSearch("");
            }}
          >
            Clear Filters
          </Button>
        ) : null}
      </div>

      <Card style={{ marginTop: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <CardTitle>Export Allocations ({rows.length} records)</CardTitle>
          <div style={{ fontSize: 13, color: "var(--black)", fontWeight: 700 }}>
            Showing <strong>{fmtT(totalFilteredTonnes)}</strong> | <strong>{fmtEur(totalFilteredRevenue)}</strong>
          </div>
        </div>

        <TableWrap style={{ marginTop: 12 }}>
          <Table>
            <thead>
              <tr>
                <th>Farm ID</th>
                <th>Segment</th>
                <th>Client ID</th>
                <th className="num">Tonnes</th>
                <th>Quality Upgrade</th>
                <th className="num">Export Price</th>
                <th className="num">Export Revenue</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${row.farm_id}-${row.segment}-${row.client_id}-${index}`}>
                  <td><strong>{row.farm_id}</strong></td>
                  <td><Badge variant="default">Segment {row.segment}</Badge></td>
                  <td><strong>{row.client_id}</strong></td>
                  <td className="num"><strong>{fmtT(row.tonnes)}</strong></td>
                  <td>
                    <Badge variant={row.quality_upgrade === "EXACT" ? "yellow" : "black"}>
                      {row.quality_upgrade}
                    </Badge>
                  </td>
                  <td className="num">{fmtEur(row.export_price_per_t_eur)}/t</td>
                  <td className="num"><strong>{fmtEur(row.export_revenue_eur)}</strong></td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      </Card>

      {/* Local Residual Table */}
      <Card style={{ marginTop: 16 }}>
        <CardTitle>Local Market Residual Breakdown</CardTitle>
        <p className="subtitle">
          Actual volume unserved by export program due to line capacity or quality constraints.
        </p>
        <TableWrap style={{ marginTop: 12 }}>
          <Table>
            <thead>
              <tr>
                <th>Farm ID</th>
                <th>Segment</th>
                <th className="num">Local Tonnes</th>
                <th className="num">Reference Export Price</th>
                <th className="num">Local Market Value (10%)</th>
              </tr>
            </thead>
            <tbody>
              {plan.local_residuals.map((row, index) => (
                <tr key={`${row.farm_id}-${row.segment}-${index}`}>
                  <td><strong>{row.farm_id}</strong></td>
                  <td><Badge variant="yellow">Segment {row.segment}</Badge></td>
                  <td className="num neg"><strong>{fmtT(row.tonnes)}</strong></td>
                  <td className="num">{fmtEur(row.reference_price_per_t_eur)}/t</td>
                  <td className="num"><strong>{fmtEur(row.local_value_eur)}</strong></td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      </Card>
    </>
  );
}

function FilterSelect({ label, value, options, onChange }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span className="eyebrow" style={{ fontSize: 10 }}>{label}</span>
      <Select value={value} onChange={(event) => onChange(event.target.value)} style={{ height: 34 }}>
        <option value="ALL">All {label}s</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </Select>
    </label>
  );
}

function AssistantView({
  assistant,
  customQuestion,
  setCustomQuestion,
  askAssistant,
}) {
  const response = assistant.answer;
  return (
    <>
      <PageHead title="AI Planning Assistant" subtitle="Grounded decision explanations from calculated planning data" />
      <section className="assistant-shell">
        <Card>
          <CardHeader>
            <CardTitle style={{ fontSize: 18 }}>Suggested Questions</CardTitle>
          </CardHeader>
          <div className="question-list">
            {QUESTIONS.map((question) => (
              <Button
                key={question}
                variant="secondary"
                onClick={() => askAssistant(question)}
                style={{
                  height: "auto",
                  minHeight: 46,
                  justifyContent: "flex-start",
                  textAlign: "left",
                  padding: "12px 14px",
                  lineHeight: 1.4,
                  fontSize: 14.5,
                }}
              >
                <Icon name="help" style={{ flexShrink: 0 }} />
                {question}
              </Button>
            ))}
          </div>
          <div className="toolbar" style={{ marginTop: 16 }}>
            <Input
              value={customQuestion}
              onChange={(event) => setCustomQuestion(event.target.value)}
              placeholder="Ask a question about current plan..."
              onKeyDown={(e) => e.key === "Enter" && askAssistant(customQuestion)}
              style={{ fontSize: 14 }}
            />
            <Button variant="default" onClick={() => askAssistant(customQuestion)} style={{ fontSize: 14 }}>
              <Icon name="send" />
              Ask
            </Button>
          </div>
        </Card>

        <Card className="answer">
          {assistant.loading ? (
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: 20 }}>
              <Icon name="sync" className="spin" style={{ fontSize: 28 }} />
              <div>
                <strong style={{ fontSize: 16 }}>Analyzing calculated data...</strong>
                <p className="subtitle" style={{ fontSize: 14, marginTop: 2 }}>Synthesizing evidence across farms and commercial clients</p>
              </div>
            </div>
          ) : null}

          {assistant.error ? (
            <div className="error-state" style={{ margin: 0 }}>
              <h2 style={{ fontSize: 18 }}>{assistant.error.title}</h2>
              <p style={{ fontSize: 14.5 }}>{assistant.error.message}</p>
              <Button onClick={() => askAssistant(assistant.lastQuestion || QUESTIONS[0])}>
                <Icon name="replay" />
                Retry Question
              </Button>
            </div>
          ) : null}

          {response ? (
            <>
              <div>
                <span className="eyebrow" style={{ fontSize: 12 }}>{response.provider_state || "Deterministic Engine Response"}</span>
                <h2 style={{ marginTop: 4, fontSize: 20 }}>
                  {response.mode === "deterministic" ? "Calculated Explanation" : "Assistant Response"}
                </h2>
              </div>
              <p style={{ fontSize: 16, lineHeight: 1.65, color: "var(--black)", fontWeight: 500 }}>
                {response.answer}
              </p>
              <div style={{ marginTop: 12 }}>
                <span className="eyebrow" style={{ marginBottom: 6, display: "block", fontSize: 12 }}>Supporting Evidence:</span>
                <div className="warning-facts">
                  {(response.evidence || []).map((item) => (
                    <Badge
                      key={item}
                      variant={
                        String(item).startsWith("C0") || String(item).includes("Segment A")
                          ? "yellow"
                          : "default"
                      }
                      style={{ fontSize: 13, padding: "4px 10px" }}
                    >
                      {item}
                    </Badge>
                  ))}
                </div>
              </div>
            </>
          ) : null}

          {!assistant.loading && !assistant.error && !response ? (
            <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--black)" }}>
              <Icon name="psychology" style={{ fontSize: 48 }} />
              <p style={{ marginTop: 10, fontWeight: 600, fontSize: 16 }}>Select a suggested question or type your prompt above.</p>
            </div>
          ) : null}
        </Card>
      </section>
    </>
  );
}

function ImpactDrawer({ item }) {
  return (
    <div className="stack">
      <div className="mini-grid">
        <div className="mini">
          <span>Farm / Segment Gap</span>
          <strong className={cssVar(item.variance_t)}>{signedT(item.variance_t)}</strong>
        </div>
        <div className="mini">
          <span>Actual Received</span>
          <strong>{fmtT(item.actual_t)}</strong>
        </div>
        <div className="mini">
          <span>Export Allocated</span>
          <strong>{fmtT(item.allocated_t)}</strong>
        </div>
        <div className="mini">
          <span>Local Residual</span>
          <strong className={item.local_t > 0 ? "neg" : ""}>{fmtT(item.local_t)}</strong>
        </div>
      </div>

      <Card size="sm">
        <CardTitle>Affected Export Clients</CardTitle>
        <div className="warning-facts">
          {item.affected_clients.length ? (
            item.affected_clients.map((client) => (
              <Badge key={client.client_id} variant="yellow">
                {client.client_id} | Allocated: {fmtT(client.allocated_t)} | Shortage:{" "}
                {fmtT(client.remaining_t)} | {client.shortage_reason}
              </Badge>
            ))
          ) : (
            <Badge variant="yellow">No client shortage tied to this farm segment</Badge>
          )}
        </div>
      </Card>

      <Card size="sm">
        <CardTitle>Direct Allocations</CardTitle>
        <div className="warning-facts">
          {item.allocations.length ? (
            item.allocations.map((allocation, index) => (
              <Badge key={`${allocation.client_id}-${index}`} variant="black">
                {allocation.client_id} | {fmtT(allocation.tonnes)} | {allocation.quality_upgrade}
              </Badge>
            ))
          ) : (
            <Badge variant="yellow">No export allocation line</Badge>
          )}
        </div>
      </Card>
    </div>
  );
}

function ClientTraceDrawer({ client, plan }) {
  const clientAllocations = useMemo(() => {
    return plan.allocations.filter((row) => row.client_id === client.client_id);
  }, [plan.allocations, client.client_id]);

  return (
    <div className="stack">
      <div className="mini-grid">
        <div className="mini">
          <span>Program Demand</span>
          <strong>{fmtT(client.demand_t)}</strong>
        </div>
        <div className="mini">
          <span>Allocated Volume</span>
          <strong className="pos">{fmtT(client.allocated_t)}</strong>
        </div>
        <div className="mini">
          <span>Shortage Remaining</span>
          <strong className={client.remaining_t > 0 ? "neg" : ""}>
            {fmtT(client.remaining_t)}
          </strong>
        </div>
        <div className="mini">
          <span>Export Revenue</span>
          <strong>{fmtEur(client.export_revenue_eur)}</strong>
        </div>
      </div>

      <Card size="sm">
        <CardTitle>Quality Acceptance Rule</CardTitle>
        <p className="subtitle">
          Mode: <strong>{client.acceptance_mode}</strong> | Requested Segment:{" "}
          <strong>Segment {client.requested_segment}</strong>
        </p>
      </Card>

      <Card size="sm">
        <CardTitle>Supplying Farm Allocations ({clientAllocations.length} sources)</CardTitle>
        <TableWrap style={{ marginTop: 8 }}>
          <Table>
            <thead>
              <tr>
                <th>Farm ID</th>
                <th>Segment</th>
                <th className="num">Tonnes</th>
                <th>Quality Match</th>
              </tr>
            </thead>
            <tbody>
              {clientAllocations.map((row, index) => (
                <tr key={`${row.farm_id}-${row.segment}-${index}`}>
                  <td><strong>{row.farm_id}</strong></td>
                  <td>Segment {row.segment}</td>
                  <td className="num"><strong>{fmtT(row.tonnes)}</strong></td>
                  <td>
                    <Badge variant={row.quality_upgrade === "EXACT" ? "yellow" : "black"}>
                      {row.quality_upgrade}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      </Card>
    </div>
  );
}
