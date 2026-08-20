import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getAuthoritativeFullTrainingStatus, type AuthoritativeHistoryPoint, type AuthoritativeTrainingStatus } from "../services/training.service";
import "./TrainingLive.css";

const nf = new Intl.NumberFormat("en-US");

type MetricKey = "loss" | "policy_reward" | "validation_score" | "reward_efficiency" | "total_updates";

const valueOf = (point: AuthoritativeHistoryPoint, metric: MetricKey) => {
  if (metric === "policy_reward") return Number(point.policy_reward ?? point.avg_reward ?? point.average_reward ?? 0);
  if (metric === "total_updates") return Number(point.total_updates ?? point.updates ?? 0);
  return Number((point as any)[metric] ?? 0);
};

function Chart({ values, labels, formatter }: { values: number[]; labels: string[]; formatter: (value: number) => string }) {
  if (!values.length) return <div className="chart-empty">No persisted epoch telemetry.</div>;
  const width = 560;
  const height = 200;
  const pad = 18;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || Math.max(Math.abs(max) * 0.05, 1);
  const points = values.map((value, index) => {
    const x = pad + (index / Math.max(values.length - 1, 1)) * (width - pad * 2);
    const y = height - pad - ((value - min) / range) * (height - pad * 2);
    return `${x},${y}`;
  });
  return (
    <div className="legacy-line-chart">
      <div className="legacy-line-chart__axis legacy-line-chart__axis--top">{formatter(max)}</div>
      <div className="legacy-line-chart__axis legacy-line-chart__axis--bottom">{formatter(min)}</div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        <line x1={pad} x2={width - pad} y1={pad} y2={pad} />
        <line x1={pad} x2={width - pad} y1={height / 2} y2={height / 2} />
        <line x1={pad} x2={width - pad} y1={height - pad} y2={height - pad} />
        <polyline points={points.join(" ")} />
        {values.map((value, index) => {
          const [cx, cy] = points[index].split(",");
          return <circle key={`${labels[index]}-${index}`} cx={cx} cy={cy} r="3.5"><title>{`${labels[index]} · ${formatter(value)}`}</title></circle>;
        })}
      </svg>
      <div className="legacy-line-chart__labels"><span>{labels[0]}</span><span>{labels[labels.length - 1]}</span></div>
    </div>
  );
}

function MetricChart({ title, history, metric, percent = false }: { title: string; history: AuthoritativeHistoryPoint[]; metric: MetricKey; percent?: boolean }) {
  const values = history.map((point) => valueOf(point, metric));
  const labels = history.map((point) => `E${point.epoch}`);
  return (
    <article className="legacy-chart-panel">
      <div className="legacy-chart-panel__header"><div><p className="eyebrow">TRAINING CURVE</p><h2>{title}</h2></div><span>{history.length} epochs</span></div>
      <Chart values={values} labels={labels} formatter={(value) => metric === "total_updates" ? nf.format(Math.round(value)) : percent ? `${(value * 100).toFixed(1)}%` : value.toFixed(4)} />
      <div className="legacy-chart-panel__meta"><span>min {Math.min(...values).toFixed(5)}</span><span>max {Math.max(...values).toFixed(5)}</span></div>
    </article>
  );
}

export function TrainingRunViewer() {
  const { runId = "" } = useParams();
  const [state, setState] = useState<AuthoritativeTrainingStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getAuthoritativeFullTrainingStatus(runId)
      .then(setState)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [runId]);

  const training = state?.results?.training;
  const history = useMemo(() => training?.history ?? [], [training?.history]);
  const evaluation = state?.results?.evaluation;
  const comparison = state?.results?.comparison;
  const bestValidation = comparison?.best?.validation_score ?? training?.validation_score;
  const bestEpoch = training?.best_epoch ?? comparison?.best?.best_epoch;
  const bestReward = history.length ? Math.max(...history.map((point) => valueOf(point, "policy_reward"))) : null;
  const bestEfficiency = history.length ? Math.max(...history.map((point) => valueOf(point, "reward_efficiency"))) : null;

  return (
    <div className="live-page">
      <header className="live-hero">
        <div>
          <div className="live-kicker">RL CONTROL ROOM · PERSISTED TRAINING RUN</div>
          <h1>{training?.display_name ?? training?.algorithm ?? "Historical training run"}</h1>
          <p>Read-only historical telemetry. Loading this run does not start training and does not modify the model.</p>
        </div>
        <div className="live-actions">
          <Link className="live-btn" to="/training/history">Previous runs</Link>
          <Link className="live-btn" to="/training/live">Current monitor</Link>
        </div>
      </header>

      {error && <div className="live-error">{error}</div>}
      {!error && !state && <div className="chart-empty">Loading persisted run…</div>}

      {state && <>
        <section className="live-kpis">
          <div><span>Status</span><strong>{state.status}</strong></div>
          <div><span>Algorithm</span><strong>{training?.display_name ?? training?.algorithm ?? "—"}</strong></div>
          <div><span>Epochs</span><strong>{nf.format(training?.actual_epochs ?? history.length)} / {nf.format(training?.epochs ?? 0)}</strong></div>
          <div><span>Best epoch</span><strong>{bestEpoch ?? "—"}</strong></div>
          <div><span>Validation</span><strong>{typeof bestValidation === "number" ? `${(bestValidation * 100).toFixed(1)}%` : "—"}</strong></div>
          <div><span>Stop reason</span><strong>{training?.stopping_reason ?? "—"}</strong></div>
        </section>

        <section className="best-grid">
          <article className="best-card"><span>BEST EPOCH</span><strong>{bestEpoch ?? "—"}</strong><small>Validation-selected checkpoint</small></article>
          <article className="best-card"><span>BEST VALIDATION</span><strong>{typeof bestValidation === "number" ? `${(bestValidation * 100).toFixed(1)}%` : "—"}</strong><small>Persisted validation selection score</small></article>
          <article className="best-card"><span>BEST POLICY REWARD</span><strong>{bestReward != null ? bestReward.toFixed(4) : "—"}</strong><small>Highest persisted policy reward</small></article>
          <article className="best-card"><span>BEST EFFICIENCY</span><strong>{bestEfficiency != null ? `${(bestEfficiency * 100).toFixed(1)}%` : "—"}</strong><small>Highest persisted reward efficiency</small></article>
        </section>

        <section className="live-grid live-grid--two">
          <MetricChart title="Training loss" history={history} metric="loss" />
          <MetricChart title="Policy reward" history={history} metric="policy_reward" />
          <MetricChart title="Validation score" history={history} metric="validation_score" percent />
          <MetricChart title="Reward efficiency" history={history} metric="reward_efficiency" percent />
          <MetricChart title="Cumulative optimizer updates" history={history} metric="total_updates" />
        </section>

        <section className="best-grid">
          <article className="best-card"><span>UNSEEN TEST REWARD</span><strong>{evaluation?.average_reward != null ? evaluation.average_reward.toFixed(4) : "—"}</strong><small>Final unseen-incident evaluation</small></article>
          <article className="best-card"><span>TEST OPTIMALITY</span><strong>{evaluation?.policy_optimality != null ? `${(evaluation.policy_optimality * 100).toFixed(1)}%` : "—"}</strong><small>Agent action vs best available action</small></article>
          <article className="best-card"><span>TEST EFFICIENCY</span><strong>{evaluation?.reward_efficiency != null ? `${(evaluation.reward_efficiency * 100).toFixed(1)}%` : "—"}</strong><small>Real-data evaluation</small></article>
        </section>
      </>}
    </div>
  );
}
