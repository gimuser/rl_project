import { useCallback, useEffect, useState } from "react";
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
type Key = "loss" | "policy_reward" | "validation_score" | "reward_efficiency" | "total_updates";
type ChartPoint = { label: string | number; value: number };

const metric = (p: AuthoritativeHistoryPoint, k: Key) =>
  Number((p as any)[k] ?? (k === "policy_reward" ? (p.avg_reward ?? p.average_reward ?? 0) : 0));

const fmt = (v: number | null | undefined, d = 4) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";

function LegacyChart({ points, label, valueFormatter = (value) => value.toFixed(4), accent = "#2563eb" }: {
  points: ChartPoint[];
  label: string;
  valueFormatter?: (value: number) => string;
  accent?: string;
}) {
  if (points.length === 0) return <div className="chart-empty">Waiting for persisted epoch telemetry…</div>;
  const width = 560, height = 200, padding = 18;
  const values = points.map((point) => point.value);
  const min = Math.min(...values), max = Math.max(...values), range = max - min || 1;
  const coordinates = points.map((point, index) => {
    const x = padding + (index / Math.max(points.length - 1, 1)) * (width - padding * 2);
    const y = height - padding - ((point.value - min) / range) * (height - padding * 2);
    return `${x},${y}`;
  });
  return <div className="legacy-line-chart" style={{ "--chart-accent": accent } as React.CSSProperties} role="img" aria-label={`${label} line chart`}>
    <div className="legacy-line-chart__axis legacy-line-chart__axis--top">{valueFormatter(max)}</div>
    <div className="legacy-line-chart__axis legacy-line-chart__axis--bottom">{valueFormatter(min)}</div>
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <line x1={padding} x2={width - padding} y1={padding} y2={padding} />
      <line x1={padding} x2={width - padding} y1={height / 2} y2={height / 2} />
      <line x1={padding} x2={width - padding} y1={height - padding} y2={height - padding} />
      <polyline points={coordinates.join(" ")} />
      {coordinates.map((coordinate, index) => { const [cx, cy] = coordinate.split(","); return <circle key={`${coordinate}-${index}`} cx={cx} cy={cy} r="3.5" />; })}
    </svg>
    <div className="legacy-line-chart__labels"><span>{points[0].label}</span><span>{points[points.length - 1].label}</span></div>
  </div>;
}

function HistoryChart({ title, history, field, windowSize, percent = false, accent }: {
  title: string; history: AuthoritativeHistoryPoint[]; field: Key; windowSize: number; percent?: boolean; accent?: string;
}) {
  const visible = history.slice(-Math.max(1, Math.min(windowSize, history.length)));
  const points = visible.map((point) => ({ label: `E${point.epoch}`, value: metric(point, field) }));
  return <article className="legacy-chart-panel">
    <div className="legacy-chart-panel__header"><div><p className="eyebrow">TRAINING CURVE</p><h2>{title}</h2></div><span>{visible.length} epochs</span></div>
    <LegacyChart label={title} points={points} accent={accent} valueFormatter={(value) => field === "total_updates" ? nf.format(Math.round(value)) : percent ? `${(value * 100).toFixed(1)}%` : value.toFixed(4)} />
    {visible.length > 0 && <div className="legacy-chart-panel__meta"><span>min {fmt(Math.min(...points.map((point) => point.value)), 5)}</span><span>max {fmt(Math.max(...points.map((point) => point.value)), 5)}</span></div>}
  </article>;
}

function ActionsChart({ history, windowSize }: { history: AuthoritativeHistoryPoint[]; windowSize: number }) {
  const visible = history.slice(-Math.max(1, Math.min(windowSize, history.length)));
  const actions = [
    { name: "Allow", key: "allow", accent: "#2563eb" },
    { name: "Block", key: "block", accent: "#a7680a" },
    { name: "Human review", key: "human_review", accent: "#7c3aed" },
  ] as const;
  return <article className="legacy-chart-panel">
    <div className="legacy-chart-panel__header"><div><p className="eyebrow">FINAL POLICY</p><h2>Action distribution</h2></div><span>Dynamic by epoch</span></div>
    {visible.length ? <div className="legacy-action-chart">
      <div className="legacy-action-chart__plot">{actions.map((action) => {
        const points = visible.map((point) => {
          const distribution = point.action_distribution ?? {};
          const total = Object.values(distribution).reduce((sum, value) => sum + Number(value || 0), 0) || 1;
          return { label: `E${point.epoch}`, value: Number((distribution as Record<string, number>)[action.key] || 0) / total };
        });
        return <LegacyChart key={action.key} label={action.name} points={points} accent={action.accent} valueFormatter={(value) => `${(value * 100).toFixed(0)}%`} />;
      })}</div>
      <div className="legacy-chart-legend">{actions.map((action) => <span key={action.key}><i style={{ background: action.accent }} />{action.name}</span>)}</div>
    </div> : <div className="chart-empty">Waiting for action telemetry…</div>}
  </article>;
}

export function TrainingLive() {
  const navigate = useNavigate();
  const [state, setState] = useState<AuthoritativeTrainingStatus | null>(null);
  const [error, setError] = useState("");
  const [windowSize, setWindowSize] = useState(40);
  const [follow, setFollow] = useState(true);
  const [stopping, setStopping] = useState(false);

  const refresh = useCallback(async () => { try { setState(await getAuthoritativeFullTrainingStatus()); setError(""); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } }, []);
  useEffect(() => { void refresh(); const id = window.setInterval(() => void refresh(), 2500); return () => window.clearInterval(id); }, [refresh]);

  const t = state?.results?.training;
  const history = t?.history ?? [];
  const latest = history.at(-1);
  const comparison = state?.results?.comparison;
  const live = state?.results?.live_inference as any;
  const best = comparison?.best;
  const selected = t?.selected_models ?? [];
  const liveDistribution = (live?.action_distribution ?? {}) as Record<string, number>;
  const liveTotal = Object.values(liveDistribution).reduce((sum, value) => sum + Number(value || 0), 0);
  const maxWindow = Math.max(10, history.length || 10);
  const effectiveWindow = Math.min(windowSize, maxWindow);

  const stop = async () => {
    if (stopping) return;
    setStopping(true);
    try { await stopAuthoritativeFullTraining(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setStopping(false); }
  };

  const liveComplete = live?.alerts_considered === LIVE_EXPECTED && live?.alerts_processed === LIVE_EXPECTED;
  const statusClass = state?.status ?? "idle";

  return <div className="live-page">
    <header className="live-hero"><div><div className="live-kicker">RL CONTROL ROOM · HARD-DATA TRAINING</div><h1>{t?.display_name ?? t?.model_name ?? "Training monitor"}</h1><p>Alert-level streaming training, incident-disjoint validation, unseen TEST evaluation, then the complete 80-alert live holdout.</p></div><div className="live-actions"><button className="live-btn" onClick={() => navigate("/training")}>Choose models</button><button className="live-btn" onClick={() => void refresh()}>Refresh</button>{state?.status === "running" && <button className="live-btn live-btn--danger" disabled={stopping} onClick={() => void stop()}>{stopping ? "Stopping…" : "Stop training"}</button>}</div></header>
    {error && <div className="live-error">{error}</div>}
    <section className="live-kpis"><div><span>Status</span><strong className={`status ${statusClass}`}>{state?.status ?? "idle"}</strong></div><div><span>Algorithm</span><strong>{t?.display_name ?? t?.algorithm ?? "—"}</strong></div><div><span>Epoch</span><strong>{nf.format(t?.actual_epochs ?? latest?.epoch ?? 0)} / {nf.format(t?.epochs ?? 0)}</strong></div><div><span>Updates</span><strong>{nf.format(t?.total_updates_used ?? 0)}</strong></div><div><span>Best epoch</span><strong>{nf.format(t?.best_epoch ?? 0)}</strong></div><div><span>Stop reason</span><strong>{t?.stopping_reason ?? "learning"}</strong></div></section>
    <section className="live-grid live-grid--four"><div className="metric"><span>Policy reward</span><strong>{fmt(t?.policy_reward ?? latest?.policy_reward, 6)}</strong></div><div className="metric"><span>Validation score</span><strong>{fmt(t?.validation_score ?? latest?.validation_score, 4)}</strong></div><div className="metric"><span>Reward efficiency</span><strong>{fmt(t?.reward_efficiency ?? latest?.reward_efficiency, 4)}</strong></div><div className="metric"><span>Live cycle</span><strong>{liveTotal ? `${liveTotal} actions` : "waiting"}</strong></div></section>
    <section className="chart-toolbar"><div><strong>Telemetry window</strong><span>{history.length} persisted epochs</span></div><label>Window <input type="range" min="10" max={maxWindow} value={effectiveWindow} onChange={(event) => { setFollow(false); setWindowSize(Number(event.target.value)); }} /><b>{effectiveWindow}</b></label><button className={follow ? "toggle active" : "toggle"} onClick={() => setFollow((value) => !value)}>{follow ? "Following latest" : "Manual window"}</button></section>
    <section className="charts-grid"><HistoryChart title="Training loss" history={history} field="loss" windowSize={effectiveWindow} accent="#2563eb" /><HistoryChart title="Policy reward" history={history} field="policy_reward" windowSize={effectiveWindow} accent="#12805c" /><HistoryChart title="Validation score" history={history} field="validation_score" windowSize={effectiveWindow} percent accent="#7c3aed" /><HistoryChart title="Reward efficiency" history={history} field="reward_efficiency" windowSize={effectiveWindow} percent accent="#a7680a" /><HistoryChart title="Cumulative optimizer updates" history={history} field="total_updates" windowSize={effectiveWindow} accent="#c43d4b" /><ActionsChart history={history} windowSize={effectiveWindow} /></section>
    <section className="live-bottom-grid"><article><div className="panel-title">Selected models</div><div className="chips">{selected.length ? selected.map((name) => <span key={name}>{name}</span>) : <span>—</span>}</div><div className="panel-title">Champion</div><strong>{best?.display_name ?? best?.name ?? "Not selected until comparison completes"}</strong></article><article><div className="panel-title">80-alert live holdout</div><div className="live-stats"><span>Expected<strong>{LIVE_EXPECTED}</strong></span><span>Considered<strong>{live?.alerts_considered ?? "—"}</strong></span><span>Processed<strong>{live?.alerts_processed ?? "—"}</strong></span></div><p>Human review <strong>{live?.human_review_routed ?? "—"}</strong></p><p>{liveComplete ? "All 80 real live alerts were processed." : "The live holdout is complete only when all 80 alerts have been considered and processed."}</p>{liveTotal > 0 && <p>Actions: {Object.entries(liveDistribution).map(([action, count]) => `${action} ${count}`).join(" · ")}</p>}</article></section>
  </div>;
}

export default TrainingLive;
