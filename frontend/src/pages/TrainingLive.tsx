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

type Key = "loss" | "policy_reward" | "validation_score" | "reward_efficiency" | "total_updates";

const valueFor = (p: AuthoritativeHistoryPoint, key: Key) => Number((p as any)[key] ?? (key === "policy_reward" ? (p.avg_reward ?? 0) : 0));
const formatValue = (value: number | null | undefined, digits = 4) => typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";

function MiniChart({ title, history, field, percent = false }: { title: string; history: AuthoritativeHistoryPoint[]; field: Key; percent?: boolean }) {
  const visible = history.slice(-40);
  if (visible.length < 2) return <div className="chart-card"><div className="chart-title"><span>{title}</span></div><div className="chart-empty">Waiting for persisted telemetry…</div></div>;
  const width = 900, height = 240, left = 58, right = 20, top = 20, bottom = 32;
  const plotW = width - left - right, plotH = height - top - bottom;
  const values = visible.map(p => valueFor(p, field));
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const points = visible.map((p, i) => `${left + (i / (visible.length - 1)) * plotW},${top + (1 - (valueFor(p, field) - min) / span) * plotH}`).join(" ");
  return <div className="chart-card">
    <div className="chart-title"><span>{title}</span><strong>Epoch {visible.at(-1)?.epoch}</strong></div>
    <svg viewBox={`0 0 ${width} ${height}`} className="telemetry-svg" aria-label={title}>
      <polyline points={points} fill="none" stroke="#6ea8ff" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
      <text x={left} y={height - 10} className="axis-label">Epoch {visible[0].epoch}</text>
      <text x={left + plotW} y={height - 10} textAnchor="end" className="axis-label">Epoch {visible.at(-1)?.epoch}</text>
    </svg>
    <div className="chart-meta"><span>min {percent ? `${(min * 100).toFixed(1)}%` : min.toFixed(4)}</span><span>max {percent ? `${(max * 100).toFixed(1)}%` : max.toFixed(4)}</span></div>
  </div>;
}

export function TrainingLive() {
  const navigate = useNavigate();
  const [state, setState] = useState<AuthoritativeTrainingStatus | null>(null);
  const [error, setError] = useState("");
  const [stopping, setStopping] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setState(await getAuthoritativeFullTrainingStatus());
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const training = state?.results?.training;
  const history = training?.history ?? [];
  const latest = history.at(-1);
  const comparison = state?.results?.comparison;
  const live = state?.results?.live_inference;
  const best = comparison?.best;
  const actionDistribution = (live?.action_distribution ?? {}) as Record<string, number>;
  const actionTotal = Object.values(actionDistribution).reduce((sum, value) => sum + Number(value || 0), 0);
  const liveConsidered = Number(live?.alerts_considered ?? 0);
  const liveProcessed = Number(live?.alerts_processed ?? 0);
  const liveComplete = liveConsidered === LIVE_EXPECTED && liveProcessed === LIVE_EXPECTED;
  const selected = training?.selected_models ?? [];

  const statusText = useMemo(() => {
    if (state?.status === "running") return "TRAINING";
    if (state?.status === "completed") return liveComplete ? "COMPLETED · 80/80 LIVE" : "COMPLETED";
    return String(state?.status ?? "IDLE").toUpperCase();
  }, [state?.status, liveComplete]);

  const stop = async () => {
    setStopping(true);
    try {
      await stopAuthoritativeFullTraining();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStopping(false);
    }
  };

  return <div className="live-page">
    <header className="live-hero">
      <div>
        <div className="live-kicker">RL CONTROL ROOM · HARD-DATA TRAINING</div>
        <h1>{training?.display_name ?? training?.model_name ?? "Training monitor"}</h1>
        <p>Alert-level streaming training, incident-disjoint validation, unseen TEST evaluation, then the complete 80-alert live holdout.</p>
      </div>
      <div className="live-actions">
        <button className="live-btn" onClick={() => navigate("/training")}>Choose models</button>
        <button className="live-btn" onClick={() => void refresh()}>Refresh</button>
        {state?.status === "running" && <button className="live-btn live-btn--danger" disabled={stopping} onClick={() => void stop()}>{stopping ? "Stopping…" : "Stop training"}</button>}
      </div>
    </header>

    {error && <div className="live-error">{error}</div>}

    <section className="live-kpis">
      <div><span>Status</span><strong>{statusText}</strong></div>
      <div><span>Algorithm</span><strong>{training?.display_name ?? training?.algorithm ?? "—"}</strong></div>
      <div><span>Epoch</span><strong>{nf.format(training?.actual_epochs ?? latest?.epoch ?? 0)} / {nf.format(training?.epochs ?? 0)}</strong></div>
      <div><span>Updates</span><strong>{nf.format(training?.total_updates_used ?? 0)}</strong></div>
      <div><span>Best epoch</span><strong>{nf.format(training?.best_epoch ?? 0)}</strong></div>
      <div><span>Data mode</span><strong>HARD ALERT STREAM</strong></div>
    </section>

    <section className="live-grid live-grid--four">
      <div className="metric"><span>Policy reward</span><strong>{formatValue(training?.policy_reward ?? latest?.policy_reward, 6)}</strong></div>
      <div className="metric"><span>Validation score</span><strong>{formatValue(training?.validation_score ?? latest?.validation_score, 4)}</strong></div>
      <div className="metric"><span>Reward efficiency</span><strong>{formatValue(training?.reward_efficiency ?? latest?.reward_efficiency, 4)}</strong></div>
      <div className="metric"><span>Live holdout</span><strong>{liveComplete ? "80 / 80" : `${liveProcessed} / ${LIVE_EXPECTED}`}</strong></div>
    </section>

    <section className="charts-grid">
      <MiniChart title="Training loss" history={history} field="loss" />
      <MiniChart title="Policy reward" history={history} field="policy_reward" />
      <MiniChart title="Validation score" history={history} field="validation_score" percent />
      <MiniChart title="Reward efficiency" history={history} field="reward_efficiency" percent />
      <MiniChart title="Optimizer updates" history={history} field="total_updates" />
    </section>

    <section className="live-bottom-grid">
      <article>
        <div className="panel-title">Selected models</div>
        <div className="chips">{selected.length ? selected.map(model => <span key={model}>{model}</span>) : <span>—</span>}</div>
        <div className="panel-title">Champion</div>
        <strong>{best?.display_name ?? best?.name ?? "Not selected yet"}</strong>
      </article>

      <article>
        <div className="panel-title">80-alert live holdout</div>
        <div className="live-stats">
          <span>Expected<strong>{LIVE_EXPECTED}</strong></span>
          <span>Considered<strong>{live?.alerts_considered ?? "—"}</strong></span>
          <span>Processed<strong>{live?.alerts_processed ?? "—"}</strong></span>
          <span>Human review<strong>{live?.human_review_routed ?? "—"}</strong></span>
        </div>
        <p>{liveComplete ? "All 80 real live alerts were processed." : "The live holdout is complete only when all 80 alerts have been considered and processed."}</p>
        {actionTotal > 0 && <p>Actions: {Object.entries(actionDistribution).map(([action, count]) => `${action} ${count}`).join(" · ")}</p>}
      </article>
    </section>
  </div>;
}

export default TrainingLive;
