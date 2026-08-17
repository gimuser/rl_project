import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/ui/QueryState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useApi } from "../hooks/useApi";
import { decisionsService, type LiveDecision } from "../services/decisions.service";
import { formatDateTime, formatNumber, humanize } from "../utils/format";

export function DecisionsPage() {
  const decisions = useApi(() => decisionsService.getLiveDecisions(100), { poll: true });
  const [query, setQuery] = useState("");

  return (
    <>
      <PageHeader
        eyebrow="RL DECISIONS"
        title="Live agent decision history"
        description="The latest isolated alert cycle as decided by the active model. Human-review routing and final analyst actions remain linked to the same MongoDB alert record."
        actions={<button className="button button--quiet" type="button" onClick={() => void decisions.refresh()} disabled={decisions.isRefreshing}>{decisions.isRefreshing ? "Refreshing…" : "Refresh"}</button>}
      />

      <QueryState state={decisions} empty={(data) => data.items.length === 0}>
        {(result) => <>
          <section className="kpi-grid" aria-label="Live decision summary">
            <Metric label="Cycle" value={result.cycle_id ?? "—"} />
            <Metric label="Processed" value={formatNumber(result.summary.processed ?? result.total)} />
            <Metric label="Human review" value={formatNumber(result.summary.human_review ?? 0)} />
            <Metric label="Decisions" value={formatNumber(result.total)} />
          </section>
          <DecisionTable decisions={result.items} query={query} onQueryChange={setQuery} />
        </>}
      </QueryState>
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <article className="kpi-card"><div className="kpi-card__top"><span>{label}</span><span className="kpi-card__icon">◇</span></div><strong className="kpi-card__value">{value}</strong><p>Current live inference cycle</p></article>;
}

function DecisionTable({ decisions, query, onQueryChange }: { decisions: LiveDecision[]; query: string; onQueryChange: (value: string) => void }) {
  const filtered = useMemo(() => {
    const normalized = query.toLowerCase().trim();
    return decisions.filter((decision) => {
      if (!normalized) return true;
      return `${decision.decision_id} ${decision.alert_id} ${decision.incident_id ?? ""} ${decision.action} ${decision.algorithm ?? ""} ${decision.verdict ?? ""}`.toLowerCase().includes(normalized);
    });
  }, [decisions, query]);

  return <section className="panel table-panel">
    <div className="table-toolbar">
      <label className="search-input"><span aria-hidden="true">⌕</span><input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Search alert, action, model, or verdict" aria-label="Search live decisions" /></label>
      <span>{filtered.length} decision{filtered.length === 1 ? "" : "s"}</span>
    </div>
    {filtered.length === 0 ? <EmptyState compact title="No decisions match the search" description="Try another alert ID, action, model, or verdict." /> : <div className="table-scroll"><table>
      <thead><tr><th>Alert</th><th>Action</th><th>Confidence</th><th>Model</th><th>Status</th><th>Analyst</th><th>Timestamp</th></tr></thead>
      <tbody>{filtered.map((decision) => <tr key={decision.decision_id}>
        <td><Link className="table-link" to={`/alerts/${encodeURIComponent(decision.alert_id)}`}>{decision.alert_id}</Link><span className="muted">Incident {decision.incident_id ?? "—"} · {decision.source_category ?? "Unknown"}</span></td>
        <td><StatusBadge value={humanize(decision.action)} /><span className="muted">Model: {humanize(decision.model_action ?? decision.action)}</span></td>
        <td>{typeof decision.confidence === "number" ? `${(decision.confidence * 100).toFixed(1)}%` : "—"}{decision.uncertainty_reason ? <span className="muted">{humanize(decision.uncertainty_reason)}</span> : null}</td>
        <td><strong>{humanize(decision.algorithm ?? "—")}</strong><span className="muted">{decision.model_version ?? "No version"}</span></td>
        <td><StatusBadge value={decision.status ?? "UNKNOWN"} /></td>
        <td>{decision.assigned_analyst ?? "—"}</td>
        <td>{formatDateTime(decision.timestamp)}</td>
      </tr>)}</tbody>
    </table></div>}
  </section>;
}
