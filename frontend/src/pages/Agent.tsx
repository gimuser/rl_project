import { useEffect, useState } from "react";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/ui/QueryState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useApi } from "../hooks/useApi";
import { liveAlertsService } from "../services/liveAlerts.service";
import { getAuthoritativeFullTrainingStatus, type AuthoritativeTrainingStatus } from "../services/training.service";
import { formatDecimal, formatNumber } from "../utils/format";

export function AgentPage() {
  const agent = useApi(liveAlertsService.getAgentStatus, { poll: true });
  const workload = useApi(liveAlertsService.getWorkload, { poll: true });
  const [training, setTraining] = useState<AuthoritativeTrainingStatus | null>(null);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const next = await getAuthoritativeFullTrainingStatus();
        if (active) setTraining(next);
      } catch {
        if (active) setTraining(null);
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const trainingRunning = training?.status === "running" || training?.status === "starting";
  const trainingData = (training?.results?.training ?? {}) as Record<string, any>;

  return <>
    <PageHeader
      eyebrow="RL AGENT"
      title="Agent oversight"
      description={trainingRunning
        ? "The selected RL model is currently training on the hard dataset. Live-alert inference remains on hold until training and evaluation complete."
        : "Live-alert supervision backed by MongoDB. Training is controlled from the training lab and is not started from this page."}
    />

    {trainingRunning ? (
      <section className="split-grid">
        <article className="panel"><div className="panel__header"><div><p className="eyebrow">TRAINING RUNTIME</p><h2>Agent state</h2></div></div>
          <dl className="detail-list">
            <Detail label="Runtime" value="ONLINE" badge />
            <Detail label="Mode" value="TRAINING" />
            <Detail label="Training" value="Running" badge />
            <Detail label="Algorithm" value={trainingData.display_name ?? trainingData.algorithm ?? "—"} />
            <Detail label="Epoch" value={`${trainingData.actual_epochs ?? 0} / ${trainingData.epochs ?? trainingData.max_epochs ?? "—"}`} />
            <Detail label="Best epoch" value={trainingData.best_epoch ?? "—"} />
            <Detail label="Optimizer updates" value={formatNumber(trainingData.total_updates_used ?? trainingData.total_updates ?? 0)} />
            <Detail label="Environment" value="HEALTHY" badge />
          </dl>
        </article>
        <article className="panel"><div className="panel__header"><div><p className="eyebrow">TRAINING STATE</p><h2>Live-alert gate</h2></div></div>
          <div className="inline-stat"><span>Current agent mode</span><StatusBadge value="TRAINING" /><strong>Live inference paused</strong></div>
          <div className="divider" />
          <dl className="detail-list">
            <Detail label="Live alerts" value="On hold" />
            <Detail label="Human review pending" value="On hold" />
            <Detail label="Model version" value="New model not promoted yet" />
          </dl>
        </article>
      </section>
    ) : (
      <section className="split-grid">
        <article className="panel"><div className="panel__header"><div><p className="eyebrow">RUNTIME SIGNALS</p><h2>Agent state</h2></div></div>
          <QueryState state={agent}>{(data) => <dl className="detail-list">
            <Detail label="Runtime" value={data.status} badge />
            <Detail label="Mode" value={data.mode} />
            <Detail label="Training" value="Not running" />
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
    )}

    <section className="panel"><div className="panel__header"><div><p className="eyebrow">MODEL DETAILS</p><h2>Inference telemetry</h2></div></div>
      {trainingRunning ? (
        <div className="api-notice"><strong>Training in progress — no new champion model is being promoted.</strong><p>The current live-alert model remains unchanged until the training candidate completes validation, unseen TEST evaluation, and promotion.</p></div>
      ) : (
        <QueryState state={agent}>{(data) => <div className="api-notice"><strong>{data.note}</strong><p>Processed alert vectors are stored separately from source alert characteristics so the final inference path can display both representations.</p></div>}</QueryState>
      )}
    </section>
  </>;
}

function Detail({ label, value, badge = false }: { label: string; value: string | number; badge?: boolean }) {
  return <div><dt>{label}</dt><dd>{badge ? <StatusBadge value={String(value)} /> : String(value)}</dd></div>;
}
