import "./TrainingLauncher.css";

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { startAuthoritativeFullTraining } from "../services/training.service";

const MODELS = [
  { name: "double_dqn", title: "Double DQN", tag: "BASELINE", detail: "Incident-level counterfactual Double DQN baseline.", warning: "" },
  { name: "cql", title: "Conservative Q-Learning · CQL", tag: "CONSERVATIVE", detail: "Penalizes unsupported Q-values and is suited to the current offline action setup.", warning: "" },
  { name: "iql", title: "Implicit Q-Learning · IQL", tag: "OFFLINE", detail: "Expectile value learning with advantage-weighted policy extraction.", warning: "Current dataset has no logged agent actions; this run records a reward-derived behavior proxy." },
  { name: "bcq", title: "Batch-Constrained Q-Learning · BCQ", tag: "OFFLINE", detail: "Constrains policy actions using an explicit behavior model.", warning: "Current dataset has no logged agent actions; this run records a reward-derived behavior proxy." },
];

export function TrainingLauncher() {
  const navigate = useNavigate(); const [selected,setSelected]=useState<string[]>([]); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  const allSelected = selected.length === MODELS.length;
  const selectionLabel = useMemo(() => selected.length === 0 ? "No model selected" : `${selected.length} model${selected.length===1?"":"s"} selected`, [selected.length]);
  const toggle=(name:string)=>setSelected(current=>current.includes(name)?current.filter(x=>x!==name):[...current,name]);
  const toggleAll=()=>setSelected(allSelected?[]:MODELS.map(x=>x.name));
  async function start(){if(!selected.length){setError("Select at least one algorithm before starting training.");return}setBusy(true);setError("");try{await startAuthoritativeFullTraining(selected);navigate("/training/live")}catch(e){setError(e instanceof Error?e.message:String(e));setBusy(false)}}
  return <div className="lux-training">
    <section className="lux-hero"><div><div className="lux-kicker">RL CONTROL ROOM · MODEL LAB</div><h1>Choose the algorithms to train</h1><p>Select the actual offline-RL algorithms for this experiment. Each selected algorithm gets its own adaptive training run, fresh 40-alert cycle, model version, and validation record.</p></div><div className="lux-hero-actions"><button className="lux-button lux-button--ghost" onClick={toggleAll}>{allSelected?"Clear selection":"Select all 4"}</button><button className="lux-button lux-button--primary" disabled={busy||!selected.length} onClick={()=>void start()}>{busy?"Launching…":"Train selected models"}</button></div></section>
    {error&&<div className="lux-alert">{error}</div>}
    <section className="lux-card"><div className="lux-card-head"><div><div className="lux-card-label">ALGORITHM SELECTION</div><h2>{selectionLabel}</h2></div><span className="lux-pill">No hidden model selection</span></div><div className="lux-model-selector-grid lux-model-selector-grid--four">{MODELS.map(model=>{const active=selected.includes(model.name);return <button key={model.name} type="button" className={`lux-model-choice ${active?"lux-model-choice--selected":""}`} onClick={()=>toggle(model.name)}><div className="lux-model-choice__top"><span className="lux-model-choice__tag">{model.tag}</span><span className="lux-model-choice__check">{active?"✓":""}</span></div><strong>{model.title}</strong><p>{model.detail}</p>{model.warning&&<small className="lux-model-choice__warning">{model.warning}</small>}<small>{active?"Selected for this experiment":"Click to include"}</small></button>})}</div></section>
    <section className="lux-main-grid"><article className="lux-card"><div className="lux-card-label">AUTOMATIC EXECUTION</div><h2>What happens after selection</h2><div className="lux-rule"><b>01</b><div><strong>Adaptive convergence</strong><p>4,000 is only a safety ceiling. Warm-up, patience, flat-validation detection, and persistent-decline detection stop a converged model early.</p></div></div><div className="lux-rule"><b>02</b><div><strong>Fresh 40-alert cycle</strong><p>Every selected algorithm gets an untouched MongoDB cycle built from the immutable live source/processed/lineage files.</p></div></div><div className="lux-rule"><b>03</b><div><strong>Champion selection</strong><p>Validation chooses the winner. The unseen test set is evaluated only after the champion is selected.</p></div></div></article><article className="lux-card"><div className="lux-card-label">RESOURCE SAFETY</div><h2>Single-flight training</h2><p className="lux-muted">Only one experiment process may run at a time. The Stop control terminates the managed process group and cleans orphaned sequential runners before another run can start.</p><div className="lux-mini-grid" style={{marginTop:14}}><div><span>Algorithms</span><strong>4</strong></div><div><span>Minimum</span><strong>1 selected</strong></div><div><span>Maximum</span><strong>4 selected</strong></div><div><span>Live holdout</span><strong>40 / algorithm</strong></div></div><div className="lux-explain"><strong>IQL / BCQ data note</strong><p>The current dataset has no historical agent-action field. Those algorithms therefore use an explicit reward-derived behavior proxy and the run artifacts record that limitation.</p></div></article></section>
  </div>;
}
export default TrainingLauncher;
