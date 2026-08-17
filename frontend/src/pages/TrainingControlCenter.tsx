import "./TrainingControlCenter.css";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getAuthoritativeFullTrainingStatus,
  startAuthoritativeFullTraining,
  stopAuthoritativeFullTraining,
  type AuthoritativeHistoryPoint,
  type AuthoritativeTrainingStatus,
} from "../services/training.service";

const nf = new Intl.NumberFormat("en-US");

type Metric = "loss" | "reward" | "updates" | "efficiency" | "validation";

function n(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? nf.format(value) : "—";
}
function d(value: unknown, digits = 4) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}
function pct(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—";
}

function metricValue(point: AuthoritativeHistoryPoint, metric: Metric) {
  switch (metric) {
    case "loss": return point.loss;
    case "reward": return point.policy_reward ?? point.avg_reward ?? point.average_reward ?? 0;
    case "updates": return point.total_updates ?? point.updates ?? 0;
    case "efficiency": return point.reward_efficiency ?? 0;
    case "validation": return point.validation_score ?? 0;
  }
}

function SparklineChart({ history, metric, zoomWindow }: { history: AuthoritativeHistoryPoint[]; metric: Metric; zoomWindow: number }) {
  if (!history.length) return <div className="lux-chart-empty">Waiting for persisted epoch telemetry…</div>;
  const visible = history.slice(-Math.max(2, Math.min(zoomWindow, history.length)));
  const values = visible.map((p) => metricValue(p, metric));
  const width = 1100;
  const height = 330;
  const pad = { left: 68, right: 28, top: 28, bottom: 48 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || Math.max(Math.abs(max) * 0.05, 1);
  const points = visible.map((point, i) => ({
    x: pad.left + (i / Math.max(1, visible.length - 1)) * plotW,
    y: pad.top + (1 - (metricValue(point, metric) - min) / span) * plotH,
    epoch: point.epoch,
    value: metricValue(point, metric),
  }));
  const line = points.map((p) => `${p.x},${p.y}`).join(" ");
  const area = `${pad.left},${pad.top + plotH} ${line} ${pad.left + plotW},${pad.top + plotH}`;
  const startEpoch = visible[0]?.epoch ?? 0;
  const endEpoch = visible.at(-1)?.epoch ?? 0;
  return (
    <div className="lux-chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="lux-chart-svg" role="img" aria-label={`${metric} training curve`}>
        <defs>
          <linearGradient id={`lux-fill-${metric}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6ea8ff" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#6ea8ff" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {[0, .25, .5, .75, 1].map((r) => {
          const y = pad.top + r * plotH;
          const v = max - r * span;
          return <g key={r}><line x1={pad.left} y1={y} x2={pad.left + plotW} y2={y} stroke="currentColor" opacity="0.12" /><text x={pad.left - 12} y={y + 4} textAnchor="end" className="lux-chart-label">{metric === "updates" ? Math.round(v).toLocaleString() : v.toFixed(metric === "loss" ? 3 : 4)}</text></g>;
        })}
        <polygon points={area} fill={`url(#lux-fill-${metric})`} />
        <polyline points={line} fill="none" stroke="#6ea8ff" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p) => <g key={p.epoch}><circle cx={p.x} cy={p.y} r="5" fill="currentColor" stroke="#6ea8ff" strokeWidth="3"><title>{`Epoch ${p.epoch} · ${p.value.toFixed(6)}`}</title></circle></g>)}
        <text x={pad.left} y={height - 14} className="lux-chart-label">Epoch {startEpoch}</text>
        <text x={pad.left + plotW} y={height - 14} textAnchor="end" className="lux-chart-label">Epoch {endEpoch}</text>
      </svg>
      <div className="lux-chart-meta"><span>Showing {n(visible.length)} epochs</span><span>Actual completion: epoch {n(endEpoch)}</span><span>Range: {d(min, 5)} → {d(max, 5)}</span></div>
    </div>
  );
}

function DistributionChart({ history, zoomWindow }: { history: AuthoritativeHistoryPoint[]; zoomWindow: number }) {
  const visible = history.slice(-Math.max(2, Math.min(zoomWindow, history.length)));
  if (!visible.length) return <div className="lux-chart-empty">Waiting for action telemetry…</div>;
  const width = 1100;
  const height = 330;
  const pad = { left: 58, right: 24, top: 22, bottom: 46 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const actions = ["allow", "block", "human_review"];
  const colors = { allow: "#6ea8ff", block: "#ff8c69", human_review: "#c6a0ff" };
  const series = actions.map((action) => {
    const pts = visible.map((row, i) => {
      const counts = row.action_distribution ?? {};
      const total = Object.values(counts).reduce((s, v) => s + Number(v || 0), 0) || 1;
      return {
        x: pad.left + (i / Math.max(1, visible.length - 1)) * plotW,
        y: pad.top + (1 - (Number(counts[action] || 0) / total)) * plotH,
        epoch: row.epoch,
        ratio: Number(counts[action] || 0) / total,
      };
    });
    return { action, pts };
  });
  return <div className="lux-chart-wrap">
    <svg viewBox={`0 0 ${width} ${height}`} className="lux-chart-svg" role="img" aria-label="Action distribution across epochs">
      {[0, .25, .5, .75, 1].map((r) => { const y = pad.top + (1-r) * plotH; return <g key={r}><line x1={pad.left} y1={y} x2={pad.left + plotW} y2={y} stroke="currentColor" opacity="0.12" /><text x={pad.left - 10} y={y + 4} textAnchor="end" className="lux-chart-label">{Math.round(r*100)}%</text></g>; })}
      {series.map(({ action, pts }) => <g key={action}><polyline points={pts.map((p) => `${p.x},${p.y}`).join(" ")} fill="none" stroke={colors[action as keyof typeof colors]} strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />{pts.map((p) => <circle key={`${action}-${p.epoch}`} cx={p.x} cy={p.y} r="4" fill="currentColor"><title>{`${action.replace("_", " ")} · epoch ${p.epoch} · ${(p.ratio*100).toFixed(1)}%`}</title></circle>)}</g>)}
      <text x={pad.left} y={height - 12} className="lux-chart-label">Epoch {visible[0].epoch}</text>
      <text x={pad.left + plotW} y={height - 12} textAnchor="end" className="lux-chart-label">Epoch {visible.at(-1)?.epoch}</text>
    </svg>
    <div className="lux-legend"><span><i style={{ background: colors.allow }} />Allow</span><span><i style={{ background: colors.block }} />Block</span><span><i style={{ background: colors.human_review }} />Human review</span></div>
  </div>;
}

export function TrainingControlCenter() {
  const [state, setState] = useState<AuthoritativeTrainingStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [cycleBusy, setCycleBusy] = useState(false);
  const [metric, setMetric] = useState<Metric>("loss");
  const [followLatest, setFollowLatest] = useState(true);
  const [windowSize, setWindowSize] = useState(60);

  const refresh = useCallback(async () => {
    try {
      const response = await getAuthoritativeFullTrainingStatus();
      setState(response);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const results = state?.results;
  const training = results?.training;
  const comparison = results?.comparison;
  const candidates = comparison?.candidates ?? [];
  const currentCandidate = training?.candidate_index ?? 0;
  const totalCandidates = (training?.candidate_count ?? candidates.length) || 3;
  const history = training?.history ?? [];
  const latest = history.at(-1);
  const live = results?.live_inference as any;
  const post = results?.post_training as any;
  const liveSummary = live?.summary ?? live ?? post?.inference ?? post?.live_inference ?? null;
  const actionCounts = liveSummary?.action_distribution ?? training?.action_distribution ?? {};
  const liveTotal = Object.values(actionCounts).reduce((sum: number, value: any) => sum + (Number(value) || 0), 0);
  const actualEpochs = training?.actual_epochs ?? latest?.epoch ?? 0;
  const maxEpochs = training?.epochs ?? 0;
  const effectiveWindow = followLatest ? windowSize : Math.min(windowSize, history.length);

  async function start() {
    if (!confirm("Start the 3-candidate sequential experiment? Each candidate trains, receives a fresh 40-alert cycle, and routes human-review alerts to analysts.")) return;
    setBusy(true); setError("");
    try { await startAuthoritativeFullTraining(); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); }
  }
  async function stop() {
    if (!confirm("Stop the sequential experiment? Completed telemetry and archived cycles remain preserved.")) return;
    setBusy(true);
    try { await stopAuthoritativeFullTraining(); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); }
  }
  async function newCycle() {
    if (state?.status === "running") { setError("Create a new live cycle after the training sequence, not while it is running."); return; }
    if (!confirm("Create a fresh 40-alert cycle? Previous Mongo decisions will be archived and the immutable source files will remain unchanged.")) return;
    setCycleBusy(true);
    try {
      const response = await fetch("/api/live-cycle/new", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "manual_refresh", metadata: { source: "training-control" } }) });
      if (!response.ok) throw new Error(`Live cycle reset failed (${response.status})`);
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setCycleBusy(false); }
  }

  const progress = totalCandidates > 0 ? Math.min(100, ((Math.max(0, currentCandidate - 1) + (state?.status === "completed" ? 1 : 0)) / totalCandidates) * 100) : 0;
  const actionCards = useMemo(() => [
    { key: "allow", label: "Allow", value: Number(actionCounts.allow ?? 0) },
    { key: "block", label: "Block", value: Number(actionCounts.block ?? 0) },
    { key: "human_review", label: "Human review", value: Number(actionCounts.human_review ?? 0) },
  ], [actionCounts]);

  return <div className="lux-training">
    <section className="lux-hero"><div><div className="lux-kicker">RL CONTROL ROOM · SEQUENTIAL EXPERIMENT</div><h1>Train → evaluate → route</h1><p>One training command runs all configured candidates. Each completed candidate gets a fresh 40-alert holdout and the champion receives a final clean cycle.</p></div><div className="lux-hero-actions"><button className="lux-button lux-button--ghost" disabled={busy || cycleBusy} onClick={() => void refresh()}>Refresh telemetry</button><button className="lux-button lux-button--ghost" disabled={busy || cycleBusy} onClick={() => void newCycle()}>New live cycle</button>{state?.status === "running" ? <button className="lux-button lux-button--danger" disabled={busy} onClick={() => void stop()}>{busy ? "Stopping…" : "Stop sequence"}</button> : <button className="lux-button lux-button--primary" disabled={busy} onClick={() => void start()}>{busy ? "Starting…" : "Start all 3 candidates"}</button>}</div></section>
    {error && <div className="lux-alert">{error}</div>}
    <section className="lux-statusbar"><div><span>Sequence</span><strong className={`lux-status lux-status--${state?.status ?? "idle"}`}>{state?.status ?? "idle"}</strong></div><div><span>Candidate</span><strong>{currentCandidate ? `${currentCandidate} / ${totalCandidates}` : "Waiting"}</strong></div><div><span>Epoch</span><strong>{n(actualEpochs)} / {n(maxEpochs)}</strong></div><div><span>Updates</span><strong>{n(training?.total_updates_used)}</strong></div><div><span>Live alerts</span><strong>{liveTotal ? `${n(liveTotal)} actions` : "Fresh cycle"}</strong></div></section>
    <section className="lux-card"><div className="lux-card-head"><div><div className="lux-card-label">AUTOMATIC PIPELINE</div><h2>Three-model sequence</h2></div><span className="lux-pill">No manual candidate start</span></div><div className="lux-progress"><i style={{ width: `${progress}%` }} /></div><div className="lux-mini-grid" style={{ marginTop: 14 }}>{[0,1,2].map((index) => { const c = candidates[index] as any; const active = currentCandidate === index+1 && state?.status === "running"; const done = Boolean(c?.live_inference || c?.live_cycle_id); return <div key={index} className={active ? "lux-candidate lux-candidate--active" : "lux-candidate"}><span>Candidate {index+1}</span><strong>{c?.name ?? ["dqn_lr_0005","dqn_lr_001","dqn_lr_002"][index]}</strong><small className="lux-muted">{active ? "Training now" : done ? "Trained + live evaluated" : "Queued"}</small></div>; })}</div></section>
    <section className="lux-metrics-grid"><article className="lux-card lux-card--hero"><div className="lux-card-label">POLICY REWARD</div><div className="lux-number">{d(training?.policy_reward ?? latest?.policy_reward,6)}</div><div className="lux-sub">Reward obtained by the learned policy.</div></article><article className="lux-card"><div className="lux-card-label">VALIDATION SCORE</div><div className="lux-number">{d(training?.validation_score,4)}</div><div className="lux-sub">Validation-only model selection.</div></article><article className="lux-card"><div className="lux-card-label">TOTAL UPDATES</div><div className="lux-number">{n(training?.total_updates_used)}</div><div className="lux-sub">Automatically derived update budget.</div></article><article className="lux-card"><div className="lux-card-label">BEST MODEL</div><div className="lux-number lux-number--small">{String((comparison?.best as any)?.name ?? "—")}</div><div className="lux-sub">Champion after candidate comparison.</div></article></section>

    <section className="lux-card lux-chart-card"><div className="lux-card-head"><div><div className="lux-card-label">INTERACTIVE TELEMETRY</div><h2>Learning curves</h2><p className="lux-muted">The chart follows the actual completed epoch by default. Zoom never includes thousands of empty future epochs.</p></div><div className="lux-chart-controls">{(["loss","reward","updates","efficiency","validation"] as Metric[]).map((m)=><button key={m} className={metric===m?"lux-chart-tab lux-chart-tab--active":"lux-chart-tab"} onClick={()=>setMetric(m)}>{m === "loss" ? "Loss" : m === "reward" ? "Policy reward" : m === "updates" ? "Updates" : m === "efficiency" ? "Efficiency" : "Validation"}</button>)}</div></div><div className="lux-chart-toolbar"><label>Visible epochs <input type="range" min={10} max={Math.max(10, Math.min(500, Math.max(history.length, actualEpochs)))} value={Math.min(windowSize, Math.max(10, Math.max(history.length, actualEpochs)))} onChange={(e)=>setWindowSize(Number(e.target.value))} /></label><strong>{Math.min(windowSize, Math.max(0, history.length)) || 0}</strong><button className={followLatest?"lux-chart-mode lux-chart-mode--active":"lux-chart-mode"} onClick={()=>setFollowLatest(!followLatest)}>{followLatest ? "Following latest" : "Manual window"}</button><button className="lux-chart-mode" onClick={()=>setWindowSize(Math.min(500, Math.max(10, history.length || actualEpochs || 10)))}>Show all completed</button></div><SparklineChart history={history} metric={metric} zoomWindow={effectiveWindow} /></section>

    <section className="lux-card lux-chart-card"><div className="lux-card-head"><div><div className="lux-card-label">POLICY BEHAVIOR</div><h2>Dynamic action distribution</h2><p className="lux-muted">Tracks allow/block/human-review shares by completed epoch instead of showing one static snapshot.</p></div></div><DistributionChart history={history} zoomWindow={effectiveWindow} /></section>

    <section className="lux-main-grid"><article className="lux-card"><div className="lux-card-label">LIVE 40-ALERT EVALUATION</div><h2>Latest inference cycle</h2><div className="lux-mini-grid" style={{ marginTop:16 }}><div><span>Cycle</span><strong>{liveSummary?.cycle_id ?? liveSummary?.decision_cycle_id ?? "—"}</strong></div><div><span>Considered</span><strong>{n(liveSummary?.alerts_considered)}</strong></div><div><span>Processed</span><strong>{n(liveSummary?.alerts_processed)}</strong></div><div><span>Human review</span><strong>{n(liveSummary?.human_review_routed)}</strong></div></div><div className="lux-main-grid" style={{ marginTop:14 }}>{actionCards.map((item)=><div key={item.key} className="lux-mini-grid"><div><span>{item.label}</span><strong>{n(item.value)}</strong></div></div>)}</div><p className="lux-muted" style={{marginTop:14}}>Every candidate receives a new MongoDB cycle; source, processed, and lineage files remain untouched.</p></article><article className="lux-card"><div className="lux-card-label">RESET SEMANTICS</div><h2>Fresh means fresh</h2><div className="lux-rule"><b>1</b><div><strong>Archive</strong><p>Previous alerts, reviews, and analyst actions stay in cycle history.</p></div></div><div className="lux-rule"><b>2</b><div><strong>Rebuild</strong><p>The active queue is recreated from the immutable 40-alert holdout.</p></div></div><div className="lux-rule"><b>3</b><div><strong>Re-infer</strong><p>The next model evaluates all 40 alerts from a clean cycle.</p></div></div></article></section>
  </div>;
}

export default TrainingControlCenter;
