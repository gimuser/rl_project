import { useMemo } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/ui/QueryState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useApi } from "../hooks/useApi";
import { apiRequest } from "../services/api";
import { liveAlertsService } from "../services/liveAlerts.service";

export function HistoryPage() {
  const activity = useApi(() => apiRequest<{ items: ActivityItem[]; total: number }>("/api/live-activity?limit=200"), { poll: true });
  const system = useApi(liveAlertsService.getSystemStatus, { poll: true });
  const grouped = useMemo(() => activity.data?.items ?? [], [activity.data]);

  return (
    <>
      <PageHeader eyebrow="SYSTEM RECORDS" title="History" description="Persistent live-alert activity, assignments, human decisions, and system events from MongoDB." actions={<button className="button" type="button" onClick={() => void activity.refresh()}>Refresh</button>} />
      <section className="split-grid">
        <article className="panel"><div className="panel__header"><div><p className="eyebrow">LIVE DATA</p><h2>Operational state</h2></div></div><QueryState state={system}>{(data) => <dl className="detail-list"><Detail label="API" value={data.api} /><Detail label="Database" value={data.database} /><Detail label="Live alerts" value={String(data.live_alerts)} /><Detail label="Human review pending" value={String(data.pending_human_review)} /></dl>}</QueryState></article>
        <article className="panel"><div className="panel__header"><div><p className="eyebrow">AUDIT</p><h2>Activity stream</h2></div></div><QueryState state={activity}>{(data) => <dl className="detail-list"><Detail label="Recorded events" value={String(data.total)} /><Detail label="Latest event" value={data.items[0]?.action ?? "No activity"} /><Detail label="Latest actor" value={String(data.items[0]?.actor ?? "—")} /></dl>}</QueryState></article>
      </section>
      <section className="panel"><div className="panel__header"><div><p className="eyebrow">LIVE ALERT AUDIT TRAIL</p><h2>Recent activity</h2></div></div><QueryState state={activity} empty={(data) => data.items.length === 0}>{(data) => <div className="table-scroll"><table className="alerts-table"><thead><tr><th>Time</th><th>Alert</th><th>Actor</th><th>Action</th><th>Details</th><th /></tr></thead><tbody>{grouped.map((entry, index) => <tr key={`${entry.alert_id}-${entry.timestamp}-${index}`}><td>{formatDate(entry.timestamp)}</td><td className="mono">{entry.alert_id}</td><td>{entry.actor}</td><td><StatusBadge value={entry.action} /></td><td>{JSON.stringify(entry.details ?? {})}</td><td><Link className="table-link" to={`/alerts/${encodeURIComponent(entry.alert_id)}`}>Inspect →</Link></td></tr>)}</tbody></table></div>}</QueryState></section>
    </>
  );
}

type ActivityItem = {
  alert_id: string;
  actor: string;
  action: string;
  details: Record<string, unknown>;
  timestamp: string;
};

function Detail({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function formatDate(value: string) { const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(parsed); }

export default HistoryPage;
