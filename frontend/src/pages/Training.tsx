import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getAuthoritativeFullTrainingStatus,
  startAuthoritativeFullTraining,
  stopAuthoritativeFullTraining,
  type AuthoritativeHistoryPoint,
  type AuthoritativeTrainingStatus,
} from "../services/training.service";
import { StatusBadge } from "../components/ui/StatusBadge";

const numberFmt = new Intl.NumberFormat("en-US");

function num(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? numberFmt.format(value) : "—";
}

function decimal(value: unknown, digits = 4) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

function boolLabel(value: unknown) {
  return typeof value === "boolean" ? (value ? "Yes" : "No") : "—";
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function Detail({ label, value }: { label: string; value: React.ReactNode }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

type ChartMetric = "loss" | "reward" | "updates";

function metricValue(point: AuthoritativeHistoryPoint, metric: ChartMetric) {
  if (metric === "loss") return point.loss;
  if (metric === "reward") return point.avg_reward ?? point.average_reward ?? 0;
  return point.updates ?? 0;
}

function MetricChart({ history, metric }: { history: AuthoritativeHistoryPoint[]; metric: ChartMetric }) {
  if (!history.length) {
    return <div className="empty-state empty-state--compact"><span className="empty-state__icon">⌁</span><h3>Waiting for epoch data</h3><p>The chart will populate after the first persisted epoch.</p></div>;
  }

  const width = 920;
  const height = 280;
  const pad = { left: 54, right: 22, top: 22, bottom: 42 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const values = history.map((point) => metricValue(point, metric));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((value, index) => {
    const x = pad.left + (index / Math.max(1, values.length - 1)) * plotW;
    const y = pad.top + (1 - (value - min) / span) * plotH;
    return { x, y, value, epoch: history[index].epoch };
  });
  const line = points.map((point) => `${point.x},${point.y}`).join(" ");
  const area = `${pad.left},${pad.top + plotH} ${line} ${pad.left + plotW},${pad.top + plotH}`;

  return <div style={{ overflowX: "auto" }}>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${metric} by epoch`} style={{ width: "100%", minWidth: 620, height: "auto", display: "block" }}>
      <defs><linearGradient id={`fill-${metric}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2563eb" stopOpacity="0.18" /><stop offset="100%" stopColor="#2563eb" stopOpacity="0.01" /></linearGradient></defs>
      {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
        const y = pad.top + ratio * plotH;
        const v = max - ratio * span;
        return <g key={ratio}><line x1={pad.left} y1={y} x2={pad.left + plotW} y2={y} stroke="#dbe3ee" strokeDasharray="5 6" /><text x={pad.left - 10} y={y + 4} textAnchor="end" fontSize="10" fill="#708197">{decimal(v, metric === "updates" ? 0 : 3)}</text></g>;
      })}
      <polygon points={area} fill={`url(#fill-${metric})`} />
      <polyline points={line} fill="none" stroke="#2563eb" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
      {points.map((point) => <g key={String(point.epoch)}><circle cx={point.x} cy={point.y} r="5" fill="#fff" stroke="#2563eb" strokeWidth="2" /><title>{`Epoch ${point.epoch}: ${metric === "updates" ? point.value : point.value.toFixed(6)}`}</title></g>)}
      <text x={pad.left} y={height - 12} fontSize="11" fill="#708197">Epoch {history[0].epoch}</text>
      <text x={pad.left + plotW} y={height - 12} textAnchor="end" fontSize="11" fill="#708197">Epoch {history[history.length - 1].epoch}</text>
    </svg>
  </div>;
}

function ActionBars({ actions }: { actions: Record<string, number> | null | undefined }) {
  const entries = Object.entries(actions ?? {});
  const total = entries.reduce((sum, [, value]) => sum + value, 0);
  if (!entries.length || total <= 0) {
    return <div className="empty-state empty-state--compact"><span className="empty-state__icon">◎</span><h3>No action distribution yet</h3><p>Persisted action counts will appear here.</p></div>;
  }
  return <div style={{ display: "grid", gap: 14 }}>
    {entries.map(([name, value]) => {
      const ratio = value / total;
      return <div key={name}><div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, gap: 12 }}><strong style={{ color: "#223047", textTransform: "capitalize" }}>{name.replaceAll("_", " ")}</strong><span style={{ color: "#607089", fontSize: 13 }}>{num(value)} · {formatPercent(ratio)}</span></div><div style={{ height: 10, borderRadius: 999, background: "#e8eef6", overflow: "hidden" }}><div style={{ width: `${ratio * 100}%`, height: "100%", borderRadius: 999, background: "linear-gradient(90deg,#2563eb,#60a5fa)", transition: "width .35s ease" }} /></div></div>;
    })}
  </div>;
}

export function TrainingPage() {
  const [response, setResponse] = useState<AuthoritativeTrainingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [chartMetric, setChartMetric] = useState<ChartMetric>("loss");
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    try {
      const value = await getAuthoritativeFullTrainingStatus();
      setResponse(value);
      setError("");
      setLastRefresh(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const start = async () => {
    if (!window.confirm("Start the complete real-data RL training pipeline with validation, early stopping, and model comparison?")) return;
    try { setBusy(true); setError(""); await startAuthoritativeFullTraining(); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  const stop = async () => {
    if (!window.confirm("Stop the running full real-data training process? Completed epoch metrics and candidate checkpoints will be preserved.")) return;
    try { setBusy(true); setError(""); await stopAuthoritativeFullTraining(); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  const results = response?.results ?? null;
  const dataset = results?.dataset;
  const training = results?.training;
  const evaluation = results?.evaluation;
  const model = results?.model;
  const comparison = results?.comparison;
  const history = training?.history ?? [];
  const latest = history[history.length - 1];
  const isRunning = response?.status === "running";
  const actions = training?.action_distribution ?? latest?.action_distribution;

  const chartSummary = useMemo(() => {
    if (!history.length) return null;
    const losses = history.map((x) => x.loss);
    return { minLoss: Math.min(...losses), maxLoss: Math.max(...losses), latestReward: latest?.avg_reward ?? latest?.average_reward ?? null };
  }, [history, latest]);

  return <>
    <header className="page-header"><div><p className="eyebrow">MODEL TRAINING</p><h1>Training control</h1><p className="page-header__description">Live authoritative training telemetry with validation-based early stopping and automatic model comparison.</p></div><div className="page-header__actions"><div className="button-group">{!isRunning ? <button className="button button--primary" type="button" disabled={busy} onClick={() => void start()}>{busy ? "Starting…" : "Full training on real dataset"}</button> : <button className="button button--danger" type="button" disabled={busy} onClick={() => void stop()}>{busy ? "Stopping…" : "Stop training"}</button>}<button className="button button--quiet" type="button" disabled={busy} onClick={() => void refresh()}>Refresh</button></div></div></header>

    {error && <section className="panel query-error" role="alert"><div><strong>Training API error</strong><p>{error}</p></div><button className="button button--quiet" type="button" onClick={() => void refresh()}>Retry</button></section>}

    {loading ? <section className="panel loading-block"><div className="loading-block__line" /><div className="loading-block__line" /><div className="loading-block__line" /></section> : <>
      <section className="kpi-grid kpi-grid--four">
        <article className="kpi-card"><div className="kpi-card__top"><span>Status</span><StatusBadge value={response?.status ?? "unknown"} /></div><strong className="kpi-card__value">{isRunning ? "LIVE" : response?.status ?? "—"}</strong><p>{lastRefresh ? `Updated ${lastRefresh.toLocaleTimeString()}` : "Waiting for telemetry"}</p></article>
        <article className="kpi-card"><div className="kpi-card__top"><span>Epoch progress</span><span className="kpi-card__icon">↗</span></div><strong className="kpi-card__value">{num(training?.final_epoch)}<small style={{ fontSize: 14, color: "#64748b" }}> / {num(training?.epochs)}</small></strong><p>{num(training?.updates_per_epoch)} updates · best epoch {num(training?.best_epoch)}</p></article>
        <article className="kpi-card"><div className="kpi-card__top"><span>Latest loss</span><span className="kpi-card__icon">◒</span></div><strong className="kpi-card__value">{decimal(training?.final_loss, 6)}</strong><p>{chartSummary ? `range ${decimal(chartSummary.minLoss, 4)} → ${decimal(chartSummary.maxLoss, 4)}` : "No epoch history yet"}</p></article>
        <article className="kpi-card"><div className="kpi-card__top"><span>Validation score</span><span className="kpi-card__icon">✦</span></div><strong className="kpi-card__value">{training?.validation ? decimal(0.7 * (training.validation.policy_optimality ?? 0) + 0.3 * (training.validation.reward_efficiency ?? 0), 4) : "—"}</strong><p>0.70 optimality + 0.30 reward efficiency</p></article>
      </section>

      <section className="panel"><div className="panel__header"><div><p className="eyebrow">AUTHORITATIVE PIPELINE</p><h2>Training data and execution state</h2></div><span className="badge badge--info">{response?.message ?? "Ready"}</span></div><dl className="detail-list">
        <Detail label="Dataset" value={dataset?.name ?? "—"} /><Detail label="Feature count" value={num(dataset?.feature_count)} /><Detail label="Train rows" value={num(dataset?.train_rows)} /><Detail label="Validation rows" value={num(dataset?.validation_rows)} /><Detail label="Test rows" value={num(dataset?.test_rows)} /><Detail label="Train incidents" value={num(dataset?.train_incidents)} /><Detail label="Validation incidents" value={num(dataset?.validation_incidents)} /><Detail label="Test incidents" value={num(dataset?.test_incidents)} /><Detail label="Incident overlap" value={num(dataset?.incident_overlap)} /><Detail label="Learning rate" value={decimal(training?.learning_rate, 6)} /><Detail label="Batch size" value={num(training?.batch_size)} /><Detail label="Max epochs" value={num(training?.epochs)} /><Detail label="Actual epochs" value={num(training?.actual_epochs)} /><Detail label="Min epochs" value={num(training?.min_epochs)} /><Detail label="Early-stop patience" value={num(training?.patience)} /><Detail label="Min delta" value={decimal(training?.min_delta, 6)} /><Detail label="Final epoch" value={num(training?.final_epoch)} /><Detail label="Updates / epoch" value={num(training?.updates_per_epoch)} /><Detail label="Synthetic data" value={typeof dataset?.synthetic_data === "boolean" ? boolLabel(dataset.synthetic_data) : "—"} /><Detail label="Unseen incidents" value={typeof dataset?.unseen_incidents === "boolean" ? boolLabel(dataset.unseen_incidents) : "—"} /><Detail label="Candidate" value={training?.model_name ?? "—"} /><Detail label="Candidate progress" value={training?.candidate_index && training?.candidate_count ? `${training.candidate_index} / ${training.candidate_count}` : "—"} /><Detail label="Process ID" value={num(response?.pid)} /><Detail label="Started" value={response?.started_at ? new Date(response.started_at).toLocaleString() : "—"} />
      </dl></section>

      <section className="dashboard-grid dashboard-grid--bottom" style={{ marginBottom: 18 }}>
        <article className="panel"><div className="panel__header"><div><p className="eyebrow">LIVE POLICY</p><h2>Action distribution</h2></div></div><ActionBars actions={actions} /></article>
        <article className="panel"><div className="panel__header"><div><p className="eyebrow">MODEL</p><h2>Promoted model</h2></div></div><dl className="detail-list"><Detail label="Exists" value={typeof model?.exists === "boolean" ? boolLabel(model.exists) : "—"} /><Detail label="Path" value={model?.path ?? "—"} /><Detail label="Size" value={typeof model?.size_bytes === "number" ? `${num(model.size_bytes)} bytes` : "—"} /><Detail label="Modified" value={model?.modified_at ? new Date(model.modified_at).toLocaleString() : "—"} /></dl></article>
        <article className="panel"><div className="panel__header"><div><p className="eyebrow">EVALUATION</p><h2>Unseen incidents</h2></div></div><dl className="detail-list"><Detail label="Samples" value={num(evaluation?.samples)} /><Detail label="Throughput" value={typeof evaluation?.throughput_rows_per_second === "number" ? `${evaluation.throughput_rows_per_second.toFixed(2)} rows/sec` : "—"} /><Detail label="Average reward" value={decimal(evaluation?.average_reward)} /><Detail label="Policy optimality" value={typeof evaluation?.policy_optimality === "number" ? formatPercent(evaluation.policy_optimality) : "—"} /><Detail label="Reward efficiency" value={typeof evaluation?.reward_efficiency === "number" ? formatPercent(evaluation.reward_efficiency) : "—"} /></dl></article>
      </section>

      <section className="panel"><div className="panel__header"><div><p className="eyebrow">MODEL COMPARISON</p><h2>Candidate leaderboard</h2><p className="muted" style={{ marginTop: 6 }}>Candidates are selected using validation data only. The unseen test set is not used for model selection.</p></div></div>
        {comparison?.candidates?.length ? <div className="table-scroll" style={{ maxHeight: 360, overflow: "auto" }}><table><thead><tr><th>Model</th><th>Learning rate</th><th>Epochs</th><th>Val optimality</th><th>Val efficiency</th><th>Selection score</th><th>Status</th></tr></thead><tbody>{comparison.candidates.map((candidate, index) => <tr key={candidate.name}><td><strong>{index === 0 ? "★ " : ""}{candidate.name}</strong></td><td>{typeof candidate.learning_rate === "number" ? candidate.learning_rate.toExponential(1) : "—"}</td><td>{num(candidate.actual_epochs)}</td><td>{typeof candidate.best_validation?.policy_optimality === "number" ? formatPercent(candidate.best_validation.policy_optimality) : "—"}</td><td>{typeof candidate.best_validation?.reward_efficiency === "number" ? formatPercent(candidate.best_validation.reward_efficiency) : "—"}</td><td>{decimal(candidate.validation_score, 4)}</td><td><StatusBadge value={candidate.status ?? "—"} /></td></tr>)}</tbody></table></div> : <div className="empty-state empty-state--compact"><h3>No candidate comparison yet</h3><p>The comparison table will populate as model candidates complete.</p></div>}
      </section>

      <section className="panel" style={{ marginTop: 18 }}><div className="panel__header"><div><p className="eyebrow">INTERACTIVE TELEMETRY</p><h2>Training curves</h2><p className="muted" style={{ marginTop: 6 }}>Select a metric. Hover points for exact epoch values.</p></div><div className="button-group">{(["loss", "reward", "updates"] as ChartMetric[]).map((metric) => <button key={metric} type="button" className={`button ${chartMetric === metric ? "button--primary" : "button--quiet"}`} onClick={() => setChartMetric(metric)}>{metric === "loss" ? "Loss" : metric === "reward" ? "Reward" : "Updates"}</button>)}</div></div><MetricChart history={history} metric={chartMetric} /></section>

      <section className="split-grid" style={{ marginTop: 18 }}>
        <article className="panel"><div className="panel__header"><div><p className="eyebrow">EARLY STOPPING</p><h2>Convergence state</h2></div></div><dl className="detail-list"><Detail label="Best epoch" value={num(training?.best_epoch)} /><Detail label="Patience" value={training?.patience != null ? `${num(training.patience)}` : "—"} /><Detail label="Current patience used" value={latest?.patience_used != null ? `${num(latest.patience_used)}` : "—"} /><Detail label="Minimum improvement" value={decimal(training?.min_delta, 6)} /><Detail label="Validation optimality" value={typeof training?.validation?.policy_optimality === "number" ? formatPercent(training.validation.policy_optimality) : "—"} /><Detail label="Validation efficiency" value={typeof training?.validation?.reward_efficiency === "number" ? formatPercent(training.validation.reward_efficiency) : "—"} /></dl></article>
        <article className="panel"><div className="panel__header"><div><p className="eyebrow">EPOCH HISTORY</p><h2>Latest completed epochs</h2></div></div><div className="table-scroll" style={{ maxHeight: 360, overflow: "auto" }}><table><thead><tr><th>Epoch</th><th>Loss</th><th>Train reward</th><th>Val score</th><th>Updates</th><th>Patience</th></tr></thead><tbody>{history.slice(-15).reverse().map((row) => <tr key={row.epoch}><td>{num(row.epoch)}</td><td>{decimal(row.loss, 6)}</td><td>{decimal(row.avg_reward ?? row.average_reward, 6)}</td><td>{decimal(row.validation_score, 4)}</td><td>{num(row.updates)}</td><td>{num(row.patience_used)}</td></tr>)}</tbody></table>{!history.length && <div className="empty-state empty-state--compact"><h3>No persisted epoch history</h3></div>}</div></article>
      </section>

      <section className="split-grid" style={{ marginTop: 18 }}><article className="panel"><div className="panel__header"><div><p className="eyebrow">TEST ACTIONS</p><h2>Unseen-incident policy</h2></div></div><ActionBars actions={evaluation?.action_distribution} /></article><article className="panel"><div className="panel__header"><div><p className="eyebrow">SELECTION RULE</p><h2>How the winner is chosen</h2></div></div><div className="api-notice"><strong>{comparison?.selection_rule ?? "Validation-only selection"}</strong><p>Training uses the train incidents, early stopping uses validation incidents, and the final unseen test set is evaluated only after the best candidate is promoted.</p></div></article></section>

      {evaluation?.per_class && <section className="panel" style={{ marginTop: 18 }}><div className="panel__header"><div><p className="eyebrow">UNSEEN-INCIDENT EVALUATION</p><h2>Per-class results</h2></div></div><div className="table-scroll" style={{ maxHeight: 320, overflow: "auto" }}><table><thead><tr><th>Class</th><th>Rows</th><th>Avg reward</th><th>Optimality</th></tr></thead><tbody>{Object.entries(evaluation.per_class).map(([name, value]) => <tr key={name}><td>{name}</td><td>{num(value.rows)}</td><td>{decimal(value.average_reward)}</td><td>{typeof value.optimality === "number" ? formatPercent(value.optimality) : "—"}</td></tr>)}</tbody></table></div></section>}
    </>}
  </>;
}

export default TrainingPage;
