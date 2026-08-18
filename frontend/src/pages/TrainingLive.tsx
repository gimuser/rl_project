import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./TrainingLive.css";
import {
  getAuthoritativeFullTrainingStatus,
  stopAuthoritativeFullTraining,
  type AuthoritativeHistoryPoint,
  type AuthoritativeTrainingStatus,
} from "../services/training.service";

const nf = new Intl.NumberFormat("en-US");
const LIVE_EXPECTED = 80;
type MetricKey = "loss" | "policy_reward" | "validation_score" | "reward_efficiency" | "total_updates";

type ProgressState = {
  status?: string;
  stage?: string;
  algorithm?: string | null;
  display_name?: string | null;
  epoch?: number;
  epochs?: number;
  completed_epochs?: number;
  source_rows_processed?: number;
  source_rows_total?: number;
  progress_percent?: number;
  chunks_processed?: number;
  chunks_total?: number;
  filtered_train_rows_processed?: number;
  updates?: number;
  total_updates?: number;
};

const fmt = (value: unknown, digits = 4) =>
  typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";

const number = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) ? nf.format(value) : "—";

const pointValue = (point: AuthoritativeHistoryPoint, metric: MetricKey) => {
  if (metric === "policy_reward") return Number((point as any).policy_reward ?? point.avg_reward ?? point.average_reward ?? 0);
  if (metric === "total_updates") return Number((point as any).total_updates ?? point.updates ?? 0);
  return Number((point as any)[metric] ?? 0);
};

function LegacyChart({ values, labels, label, accent, formatter }: { values: number[]; labels: string[]; label: string; accent: string; formatter: (value: number) => string; }) {
  if (!values.length) return <div className="chart-empty">No completed epoch telemetry yet.</div>;
  const width = 560;
  const height = 200;
  const padding = 18;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || Math.max(Math.abs(max) * 0.05, 1);
  const coordinates = values.map((value, index) => {
    const x = padding + (index / Math.max(values.length - 1, 1)) * (width - padding * 2);
    const y = height - padding - ((value - min) / range) * (height - padding * 2);
    return { x, y };
  });
  return (
    <div className="legacy-line-chart" style={{ "--chart-accent": accent } as React.CSSProperties} role="img" aria-label={`${label} line chart`}>
      <div className="legacy-line-chart__axis legacy-line-chart__axis--top">{formatter(max)}</div>
      <div className="legacy-line-chart__axis legacy-line-chart__axis--bottom">{formatter(min)}</div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        <line x1={padding} x2={width - padding} y1={padding} y2={padding} />
        <line x1={padding} x2={width - padding} y1={height / 2} y2={height / 2} />
        <line x1={padding} x2={width - padding} y1={height - padding} y2={height - padding} />
        <polyline points={coordinates.map((p) => `${p.x},${p.y}`).join(" ")} />
        {coordinates.map((p, index) => <circle key={`${labels[index]}-${index}`} cx={p.x} cy={p.y} r="3.5"><title>{`${labels[index]} · ${formatter(values[index])}`}</title></circle>)}
      </svg>
      <div className="legacy-line-chart__labels"><span>{labels[0]}</span><span>{labels[labels.length - 1]}</span></div>
    </div>
  );
}

function HistoryChart({ title, history, metric, windowSize, accent, percent = false }: { title: string; history: AuthoritativeHistoryPoint[]; metric: MetricKey; windowSize: number; accent: string; percent?: boolean; }) {
  const visible = history.slice(-Math.max(1, Math.min(windowSize, history.length)));
  const values = visible.map((point) => pointValue(point, metric));
  const labels = visible.map((point) => `E${point.epoch}`);
  const formatter = (value: number) => metric === "total_updates" ? nf.format(Math.round(value)) : percent ? `${(value * 100).toFixed(1)}%` : value.toFixed(4);
  return (
    <article className="legacy-chart-panel">
      <div className="legacy-chart-panel__header"><div><p className="eyebrow">TRAINING CURVE</p><h2>{title}</h2></div><span>{visible.length} epochs</span></div>
      <LegacyChart values={values} labels={labels} label={title} accent={accent} formatter={formatter} />
      {visible.length > 0 && <div className="legacy-chart-panel__meta"><span>min {fmt(Math.min(...values), 5)}</span><span>max {fmt(Math.max(...values), 5)}</span></div>}
    </article>
  );
}

function ProgressChart({ progress }: { progress: ProgressState }) {
  const percent = Math.max(0, Math.min(100, Number(progress.progress_percent ?? 0)));
  const processed = Number(progress.source_rows_processed ?? 0);
  const total = Number(progress.source_rows_total ?? 0);
  return (
    <article className="legacy-chart-panel legacy-chart-panel--progress">
      <div className="legacy-chart-panel__header"><div><p className="eyebrow">LIVE STREAM</p><h2>Epoch progress</h2></div><span>Epoch {number(progress.epoch ?? 0)} in progress</span></div>
      <div className="progress-plot"><div className="progress-plot__scale"><span>0%</span><strong>{percent.toFixed(1)}%</strong><span>100%</span></div><div className="progress-plot__track"><i style={{ width: `${percent}%` }} /></div><div className="progress-plot__axis"><span>Start</span><span>Current stream position</span><span>Complete</span></div></div>
      <div className="legacy-chart-panel__meta progress-meta"><span>Rows {number(processed)} / {number(total)}</span><span>Chunks {number(progress.chunks_processed ?? 0)} / {number(progress.chunks_total ?? 0)}</span><span>Updates {number(progress.total_updates ?? 0)}</span></div>
    </article>
  );
}

function ActionsChart({ history, windowSize }: { history: AuthoritativeHistoryPoint[]; windowSize: number }) {
  const visible = history.slice(-Math.max(1, Math.min(windowSize, history.length)));
  const actions = [
    { name: "Allow", key: "allow", accent: "#2563eb" },
    { name: "Block", key: "block", accent: "#a7680a" },
    { name: "Human review", key: "human_review", accent: "#7c3aed" },
  ] as const;
  return (
    <article className="legacy-chart-panel">
      <div className="legacy-chart-panel__header"><div><p className="eyebrow">FINAL POLICY</p><h2>Action distribution</h2></div><span>Dynamic by epoch</span></div>
      {visible.length ? <div className="legacy-action-chart"><div className="legacy-action-chart__plot">
        {actions.map((action) => {
          const values = visible.map((point) => {
            const distribution = point.action_distribution ?? {};
            const total = Object.values(distribution).reduce((sum, value) => sum + Number(value || 0), 0) || 1;
            return Number((distribution as Record<string, number>)[action.key] || 0) / total;
          });
          const labels = visible.map((point) => `E${point.epoch}`);
          return <LegacyChart key={action.key} values={values} labels={labels} label={action.name} accent={action.accent} formatter={(value) => `${(value * 100).toFixed(0)}%`} />;
        })}
      </div><div className="legacy-chart-legend">{actions.map((action) => <span key={action.key}><i style={{ background: action.accent }} />{action.name}</span>)}</div></div> : <div className="chart-empty">Action distribution appears after the first completed epoch.</div>}
    </article>
  );
}

export function TrainingLive() {
  const navigate = useNavigate();
  const [state, setState] = useState<AuthoritativeTrainingStatus | null>(null);
  const [error, setError] = useState("");
  const [windowSize, setWindowSize] = useState(40);
  const [follow, setFollow] = useState(true);
  const [stopping, setStopping] = useState(false);

  const refresh = useCallback(async () => {
    try { setState(await getAuthoritativeFullTrainingStatus()); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }, []);

  useEffect(() => { void refresh(); const id = window.setInterval(() => void refresh(), 2500); return () => window.clearInterval(id); }, [refresh]);

  const activeRun = state?.status === "running" || state?.status === "starting";
  const t = activeRun ? (state?.results?.training as any) : null;
  const history = activeRun ? ((t?.history ?? []) as AuthoritativeHistoryPoint[]) : [];
  const latest = history.at(-1);
  const comparison = activeRun ? (state?.results?.comparison as any) : null;
  const live = activeRun ? (state?.results?.live_inference as any) : null;
  const best = comparison?.best as any;
  const selected = activeRun ? (t?.selected_models ?? []) : [];
  const progress = activeRun ? ((t?.progress ?? null) as ProgressState | null) : null;
  const liveDistribution = (live?.action_distribution ?? {}) as Record<string, number>;
  const liveTotal = Object.values(liveDistribution).reduce((sum, value) => sum + Number(value || 0), 0);
  const maxWindow = Math.max(10, history.length || 10);
  const effectiveWindow = Math.min(windowSize, maxWindow);
  const progressVisible = activeRun && progress?.stage === "epoch_in_progress";

  const bestStats = useMemo(() => {
    if (!history.length) return { epoch: null, validation: null, reward: null, efficiency: null };
    const byValidation = [...history].filter((p) => Number.isFinite(Number((p as any).validation_score))).sort((a, b) => Number((b as any).validation_score ?? -Infinity) - Number((a as any).validation_score ?? -Infinity))[0];
    const byReward = [...history].sort((a, b) => pointValue(b, "policy_reward") - pointValue(a, "policy_reward"))[0];
    const byEfficiency = [...history].sort((a, b) => pointValue(b, "reward_efficiency") - pointValue(a, "reward_efficiency"))[0];
    return { epoch: (t?.best_epoch ?? byValidation?.epoch ?? null) as number | null, validation: byValidation ? pointValue(byValidation, "validation_score") : null, reward: byReward ? pointValue(byReward, "policy_reward") : null, efficiency: byEfficiency ? pointValue(byEfficiency, "reward_efficiency") : null };
  }, [history, t?.best_epoch]);

  const stop = async () => {
    if (stopping) return;
    setStopping(true);
    try { await stopAuthoritativeFullTraining(); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setStopping(false); }
  };

  const liveComplete = live?.alerts_considered === LIVE_EXPECTED && live?.alerts_processed === LIVE_EXPECTED;
  const statusClass = state?.status ?? "idle";

  return (
    <div className="live-page">
      <header className="live-hero">
        <div><div className="live-kicker">RL CONTROL ROOM · HARD-DATA TRAINING</div><h1>{activeRun ? (t?.display_name ?? t?.model_name ?? "Training monitor") : "Training monitor"}</h1><p>Alert-level streaming training, incident-disjoint validation, unseen TEST evaluation, then the complete 80-alert live holdout.</p></div>
        <div className="live-actions"><button className="live-btn" onClick={() => navigate("/training")}>Choose models</button><button className="live-btn" onClick={() => void refresh()}>Refresh</button>{activeRun && <button className="live-btn live-btn--danger" disabled={stopping} onClick={() => void stop()}>{stopping ? "Stopping…" : "Stop training"}</button>}</div>
      </header>
      {error && <div className="live-error">{error}</div>}

      <section className="live-kpis">
        <div><span>Status</span><strong className={`status ${statusClass}`}>{state?.status ?? "idle"}</strong></div>
        <div><span>Algorithm</span><strong>{activeRun ? (t?.display_name ?? t?.algorithm ?? progress?.display_name ?? "—") : "—"}</strong></div>
        <div><span>Epoch</span><strong>{progressVisible ? `${number(progress?.epoch ?? 1)} in progress` : activeRun ? `${number(t?.actual_epochs ?? latest?.epoch ?? 0)} / ${number(t?.epochs ?? 0)}` : "—"}</strong></div>
        <div><span>Updates</span><strong>{activeRun ? number(t?.total_updates_used ?? progress?.total_updates ?? 0) : "—"}</strong></div>
        <div><span>Best epoch</span><strong>{activeRun ? number(bestStats.epoch) : "—"}</strong></div>
        <div><span>Stop reason</span><strong>{activeRun ? (t?.stopping_reason ?? "learning") : "—"}</strong></div>
      </section>

      {progressVisible && <section className="realtime-progress"><div className="realtime-progress__head"><div><p className="eyebrow">REAL-TIME TRAINING PROGRESS</p><h2>Epoch {number(progress?.epoch ?? 1)} in progress</h2><p>The epoch is still computing. Completed-epoch curves remain separate from live streaming telemetry.</p></div><strong>{Number(progress?.progress_percent ?? 0).toFixed(1)}%</strong></div><div className="realtime-progress__bar"><i style={{ width: `${Math.max(0, Math.min(100, Number(progress?.progress_percent ?? 0)))}%` }} /></div><div className="realtime-progress__stats"><div><span>Rows processed</span><strong>{number(progress?.source_rows_processed ?? 0)} / {number(progress?.source_rows_total ?? 0)}</strong></div><div><span>Chunks</span><strong>{number(progress?.chunks_processed ?? 0)} / {number(progress?.chunks_total ?? 0)}</strong></div><div><span>Optimizer updates</span><strong>{number(progress?.total_updates ?? 0)}</strong></div></div></section>}

      <section className="live-grid live-grid--four"><div className="metric"><span>Policy reward</span><strong>{activeRun ? fmt(t?.policy_reward ?? latest?.policy_reward, 6) : "—"}</strong></div><div className="metric"><span>Validation score</span><strong>{activeRun ? fmt(t?.validation_score ?? latest?.validation_score, 4) : "—"}</strong></div><div className="metric"><span>Reward efficiency</span><strong>{activeRun ? fmt(t?.reward_efficiency ?? latest?.reward_efficiency, 4) : "—"}</strong></div><div className="metric"><span>Live cycle</span><strong>{activeRun && liveTotal ? `${number(liveTotal)} actions` : "waiting"}</strong></div></section>

      <section className="best-grid"><article className="best-card"><span>BEST EPOCH</span><strong>{activeRun ? number(bestStats.epoch) : "—"}</strong><small>Validation-selected checkpoint</small></article><article className="best-card"><span>BEST VALIDATION</span><strong>{activeRun && bestStats.validation != null ? `${(bestStats.validation * 100).toFixed(1)}%` : "—"}</strong><small>Highest persisted validation score</small></article><article className="best-card"><span>BEST POLICY REWARD</span><strong>{activeRun && bestStats.reward != null ? bestStats.reward.toFixed(4) : "—"}</strong><small>Highest persisted policy reward</small></article><article className="best-card"><span>BEST EFFICIENCY</span><strong>{activeRun && bestStats.efficiency != null ? `${(bestStats.efficiency * 100).toFixed(1)}%` : "—"}</strong><small>Highest persisted reward efficiency</small></article></section>

      <section className="chart-toolbar"><div><strong>Telemetry window</strong><span>{history.length} persisted epochs</span></div><label>Window <input type="range" min="10" max={maxWindow} value={effectiveWindow} onChange={(event) => { setFollow(false); setWindowSize(Number(event.target.value)); }} /><b>{effectiveWindow}</b></label><button className={follow ? "toggle active" : "toggle"} onClick={() => setFollow((value) => !value)}>{follow ? "Following latest" : "Manual window"}</button></section>

      <section className="charts-grid">{progressVisible && <ProgressChart progress={progress ?? {}} />}<HistoryChart title="Training loss" history={history} metric="loss" windowSize={effectiveWindow} accent="#2563eb" /><HistoryChart title="Policy reward" history={history} metric="policy_reward" windowSize={effectiveWindow} accent="#12805c" /><HistoryChart title="Validation score" history={history} metric="validation_score" windowSize={effectiveWindow} accent="#7c3aed" percent /><HistoryChart title="Reward efficiency" history={history} metric="reward_efficiency" windowSize={effectiveWindow} accent="#a7680a" percent /><HistoryChart title="Cumulative optimizer updates" history={history} metric="total_updates" windowSize={effectiveWindow} accent="#c43d4b" /><ActionsChart history={history} windowSize={effectiveWindow} /></section>

      <section className="live-bottom-grid"><article><div className="panel-title">Selected models</div><div className="chips">{selected.length ? selected.map((name: string) => <span key={name}>{name}</span>) : <span>—</span>}</div><div className="panel-title">Champion</div><strong>{activeRun ? (best?.display_name ?? best?.name ?? "Not selected until comparison completes") : "—"}</strong></article><article><div className="panel-title">80-alert live holdout</div><div className="live-stats"><span>Expected<strong>{LIVE_EXPECTED}</strong></span><span>Considered<strong>{activeRun ? (live?.alerts_considered ?? "—") : "—"}</strong></span><span>Processed<strong>{activeRun ? (live?.alerts_processed ?? "—") : "—"}</strong></span></div><p>Human review <strong>{activeRun ? (live?.human_review_routed ?? "—") : "—"}</strong></p><p>{liveComplete ? "All 80 real live alerts were processed." : "The live holdout is complete only when all 80 alerts have been considered and processed."}</p>{liveTotal > 0 && <p>Actions: {Object.entries(liveDistribution).map(([action, count]) => `${action} ${count}`).join(" · ")}</p>}</article></section>
    </div>
  );
}

export default TrainingLive;
