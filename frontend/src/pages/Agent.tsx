import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/ui/QueryState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useApi } from "../hooks/useApi";
import { liveAlertsService } from "../services/liveAlerts.service";
import { formatDecimal, formatNumber } from "../utils/format";

export function AgentPage() {
  const agent = useApi(liveAlertsService.getAgentStatus, { poll: true });
  const workload = useApi(liveAlertsService.getWorkload, { poll: true });

  return <>
    <PageHeader eyebrow="RL AGENT" title="Agent oversight" description="Live-alert supervision backed by MongoDB. Training is intentionally not started from this page." />
    <section className="split-grid">
      <article className="panel"><div className="panel__header"><div><p className="eyebrow">RUNTIME SIGNALS</p><h2>Agent state</h2></div></div>
        <QueryState state={agent}>{(data) => <dl className="detail-list">
          <Detail label="Runtime" value={data.status} badge />
          <Detail label="Mode" value={data.mode} />
          <Detail label="Training" value={data.training ? "Running" : "Not running"} />
          <Detail label="Algorithm" value={data.algorithm} />
          <Detail label="Model version" value={data.model_version ?? "Awaiting telemetry"} />
          <Detail label="Environment" value={data.environment_health} badge />
          <Detail label="Live alerts" value={formatNumber(data.total_alerts)} />
          <Detail label="Human review pending" value={formatNumber(data.human_review_pending)} />
        </dl>}</QueryState>
      </article>
      <article className="panel"><div className="panel__header"><div><p className="eyebrow">HUMAN-IN-THE-LOOP</p><h2>Review state</h2></div></div>
        <QueryState state={agent}>{(data) => <div className="inline-stat"><span>Current agent mode</span><StatusBadge value={data.model_status} /><strong>{formatNumber(data.human_review_pending)} pending</strong></div>}</QueryState>
        <div className="divider" />
        <QueryState state={workload}>{(data) => <dl className="detail-list"><Detail label="Average analyst load" value={formatDecimal(data.average_analyst_load, 2)} /><Detail label="Load variance" value={formatDecimal(data.load_variance, 2)} /></dl>}</QueryState>
      </article>
    </section>
    <section className="panel"><div className="panel__header"><div><p className="eyebrow">MODEL DETAILS</p><h2>Inference telemetry</h2></div></div><QueryState state={agent}>{(data) => <div className="api-notice"><strong>{data.note}</strong><p>Processed alert vectors are stored separately from source alert characteristics so the final inference path can display both representations.</p></div>}</QueryState></section>
  </>;
}

function Detail({ label, value, badge = false }: { label: string; value: string | number; badge?: boolean }) {
  return <div><dt>{label}</dt><dd>{badge ? <StatusBadge value={String(value)} /> : String(value)}</dd></div>;
}
