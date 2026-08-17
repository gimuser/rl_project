import { Link } from "react-router-dom";
import { KpiCard } from "../components/ui/KpiCard";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/ui/QueryState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useApi } from "../hooks/useApi";
import { liveAlertsService } from "../services/liveAlerts.service";
import { formatDateTime, formatNumber } from "../utils/format";

export function DashboardPage() {
  const system = useApi(liveAlertsService.getSystemStatus, { poll: true });
  const alerts = useApi(() => liveAlertsService.getAlerts(0, 100), { poll: true });
  const agent = useApi(liveAlertsService.getAgentStatus, { poll: true });
  const activity = useApi(() => liveAlertsService.getActivity(100), { poll: true });
  const workload = useApi(liveAlertsService.getWorkload, { poll: true });

  const latestActivity = activity.data?.items ?? [];
  const pending = system.data?.pending_human_review ?? 0;
  const totalAlerts = system.data?.live_alerts ?? alerts.data?.total ?? 0;
  const assigned = workload.data?.items?.reduce((sum, item) => sum + item.load, 0) ?? 0;

  return (
    <>
      <PageHeader
        eyebrow="SOC SUPERVISION"
        title="Operations dashboard"
        description="Live operational data from the Mongo-backed SOAR-RL supervision layer. Training is not started by this dashboard."
        actions={<Link className="button button--primary" to="/alerts">Review alerts <span aria-hidden="true">→</span></Link>}
      />

      <QueryState state={system}>
        {() => (
          <section className="kpi-grid" aria-label="SOC live key performance indicators">
            <KpiCard label="Live alerts" value={formatNumber(totalAlerts)} detail="Isolated alert holdout" icon="◇" />
            <KpiCard label="Human review" value={formatNumber(pending)} detail="Alerts awaiting analyst control" icon="!" tone="warning" />
            <KpiCard label="Assigned" value={formatNumber(assigned)} detail="Alerts currently assigned" icon="↗" />
            <KpiCard label="Recorded activity" value={formatNumber(latestActivity.length)} detail="Recent MongoDB audit events" icon="✦" tone="success" />
          </section>
        )}
      </QueryState>

      <section className="dashboard-grid">
        <article className="panel panel--wide">
          <div className="panel__header">
            <div>
              <p className="eyebrow">ALERT OVERVIEW</p>
              <h2>Recent incoming alerts</h2>
            </div>
            <Link className="text-link" to="/alerts">View all alerts →</Link>
          </div>
          <QueryState state={alerts} empty={(data) => data.items.length === 0}>
            {(result) => (
              <div className="table-scroll">
                <table>
                  <thead><tr><th>Alert</th><th>Severity</th><th>Status</th><th>Source</th><th>Action</th></tr></thead>
                  <tbody>
                    {result.items.slice(0, 8).map((alert) => (
                      <tr key={alert.alert_id}>
                        <td><strong>{alert.title}</strong><span className="muted">{alert.alert_id} · Incident {alert.incident_id}</span></td>
                        <td><StatusBadge value={String(alert.severity ?? "unknown")} /></td>
                        <td><StatusBadge value={alert.status} /></td>
                        <td>{String(alert.source.Category ?? "Unknown")}</td>
                        <td><Link className="table-link" to={`/alerts/${encodeURIComponent(alert.alert_id)}`}>Inspect</Link></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </QueryState>
        </article>

        <article className="panel">
          <div className="panel__header">
            <div><p className="eyebrow">AGENT ACTIVITY</p><h2>Latest decisions / supervision</h2></div>
            <Link className="text-link" to="/history">History →</Link>
          </div>
          <QueryState state={activity} empty={(data) => data.items.length === 0}>
            {(result) => <ul className="activity-feed">
              {result.items.slice(0, 8).map((entry, index) => (
                <li key={`${entry.alert_id}-${entry.timestamp}-${index}`}>
                  <span className="activity-feed__mark" aria-hidden="true">↗</span>
                  <div><strong>{entry.action}</strong><p>{entry.alert_id} · {entry.actor} · {formatDateTime(entry.timestamp)}</p></div>
                </li>
              ))}
            </ul>}
          </QueryState>
        </article>
      </section>

      <section className="dashboard-grid dashboard-grid--bottom">
        <article className="panel">
          <div className="panel__header"><div><p className="eyebrow">SYSTEM HEALTH</p><h2>Service readiness</h2></div></div>
          <QueryState state={system}>
            {(data) => <div className="health-list">
              <HealthItem label="API" state={data.api} />
              <HealthItem label="Database" state={data.database} />
              <HealthItem label="Live alert store" state="Healthy" />
              <HealthItem label="Training" state={agent.data?.training_status ?? "NOT_RUNNING"} />
            </div>}
          </QueryState>
        </article>

        <article className="panel">
          <div className="panel__header"><div><p className="eyebrow">RL AGENT</p><h2>Current supervision state</h2></div><Link className="text-link" to="/agent">Open agent →</Link></div>
          <QueryState state={agent}>
            {(data) => <dl className="detail-list">
              <Detail label="Runtime" value={data.status} />
              <Detail label="Mode" value={data.mode} />
              <Detail label="Algorithm" value={data.algorithm} />
              <Detail label="Model status" value={data.model_status} />
              <Detail label="Pending human review" value={String(data.human_review_pending)} />
              <Detail label="Environment" value={data.environment_health} />
            </dl>}
          </QueryState>
        </article>

        <article className="panel">
          <div className="panel__header"><div><p className="eyebrow">ANALYST WORKLOAD</p><h2>Distribution</h2></div><Link className="text-link" to="/analysts">View analysts →</Link></div>
          <QueryState state={workload} empty={(data) => data.items.length === 0}>
            {(data) => <ul className="metric-list">
              {data.items.map((item) => <li key={item.analyst_id}><span>{item.name}</span><strong>{item.load}/{item.capacity}</strong></li>)}
            </ul>}
          </QueryState>
        </article>
      </section>

      <section className="panel rl-cycle">
        <div className="panel__header"><div><p className="eyebrow">LIVE DECISION CYCLE</p><h2>How an incoming alert flows</h2></div></div>
        <ol><li>Incoming alert</li><li>Processed RL input</li><li>Agent inference</li><li>Human review</li><li>Final action</li><li>Audit history</li></ol>
      </section>
    </>
  );
}

function HealthItem({ label, state }: { label: string; state: string }) {
  return <div className="health-list__item"><span>{label}</span><StatusBadge value={state} /></div>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}
