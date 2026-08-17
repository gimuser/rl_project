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
type Key = "loss" | "policy_reward" | "validation_score" | "reward_efficiency" | "total_updates";

const metric = (p: AuthoritativeHistoryPoint, k: Key) =>
  Number((p as any)[k] ?? (k === "policy_reward" ? (p.avg_reward ?? 0) : 0));
const fmt = (v: number | null | undefined, d = 4) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";

function Chart({
  title,
  history,
  field,
  color,
  windowSize,
  percent = false,
}: {
  title: string;
  history: AuthoritativeHistoryPoint[];
  field: Key;
  color: string;
  windowSize: number;
  percent?: boolean;
}) {
  const visible = history.slice(-Math.max(2, Math.min(windowSize, history.length)));
  const [hovered, setHovered] = useState<{ epoch: number; value: number; x: number; y: number } | null>(null);
  if (!visible.length) return <div className="chart-empty">Waiting for persisted epoch telemetry…</div>;

  const width = 900, height = 300, left = 64, right = 24, top = 24, bottom = 42;
  const pw = width - left - right, ph = height - top - bottom;
  const values = visible.map((p) => metric(p, field));
  const min0 = Math.min(...values), max0 = Math.max(...values);
  const pad = (max0 - min0 || Math.max(Math.abs(max0) * 0.08, 1)) * 0.08;
  const min = min0 - pad, max = max0 + pad;
  const span = max - min || 1;
  const pts = visible.map((p, i) => ({
    x: left + (i / Math.max(1, visible.length - 1)) * pw,
    y: top + (1 - (metric(p, field) - min) / span) * ph,
    e: p.epoch,
    v: metric(p, field),
  }));
  const line = pts.map((p) => `${p.x},${p.y}`).join(" ");

  const handleMove = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    let nearest = pts[0];
    for (const point of pts) {
      if (Math.abs(point.x - svgX) < Math.abs(nearest.x - svgX)) nearest = point;
    }
    setHovered({ epoch: nearest.e, value: nearest.v, x: nearest.x, y: nearest.y });
  };

  const displayValue = (value: number) =>
    percent ? `${(value * 100).toFixed(2)}%` : field === "total_updates" ? nf.format(Math.round(value)) : value.toFixed(6);

  return (
    <div className="chart-card">
      <div className="chart-title"><span>{title}</span><strong>Epoch {visible.at(-1)?.epoch}</strong></div>
      <div className="telemetry-chart-wrap">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="telemetry-svg"
          role="img"
          aria-label={title}
          onMouseMove={handleMove}
          onMouseLeave={() => setHovered(null)}
        >
          {[0, .25, .5, .75, 1].map((r) => {
            const y = top + r * ph;
            const val = max - r * span;
            return <g key={r}><line x1={left} y1={y} x2={left + pw} y2={y} className="grid-line"/><text x={left - 10} y={y + 4} textAnchor="end" className="axis-label">{percent ? `${(val * 100).toFixed(0)}%` : field === "total_updates" ? nf.format(Math.round(val)) : val.toFixed(3)}</text></g>;
          })}
          <polyline points={line} fill="none" stroke={color} strokeWidth="4" strokeLinejoin="round" strokeLinecap="round"/>
          {pts.map((p) => <circle key={p.e} cx={p.x} cy={p.y} r="4.5" fill={color}/>) }
          {hovered && <line x1={hovered.x} y1={top} x2={hovered.x} y2={top + ph} className="hover-guide"/>}
          <text x={left} y={height - 12} className="axis-label">Epoch {visible[0].epoch}</text>
          <text x={left + pw} y={height - 12} textAnchor="end" className="axis-label">Epoch {visible.at(-1)?.epoch}</text>
        </svg>
        {hovered && (
          <div className="chart-tooltip" style={{ left: `${Math.min(Math.max((hovered.x / width) * 100, 12), 86)}%`, top: `${Math.max((hovered.y / height) * 100 - 18, 8)}%` }}>
            <strong>Epoch {hovered.epoch}</strong>
            <span>{title}: {displayValue(hovered.value)}</span>
          </div>
        )}
      </div>
      <div className="chart-meta"><span>{visible.length} epochs</span><span>min {fmt(min0, 5)}</span><span>max {fmt(max0, 5)}</span></div>
    </div>
  );
}

function ActionsChart({ history, windowSize }: { history: AuthoritativeHistoryPoint[]; windowSize: number }) {
  const visible = history.slice(-Math.max(2, Math.min(windowSize, history.length)));
  const [hovered, setHovered] = useState<{ epoch: number; x: number; values: Record<string, number> } | null>(null);
  if (!visible.length) return <div className="chart-empty">Waiting for action telemetry…</div>;

  const width = 900, height = 300, left = 64, right = 24, top = 24, bottom = 42, pw = width-left-right, ph = height-top-bottom;
  const colors = { allow: "#6ea8ff", block: "#ff956f", human_review: "#c7a0ff" };
  const series = Object.keys(colors).map((action) => ({
    action,
    points: visible.map((p, i) => {
      const c = Number((p.action_distribution as any)?.[action] ?? 0);
      const total = Object.values(p.action_distribution ?? {}).reduce<number>((s, v) => s + Number(v || 0), 0) || 1;
      return { x: left + i/Math.max(1,visible.length-1)*pw, y: top + (1-c/total)*ph, e:p.epoch, ratio:c/total };
    }),
  }));

  const handleMove = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    let index = 0;
    let bestDistance = Infinity;
    visible.forEach((p, i) => {
      const x = left + i/Math.max(1,visible.length-1)*pw;
      const distance = Math.abs(x - svgX);
      if (distance < bestDistance) { bestDistance = distance; index = i; }
    });
    const point = visible[index];
    const values = (point.action_distribution ?? {}) as Record<string, number>;
    const total = Object.values(values).reduce((s, v) => s + Number(v || 0), 0) || 1;
    setHovered({
      epoch: point.epoch,
      x: left + index/Math.max(1,visible.length-1)*pw,
      values: {
        allow: Number(values.allow || 0) / total,
        block: Number(values.block || 0) / total,
        human_review: Number(values.human_review || 0) / total,
      },
    });
  };

  return (
    <div className="chart-card">
      <div className="chart-title"><span>Action distribution</span><strong>Dynamic by epoch</strong></div>
      <div className="telemetry-chart-wrap">
        <svg viewBox={`0 0 ${width} ${height}`} className="telemetry-svg" onMouseMove={handleMove} onMouseLeave={() => setHovered(null)}>
          {[0,.25,.5,.75,1].map(r=>{const y=top+(1-r)*ph;return <g key={r}><line x1={left} y1={y} x2={left+pw} y2={y} className="grid-line"/><text x={left-10} y={y+4} textAnchor="end" className="axis-label">{Math.round(r*100)}%</text></g>})}
          {series.map(s=><g key={s.action}><polyline points={s.points.map(p=>`${p.x},${p.y}`).join(" ")} fill="none" stroke={colors[s.action as keyof typeof colors]} strokeWidth="4"/><text x={left} y={height-12} className="axis-label">Epoch {visible[0].epoch}</text><text x={left+pw} y={height-12} textAnchor="end" className="axis-label">Epoch {visible.at(-1)?.epoch}</text></g>)}
          {hovered && <line x1={hovered.x} y1={top} x2={hovered.x} y2={top+ph} className="hover-guide"/>}
        </svg>
        {hovered && <div className="chart-tooltip chart-tooltip--multi" style={{ left: `${Math.min(Math.max((hovered.x / width) * 100, 16), 80)}%`, top: "10%" }}>
          <strong>Epoch {hovered.epoch}</strong>
          <span><i className="tooltip-dot" style={{background: colors.allow}}/>Allow {(hovered.values.allow * 100).toFixed(1)}%</span>
          <span><i className="tooltip-dot" style={{background: colors.block}}/>Block {(hovered.values.block * 100).toFixed(1)}%</span>
          <span><i className="tooltip-dot" style={{background: colors.human_review}}/>Human review {(hovered.values.human_review * 100).toFixed(1)}%</span>
        </div>}
      </div>
      <div className="legend"><span><i style={{background:colors.allow}}/>Allow</span><span><i style={{background:colors.block}}/>Block</span><span><i style={{background:colors.human_review}}/>Human review</span></div>
    </div>
  );
}

export function TrainingLive() {
  const navigate = useNavigate(); const [state, setState] = useState<AuthoritativeTrainingStatus|null>(null); const [error,setError]=useState(""); const [windowSize,setWindowSize]=useState(40); const [follow,setFollow]=useState(true); const [stopping,setStopping]=useState(false);
  const refresh=useCallback(async()=>{try{setState(await getAuthoritativeFullTrainingStatus());setError("")}catch(e){setError(e instanceof Error?e.message:String(e))}},[]);
  useEffect(()=>{void refresh();const id=window.setInterval(()=>void refresh(),2500);return()=>window.clearInterval(id)},[refresh]);
  const t=state?.results?.training; const history=t?.history??[]; const latest=history.at(-1); const comparison=state?.results?.comparison; const live=state?.results?.live_inference as any; const best=comparison?.best; const liveDistribution=(live?.action_distribution ?? {}) as Record<string, number>; const liveTotal=Object.values(liveDistribution).reduce<number>((s,v)=>s+Number(v||0),0); const selected=t?.selected_models??[];
  const visibleWindow=follow?Math.min(Math.max(windowSize,2),Math.max(history.length,2)):windowSize;
  const stop=async()=>{setStopping(true);try{await stopAuthoritativeFullTraining();await refresh()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setStopping(false)}};
  const statusClass=state?.status??"idle";
  return <div className="live-page">
    <header className="live-hero"><div><div className="live-kicker">RL CONTROL ROOM · LIVE TRAINING</div><h1>{t?.display_name ?? t?.model_name ?? "Adaptive experiment"}</h1><p>Live learning telemetry, convergence monitoring, resource-safe execution, and candidate evaluation.</p></div><div className="live-actions"><button className="live-btn" onClick={()=>navigate("/training")}>Choose models</button><button className="live-btn" onClick={()=>void refresh()}>Refresh</button>{state?.status==="running"&&<button className="live-btn live-btn--danger" disabled={stopping} onClick={()=>void stop()}>{stopping?"Stopping…":"Stop training"}</button>}</div></header>
    {error&&<div className="live-error">{error}</div>}
    <section className="live-kpis"><div><span>Status</span><strong className={`status ${statusClass}`}>{state?.status??"idle"}</strong></div><div><span>Algorithm</span><strong>{t?.display_name ?? t?.algorithm ?? "—"}</strong></div><div><span>Epoch</span><strong>{nf.format(t?.actual_epochs??latest?.epoch??0)} / {nf.format(t?.epochs??0)}</strong></div><div><span>Updates</span><strong>{nf.format(t?.total_updates_used??0)}</strong></div><div><span>Best epoch</span><strong>{nf.format(t?.best_epoch??0)}</strong></div><div><span>Stop reason</span><strong>{t?.stopping_reason??"learning"}</strong></div></section>
    <section className="live-grid live-grid--four"><div className="metric"><span>Policy reward</span><strong>{fmt(t?.policy_reward??latest?.policy_reward,6)}</strong></div><div className="metric"><span>Validation score</span><strong>{fmt(t?.validation_score??latest?.validation_score,4)}</strong></div><div className="metric"><span>Reward efficiency</span><strong>{fmt(t?.reward_efficiency??latest?.reward_efficiency,4)}</strong></div><div className="metric"><span>Live cycle</span><strong>{liveTotal?`${liveTotal} actions`:"waiting"}</strong></div></section>
    <section className="chart-toolbar"><div><strong>Telemetry window</strong><span>{history.length} persisted epochs</span></div><label>Window <input type="range" min="10" max={Math.max(10,history.length||10)} value={Math.min(windowSize,Math.max(10,history.length||10))} onChange={e=>setWindowSize(Number(e.target.value))}/><b>{Math.min(windowSize,Math.max(10,history.length||10))}</b></label><button className={follow?"toggle active":"toggle"} onClick={()=>setFollow(!follow)}>{follow?"Following latest":"Manual window"}</button></section>
    <section className="charts-grid">
      <Chart title="Training loss" history={history} field="loss" color="#6ea8ff" windowSize={visibleWindow}/>
      <Chart title="Policy reward" history={history} field="policy_reward" color="#69d2a6" windowSize={visibleWindow}/>
      <Chart title="Validation score" history={history} field="validation_score" color="#c7a0ff" windowSize={visibleWindow} percent/>
      <Chart title="Reward efficiency" history={history} field="reward_efficiency" color="#ffb86b" windowSize={visibleWindow} percent/>
      <Chart title="Cumulative optimizer updates" history={history} field="total_updates" color="#ff956f" windowSize={visibleWindow}/>
      <ActionsChart history={history} windowSize={visibleWindow}/>
    </section>
    <section className="live-bottom-grid"><article><div className="panel-title">Selected models</div><div className="chips">{selected.length?selected.map(s=><span key={s}>{s}</span>):<span>—</span>}</div><div className="panel-title">Champion</div><strong>{best?.display_name ?? best?.name ?? "Not selected until comparison completes"}</strong></article><article><div className="panel-title">Live 40-alert evaluation</div><div className="live-stats"><span>Considered<strong>{live?.alerts_considered??"—"}</strong></span><span>Processed<strong>{live?.alerts_processed??"—"}</strong></span><span>Human review<strong>{live?.human_review_routed??"—"}</strong></span></div></article></section>
  </div>;
}
