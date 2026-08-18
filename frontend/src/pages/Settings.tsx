import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../services/api";
import { PageHeader } from "../components/ui/PageHeader";
import "./Settings.css";

type ServiceStatus = "online" | "offline" | "degraded" | "checking";
type Check = { name: string; role: string; endpoint: string; status: ServiceStatus; detail: string };

type RuntimeState = {
  system?: { api?: string; database?: string; live_alerts?: number; pending_human_review?: number };
  training?: { status?: string; run_id?: string | null; algorithm?: string | null; actual_epochs?: number | null; best_epoch?: number | null };
  workload?: { average_analyst_load?: number; load_variance?: number; most_loaded_analyst?: { name?: string; utilization?: number } | null; least_loaded_analyst?: { name?: string; utilization?: number } | null };
  live?: { total?: number };
};

const statusLabel: Record<ServiceStatus, string> = { online: "ONLINE", offline: "OFFLINE", degraded: "DEGRADED", checking: "CHECKING" };

const initialChecks: Check[] = [
  { name: "FastAPI control plane", role: "Main backend API, training control, alert routing and analyst actions", endpoint: "/api/system/live-status", status: "checking", detail: "Checking…" },
  { name: "MongoDB data layer", role: "Live alerts, analyst workload, decisions and persisted operational state", endpoint: "/api/system/live-status", status: "checking", detail: "Checking…" },
  { name: "RL training service", role: "Starts/stops training, telemetry, model comparison and live evaluation", endpoint: "/api/training-control", status: "checking", detail: "Checking…" },
  { name: "Live alert pipeline", role: "Incoming live alerts, agent decisions and human-review routing", endpoint: "/api/live-alerts", status: "checking", detail: "Checking…" },
  { name: "Analyst workload service", role: "Analyst availability, utilization and routing capacity", endpoint: "/api/analysts/live-workload", status: "checking", detail: "Checking…" },
];

export function SettingsPage() {
  const [checks, setChecks] = useState<Check[]>(initialChecks);
  const [runtime, setRuntime] = useState<RuntimeState>({});
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [polling, setPolling] = useState(Number(import.meta.env.VITE_POLL_INTERVAL_MS || 2000));
  const [autoRefresh, setAutoRefresh] = useState(true);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setChecks((current) => current.map((item) => ({ ...item, status: "checking", detail: "Checking…" })));

    const runCheck = async <T,>(path: string) => {
      const started = performance.now();
      try {
        const value = await apiRequest<T>(path);
        return { ok: true, value, latency: Math.round(performance.now() - started) };
      } catch {
        return { ok: false, value: null as T | null, latency: Math.round(performance.now() - started) };
      }
    };

    const [systemResult, trainingResult, liveResult, workloadResult] = await Promise.all([
      runCheck<any>("/api/system/live-status"),
      runCheck<any>("/api/training-control"),
      runCheck<any>("/api/live-alerts?skip=0&limit=1"),
      runCheck<any>("/api/analysts/live-workload"),
    ]);

    const system = systemResult.value;
    const training = trainingResult.value?.results?.training ?? trainingResult.value?.training;
    const live = liveResult.value;
    const workload = workloadResult.value;

    setRuntime({ system, training, live, workload });
    setChecks([
      {
        name: "FastAPI control plane",
        role: "Main backend API, training control, alert routing and analyst actions",
        endpoint: "/api/system/live-status",
        status: !systemResult.ok ? "offline" : (system?.api === "healthy" || system?.api === "online" ? "online" : "degraded"),
        detail: systemResult.ok ? `${system?.api ?? "reachable"} · ${systemResult.latency} ms` : "API unreachable",
      },
      {
        name: "MongoDB data layer",
        role: "Live alerts, analyst workload, decisions and persisted operational state",
        endpoint: "/api/system/live-status",
        status: !systemResult.ok ? "offline" : (system?.database === "healthy" || system?.database === "online" ? "online" : "degraded"),
        detail: systemResult.ok ? `${system?.database ?? "reachable"} · ${systemResult.latency} ms` : "Database status unavailable",
      },
      {
        name: "RL training service",
        role: "Starts/stops training, telemetry, model comparison and live evaluation",
        endpoint: "/api/training-control",
        status: trainingResult.ok ? "online" : "offline",
        detail: trainingResult.ok ? `${training?.status ?? "ready"}${training?.algorithm ? ` · ${training.algorithm}` : ""} · ${trainingResult.latency} ms` : "Training API unreachable",
      },
      {
        name: "Live alert pipeline",
        role: "Incoming live alerts, agent decisions and human-review routing",
        endpoint: "/api/live-alerts",
        status: liveResult.ok ? "online" : "offline",
        detail: liveResult.ok ? `${live?.total ?? 0} alerts visible · ${liveResult.latency} ms` : "Live alert service unreachable",
      },
      {
        name: "Analyst workload service",
        role: "Analyst availability, utilization and routing capacity",
        endpoint: "/api/analysts/live-workload",
        status: workloadResult.ok ? "online" : "offline",
        detail: workloadResult.ok ? `${workload?.items?.length ?? 0} analysts · ${workloadResult.latency} ms` : "Analyst service unreachable",
      },
    ]);

    setLastRefresh(new Date());
    setRefreshing(false);
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = window.setInterval(() => void refresh(), Math.max(1000, polling));
    return () => window.clearInterval(id);
  }, [autoRefresh, polling, refresh]);

  const allOnline = checks.every((item) => item.status === "online");
  const system = runtime.system;
  const training = runtime.training;
  const workload = runtime.workload;

  return <>
    <PageHeader eyebrow="SYSTEM CONTROL" title="System settings & integrations" description="Monitor the live services behind the SOC control room, see what each service does, and control browser-side monitoring behavior." actions={<button className="settings-refresh" onClick={() => void refresh()} disabled={refreshing}>{refreshing ? "Checking…" : "Refresh status"}</button>} />

    <section className="settings-kpis">
      <article className="panel settings-kpi"><span>Overall health</span><strong className={allOnline ? "is-good" : "is-warning"}>{allOnline ? "Operational" : "Attention needed"}</strong></article>
      <article className="panel settings-kpi"><span>API</span><strong>{system?.api ?? "—"}</strong></article>
      <article className="panel settings-kpi"><span>Database</span><strong>{system?.database ?? "—"}</strong></article>
      <article className="panel settings-kpi"><span>Live alerts</span><strong>{system?.live_alerts ?? "—"}</strong></article>
      <article className="panel settings-kpi"><span>Human review</span><strong>{system?.pending_human_review ?? "—"}</strong></article>
    </section>

    <section className="panel settings-section">
      <div className="panel__header"><div><p className="eyebrow">INTEGRATIONS</p><h2>Connected services</h2></div><span className="settings-last-check">{lastRefresh ? `Last check ${lastRefresh.toLocaleTimeString()}` : "Checking…"}</span></div>
      <div className="settings-services">{checks.map((item) => <article className="settings-service" key={item.name}>
        <div className={`settings-status settings-status--${item.status}`}><span />{statusLabel[item.status]}</div>
        <h3>{item.name}</h3>
        <p>{item.role}</p>
        <code>{item.endpoint}</code>
        <strong>{item.detail}</strong>
      </article>)}</div>
    </section>

    <section className="settings-grid">
      <article className="panel settings-section"><div className="panel__header"><div><p className="eyebrow">RL RUNTIME</p><h2>Current training state</h2></div></div>
        <dl className="detail-list"><Detail label="Status" value={String(training?.status ?? "idle")} /><Detail label="Algorithm" value={String(training?.algorithm ?? "—")} /><Detail label="Run ID" value={String(training?.run_id ?? "—")} /><Detail label="Actual epoch" value={String(training?.actual_epochs ?? "—")} /><Detail label="Best epoch" value={String(training?.best_epoch ?? "—")} /></dl>
      </article>

      <article className="panel settings-section"><div className="panel__header"><div><p className="eyebrow">ANALYST OPERATIONS</p><h2>Workload status</h2></div></div>
        <dl className="detail-list"><Detail label="Average utilization" value={workload?.average_analyst_load != null ? `${Number(workload.average_analyst_load).toFixed(1)}%` : "—"} /><Detail label="Load variance" value={workload?.load_variance != null ? String(workload.load_variance) : "—"} /><Detail label="Most loaded" value={workload?.most_loaded_analyst?.name ? `${workload.most_loaded_analyst.name} · ${Number(workload.most_loaded_analyst.utilization ?? 0).toFixed(1)}%` : "—"} /><Detail label="Least loaded" value={workload?.least_loaded_analyst?.name ? `${workload.least_loaded_analyst.name} · ${Number(workload.least_loaded_analyst.utilization ?? 0).toFixed(1)}%` : "—"} /></dl>
      </article>
    </section>

    <section className="panel settings-section"><div className="panel__header"><div><p className="eyebrow">FRONTEND RUNTIME</p><h2>Live monitoring controls</h2></div><span className="settings-live-indicator">Browser session only</span></div>
      <div className="settings-controls"><label><span>Polling interval (ms)</span><input type="number" min={1000} max={60000} step={500} value={polling} onChange={(event) => setPolling(Number(event.target.value) || 2000)} /></label><label className="settings-toggle"><span>Auto-refresh service status</span><input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} /></label></div>
      <p className="muted">The current default is 2000 ms. These controls change only browser-side monitoring; RL training parameters remain on the training control page.</p>
    </section>
  </>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}
