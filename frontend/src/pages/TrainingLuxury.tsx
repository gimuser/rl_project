import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getAuthoritativeFullTrainingStatus,
  startAuthoritativeFullTraining,
  stopAuthoritativeFullTraining,
  type AuthoritativeHistoryPoint,
  type AuthoritativeTrainingStatus,
} from "../services/training.service";

const nf = new Intl.NumberFormat("en-US");
const CHART_WIDTH = 1100;
const CHART_HEIGHT = 360;
const DEFAULT_WINDOW = 160;

type Metric = "loss" | "policy" | "oracle" | "efficiency" | "validation" | "updates";

function n(v: unknown) { return typeof v === "number" && Number.isFinite(v) ? nf.format(v) : "—"; }
function d(v: unknown, digits = 4) { return typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "—"; }
function pct(v: unknown) { return typeof v === "number" && Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : "—"; }
function metricValue(point: AuthoritativeHistoryPoint, metric: Metric) {
  if (metric === "loss") return point.loss;
  if (metric === "policy") return point.policy_reward ?? point.avg_reward ?? point.average_reward ?? 0;
  if (metric === "oracle") return point.oracle_average_reward ?? 0;
  if (metric === "efficiency") return point.reward_efficiency ?? 0;
  if (metric === "validation") return point.validation_score ?? 0;
  return point.total_updates ?? point.updates ?? 0;
}

function visibleHistory(history: AuthoritativeHistoryPoint[], startEpoch: number, endEpoch: number) {
  const clipped = history.filter((row) => row.epoch >= startEpoch && row.epoch <= endEpoch);
  if (clipped.length <= 500) return clipped;
  const stride = Math.ceil(clipped.length / 500);
  const sampled = clipped.filter((_, index) => index % stride === 0);
  const last = clipped.at(-1);
  if (last && sampled.at(-1)?.epoch !== last.epoch) sampled.push(last);
  return sampled;
}

function lineChart(history: AuthoritativeHistoryPoint[], metric: Metric, startEpoch: number, endEpoch: number) {
  const source = visibleHistory(history, startEpoch, endEpoch);
  if (!source.length) return null;
  const points = source.map((row) => metricValue(row, metric));
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const left = 62, right = 28, top = 26, bottom = 42;
  const width = CHART_WIDTH - left - right;
  const height = CHART_HEIGHT - top - bottom;
  const coords = points.map((value, index) => ({ x: left + (index / Math.max(1, points.length - 1)) * width, y: top + (1 - (value - min) / span) * height, value, epoch: source[index].epoch }));
  return { source, coords, min, max, left, width, height, top, line: coords.map((p) => `${p.x},${p.y}`).join(" ") };
}

function InteractiveChart({ history, metric, startEpoch, endEpoch }: { history: AuthoritativeHistoryPoint[]; metric: Metric; startEpoch: number; endEpoch: number }) {
  const chart = lineChart(history, metric, startEpoch, endEpoch);
  if (!chart) return <div className="lux-empty">Waiting for completed epoch telemetry.</div>;
  const title = metric === "policy" ? "Policy reward" : metric === "oracle" ? "Oracle reward" : metric === "efficiency" ? "Policy efficiency" : metric === "validation" ? "Validation score" : metric === "updates" ? "Cumulative optimizer updates" : "Training loss";
  return <div className="lux-chart-shell">
    <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="lux-big-svg" role="img" aria-label={`${title} from epoch ${startEpoch} to ${endEpoch}`}>
      <defs><linearGradient id={`area-${metric}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="currentColor" stopOpacity=".28"/><stop offset="100%" stopColor="currentColor" stopOpacity=".01"/></linearGradient></defs>
      {[0,.25,.5,.75,1].map((ratio) => { const y = chart.top + ratio * chart.height; const value = chart.max - ratio * (chart.max - chart.min); return <g key={ratio}><line x1={chart.left} y1={y} x2={chart.left + chart.width} y2={y} className="lux-grid-line"/><text x={chart.left - 10} y={y + 4} textAnchor="end" className="lux-axis-label">{metric === "efficiency" || metric === "validation" ? pct(value) : d(value, metric === "updates" ? 0 : 4)}</text></g>; })}
      <polygon points={`${chart.left},${chart.top + chart.height} ${chart.line} ${chart.left + chart.width},${chart.top + chart.height}`} fill={`url(#area-${metric})`} />
      <polyline points={chart.line} fill="none" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      {chart.coords.map((point) => <g key={`${metric}-${point.epoch}`} className="lux-chart-point"><circle cx={point.x} cy={point.y} r="4.5" fill="var(--lux-surface)" stroke="currentColor" strokeWidth="2"/><title>{`Epoch ${point.epoch} · ${metric === "updates" ? n(point.value) : d(point.value, 6)}`}</title></g>)}
      <text x={chart.left} y={CHART_HEIGHT - 12} className="lux-axis-label">Epoch {chart.source[0].epoch}</text>
      <text x={chart.left + chart.width} y={CHART_HEIGHT - 12} textAnchor="end" className="lux-axis-label">Epoch {chart.source.at(-1)?.epoch}</text>
    </svg>
    <div className="lux-chart-caption"><span>{title}</span><span>Zoomed view · E{startEpoch} → E{endEpoch}</span></div>
  </div>;
}

function ActionDistributionChart({ history, startEpoch, endEpoch }: { history: AuthoritativeHistoryPoint[]; startEpoch: number; endEpoch: number }) {
  const actions = ["allow", "block", "human_review"];
  const colors = { allow: "#4f8cff", block: "#ff6b7f", human_review: "#d5a83a" } as const;
  const source = visibleHistory(history, startEpoch, endEpoch);
  return <div className="lux-action-timeline">{actions.map((action) => <div key={action} className="lux-action-lane"><div className="lux-action-head"><span>{action.replaceAll("_", " ")}</span><strong>epoch trend</strong></div><div className="lux-action-track">{source.map((row) => { const counts = row.action_distribution ?? {}; const total = Object.values(counts).reduce((sum, value) => sum + value, 0); const ratio = total > 0 ? ((counts[action] ?? 0) / total) : 0; return <span key={`${action}-${row.epoch}`} title={`Epoch ${row.epoch}: ${(ratio * 100).toFixed(1)}%`} style={{height:`${Math.max(3,ratio*100)}%`,background:colors[action as keyof typeof colors]}}/>; })}</div></div>)}</div>;
}

export function TrainingLuxuryPage() {
  const [response, setResponse] = useState<AuthoritativeTrainingStatus | null>(null);
  const [metric, setMetric] = useState<Metric>("loss");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [startEpoch, setStartEpoch] = useState(1);
  const [endEpoch, setEndEpoch] = useState(1);
  const [followLatest, setFollowLatest] = useState(true);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const value = await getAuthoritativeFullTrainingStatus();
      setResponse(value);
      setError("");
      const history = value.results?.training?.history ?? [];
      const latest = history.at(-1)?.epoch ?? 1;
      if (followLatest) {
        setEndEpoch(latest);
        setStartEpoch(Math.max(1, latest - DEFAULT_WINDOW + 1));
      } else {
        setStartEpoch((current) => Math.min(current, latest));
        setEndEpoch((current) => Math.min(Math.max(current, 1), latest));
      }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setRefreshing(false); }
  }, [followLatest]);

  useEffect(() => { void refresh(); const id = window.setInterval(() => void refresh(), 3000); return () => window.clearInterval(id); }, [refresh]);

  const run = response?.results;
  const training = run?.training;
  const history = training?.history ?? [];
  const comparison = run?.comparison;
  const candidates = comparison?.candidates ?? [];
  const best = comparison?.best ?? null;
  const running = response?.status === "running";
  const maxEpoch = Math.max(1, history.at(-1)?.epoch ?? training?.actual_epochs ?? 1);
  const actualEpoch = training?.actual_epochs ?? history.at(-1)?.epoch ?? 0;
  const totalUpdates = training?.total_updates_used ?? history.at(-1)?.total_updates ?? 0;
  const updateBudget = training?.max_total_updates ?? (training?.updates_per_epoch && training?.epochs ? training.updates_per_epoch * training.epochs : 0);
  const bounds = useMemo(() => ({ start: Math.max(1, Math.min(startEpoch, endEpoch, maxEpoch)), end: Math.max(1, Math.min(Math.max(startEpoch, endEpoch), maxEpoch)) }), [startEpoch, endEpoch, maxEpoch]);

  function setManualStart(value: number) { setFollowLatest(false); setStartEpoch(Math.min(value, bounds.end)); }
  function setManualEnd(value: number) { setFollowLatest(false); setEndEpoch(Math.max(value, bounds.start)); }
  function zoomLast() { const end = maxEpoch; setFollowLatest(true); setStartEpoch(Math.max(1, end - DEFAULT_WINDOW + 1)); setEndEpoch(end); }
  function zoomAll() { setFollowLatest(false); setStartEpoch(1); setEndEpoch(maxEpoch); }
  function zoomIn() { setFollowLatest(false); const mid = Math.floor((bounds.start + bounds.end) / 2); const span = Math.max(10, Math.floor((bounds.end - bounds.start + 1) / 2)); setStartEpoch(Math.max(1, mid - Math.floor(span / 2))); setEndEpoch(Math.min(maxEpoch, mid + Math.ceil(span / 2))); }
  function zoomOut() { setFollowLatest(false); const span = Math.max(10, (bounds.end - bounds.start + 1) * 2); const mid = Math.floor((bounds.start + bounds.end) / 2); setStartEpoch(Math.max(1, mid - Math.floor(span / 2))); setEndEpoch(Math.min(maxEpoch, mid + Math.ceil(span / 2))); }

  async function start() { if (!confirm("Start adaptive multi-model training on the real incident-level dataset?")) return; setBusy(true); setError(""); try { await startAuthoritativeFullTraining(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); } }
  async function stop() { if (!confirm("Stop the current training process? Completed telemetry will be preserved.")) return; setBusy(true); setError(""); try { await stopAuthoritativeFullTraining(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); } }

  return <div className="lux-training">
    <section className="lux-hero"><div><div className="lux-kicker">RL CONTROL ROOM · AUTONOMOUS TRAINING</div><h1>Model intelligence console</h1><p>Live convergence, policy reward, adaptive updates, uncertainty-aware inference, and champion-model telemetry.</p></div><div className="lux-hero-actions"><button className="lux-button lux-button--ghost" disabled={refreshing || busy} onClick={() => void refresh()}>{refreshing ? "Syncing…" : "Refresh"}</button>{running ? <button className="lux-button lux-button--danger" disabled={busy} onClick={() => void stop()}>{busy ? "Stopping…" : "Stop training"}</button> : <button className="lux-button lux-button--primary" disabled={busy} onClick={() => void start()}>{busy ? "Starting…" : "Start adaptive training"}</button>}</div></section>
    {error && <div className="lux-alert">{error}</div>}
    <section className="lux-statusbar"><div><span>Status</span><strong className={`lux-status lux-status--${response?.status ?? "idle"}`}>{response?.status ?? "idle"}</strong></div><div><span>Candidate</span><strong>{training?.candidate_index ? `${training.candidate_index} / ${training.candidate_count ?? "—"}` : "—"}</strong></div><div><span>Learning rate</span><strong>{training?.learning_rate ?? "—"}</strong></div><div><span>Completed epochs</span><strong>{n(actualEpoch)} / {n(training?.epochs)}</strong></div><div><span>Total updates</span><strong>{n(totalUpdates)}</strong></div></section>
    <section className="lux-metrics-grid"><article className="lux-card lux-card--hero"><div className="lux-card-label">POLICY REWARD</div><div className="lux-number">{d(training?.policy_reward ?? training?.final_avg_reward, 6)}</div><div className="lux-sub">Reward actually earned by the current policy actions.</div></article><article className="lux-card"><div className="lux-card-label">ORACLE GAP</div><div className="lux-number">{d((training?.oracle_average_reward ?? 0) - (training?.policy_reward ?? 0), 6)}</div><div className="lux-sub">Oracle ceiling − learned-policy reward.</div></article><article className="lux-card"><div className="lux-card-label">POLICY EFFICIENCY</div><div className="lux-number">{pct(training?.reward_efficiency)}</div><div className="lux-sub">Policy reward divided by oracle reward.</div></article><article className="lux-card"><div className="lux-card-label">MODEL STATE</div><div className="lux-number">{run?.model?.exists ? "READY" : "—"}</div><div className="lux-sub">{run?.post_training?.status ?? "Waiting for champion model"}</div></article></section>
    <section className="lux-card lux-card--wide"><div className="lux-card-head"><div><div className="lux-card-label">INTERACTIVE TELEMETRY</div><h2>Learning dynamics</h2></div><div className="lux-tabs">{(["loss","policy","oracle","efficiency","validation","updates"] as Metric[]).map((item) => <button key={item} className={metric === item ? "active" : ""} onClick={() => setMetric(item)}>{item}</button>)}</div></div><div className="lux-zoom-toolbar"><div className="lux-zoom-info"><strong>E{bounds.start} → E{bounds.end}</strong><span>{followLatest ? "Auto-following latest completed epoch" : "Manual zoom locked"}</span></div><div className="lux-zoom-actions"><button onClick={zoomIn}>＋ Zoom</button><button onClick={zoomOut}>－ Zoom</button><button onClick={zoomLast}>Latest</button><button onClick={zoomAll}>All</button></div></div><InteractiveChart history={history} metric={metric} startEpoch={bounds.start} endEpoch={bounds.end}/><div className="lux-range-grid"><label>Start epoch<input type="range" min={1} max={maxEpoch} value={bounds.start} onChange={(event) => setManualStart(Number(event.target.value))}/><span>{bounds.start}</span></label><label>End epoch<input type="range" min={1} max={maxEpoch} value={bounds.end} onChange={(event) => setManualEnd(Number(event.target.value))}/><span>{bounds.end}</span></label></div></section>
    <section className="lux-main-grid"><article className="lux-card"><div className="lux-card-label">DYNAMIC POLICY</div><h2>Action distribution by epoch</h2><p className="lux-muted">The timeline is rebuilt from every completed epoch's current policy actions; it is not a single static distribution.</p><ActionDistributionChart history={history} startEpoch={bounds.start} endEpoch={bounds.end}/></article><article className="lux-card"><div className="lux-card-label">AUTOMATIC UPDATE ENGINE</div><h2>Compute budget</h2><div className="lux-progress-block"><div className="lux-progress-top"><span>Epoch progress</span><strong>{n(actualEpoch)} / {n(training?.epochs)}</strong></div><div className="lux-progress"><i style={{width:`${training?.epochs ? Math.min(100,(actualEpoch/training.epochs)*100):0}%`}}/></div></div><div className="lux-progress-block"><div className="lux-progress-top"><span>Optimizer updates</span><strong>{n(totalUpdates)} / {n(updateBudget)}</strong></div><div className="lux-progress lux-progress--gold"><i style={{width:`${updateBudget ? Math.min(100,(totalUpdates/updateBudget)*100):0}%`}}/></div></div><div className="lux-mini-grid"><div><span>Updates / epoch</span><strong>{n(training?.updates_per_epoch)}</strong></div><div><span>Batch</span><strong>{n(training?.batch_size)}</strong></div><div><span>Patience</span><strong>{n(training?.patience)}</strong></div><div><span>Min delta</span><strong>{d(training?.min_delta,4)}</strong></div></div><div className="lux-explain"><strong>Stable reward is now split correctly</strong><p>Policy reward changes with the action chosen by the current network. The oracle ceiling is shown separately, so a flat oracle value no longer masquerades as learning progress.</p></div></article></section>
    <section className="lux-main-grid"><article className="lux-card"><div className="lux-card-head"><div><div className="lux-card-label">MODEL SELECTION</div><h2>Champion leaderboard</h2></div><span className="lux-pill">Validation only</span></div><div className="lux-table-wrap"><table className="lux-table"><thead><tr><th>Model</th><th>LR</th><th>Actual epochs</th><th>Best epoch</th><th>Val score</th><th>Status</th></tr></thead><tbody>{candidates.map((candidate,index)=><tr key={String(candidate.name??index)} className={best?.name===candidate.name?"is-best":""}><td><strong>{String(candidate.name??`Candidate ${index+1}`)}</strong></td><td>{String(candidate.learning_rate??"—")}</td><td>{n(candidate.actual_epochs)}</td><td>{n(candidate.best_epoch)}</td><td>{d(candidate.validation_score,4)}</td><td>{best?.name===candidate.name?"CHAMPION":String(candidate.status??"completed")}</td></tr>)}</tbody></table></div></article><article className="lux-card"><div className="lux-card-label">LIVE MODEL</div><h2>Operational champion</h2><div className="lux-mini-grid lux-mini-grid--model"><div><span>Version</span><strong>{String((run?.post_training?.model as any)?.model_version??"—")}</strong></div><div><span>Algorithm</span><strong>{String((run?.post_training?.model as any)?.model_name??"—")}</strong></div><div><span>Inference</span><strong>{String((run?.live_inference as any)?.status??"NOT_RUN")}</strong></div><div><span>Review routed</span><strong>{n((run?.live_inference as any)?.human_review_routed)}</strong></div></div></article></section>
    <section className="lux-card"><div className="lux-card-head"><div><div className="lux-card-label">EPOCH LEDGER</div><h2>Recent training events</h2></div><span className="lux-muted">Last {Math.min(16,history.length)} completed epochs</span></div><div className="lux-table-wrap lux-table-wrap--tall"><table className="lux-table"><thead><tr><th>Epoch</th><th>Loss</th><th>Policy</th><th>Oracle</th><th>Efficiency</th><th>Cumulative updates</th><th>Validation</th><th>Patience</th></tr></thead><tbody>{history.slice(-16).reverse().map((row)=><tr key={row.epoch}><td>{n(row.epoch)}</td><td>{d(row.loss,6)}</td><td>{d(row.policy_reward??row.avg_reward,6)}</td><td>{d(row.oracle_average_reward,6)}</td><td>{pct(row.reward_efficiency)}</td><td>{n(row.total_updates)}</td><td>{d(row.validation_score,4)}</td><td>{row.patience_used!=null?n(row.patience_used):"—"}</td></tr>)}</tbody></table></div></section>
  </div>;
}

export default TrainingLuxuryPage;
