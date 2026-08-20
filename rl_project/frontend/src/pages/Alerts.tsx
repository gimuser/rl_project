import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/ui/QueryState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useApi } from "../hooks/useApi";
import { liveAlertsService } from "../services/liveAlerts.service";
import type { LiveAlert } from "../types/domain";

const PAGE_SIZE = 10;

export function AlertsPage() {
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState("all");
  const [page, setPage] = useState(1);

  const alerts = useApi(
    () => liveAlertsService.getAlerts((page - 1) * PAGE_SIZE, PAGE_SIZE, query, severity),
    { poll: true },
  );

  return (
    <>
      <PageHeader eyebrow="ALERT OPERATIONS" title="Alert queue" description="Live holdout alerts stored in MongoDB and awaiting agent/human supervision." />
      <section className="panel filter-panel">
        <label className="search-input"><span aria-hidden="true">⌕</span><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="Search alert, source, or ID" aria-label="Search alerts" /></label>
        <label className="select-label">Severity<select value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1); }}><option value="all">All severities</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
        <button className="button button--quiet" type="button" onClick={() => void alerts.refresh()} disabled={alerts.isRefreshing}>{alerts.isRefreshing ? "Refreshing…" : "Refresh"}</button>
      </section>
      <QueryState state={alerts} empty={(data) => data.items.filter(hasValidAlertId).length === 0}>
        {(data) => <AlertsTable alerts={data.items} total={data.total} page={page} onPageChange={setPage} />}
      </QueryState>
    </>
  );
}

function hasValidAlertId(alert: LiveAlert): boolean {
  return typeof alert.alert_id === "string" && alert.alert_id.trim().length > 0 && alert.alert_id.trim().toLowerCase() !== "none";
}

function AlertsTable({
  alerts,
  total,
  page,
  onPageChange,
}: {
  alerts: LiveAlert[];
  total: number;
  page: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const resolvedPage = Math.min(page, totalPages);
  const visible = useMemo(() => alerts.filter(hasValidAlertId), [alerts]);

  if (visible.length === 0) return <EmptyState title="No live alerts match the current filters" description="Try clearing the search or selecting another severity." />;

  return (
    <section className="panel table-panel">
      <div className="table-panel__summary"><span>{total} live alert{total === 1 ? "" : "s"} returned</span><span>Invalid placeholder records are hidden; only real alert IDs are shown.</span></div>
      <div className="table-scroll"><table className="alerts-table"><thead><tr><th>ID</th><th>Alert</th><th>Severity</th><th>Source</th><th>Agent</th><th>Human review</th><th /></tr></thead><tbody>
        {visible.map((alert) => <tr key={alert.alert_id}>
          <td className="mono">{alert.alert_id}</td>
          <td><strong>{alert.title}</strong><div className="muted">Incident {String(alert.incident_id)}</div></td>
          <td><StatusBadge value={String(alert.severity ?? "unknown")} /></td>
          <td>{String(alert.source.Category ?? "Unknown")}</td>
          <td><span className="not-provided">{alert.agent.action}</span></td>
          <td><StatusBadge value={alert.agent.requires_human_review ? "Pending" : alert.status} /></td>
          <td><Link className="table-link" to={`/alerts/${encodeURIComponent(alert.alert_id)}`}>Details →</Link></td>
        </tr>)}
      </tbody></table></div>
      <Pagination page={resolvedPage} totalPages={totalPages} onPageChange={onPageChange} />
    </section>
  );
}

function Pagination({ page, totalPages, onPageChange }: { page: number; totalPages: number; onPageChange: (page: number) => void }) {
  return <nav className="pagination" aria-label="Alert pagination"><button type="button" className="button button--quiet" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>← Previous</button><span>Page {page} of {totalPages}</span><button type="button" className="button button--quiet" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>Next →</button></nav>;
}
