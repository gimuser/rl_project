import "./TrainingLauncher.css";

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { startAuthoritativeFullTraining } from "../services/training.service";

const MODELS = [
  { name: "double_dqn", title: "Double DQN", tag: "BASELINE", detail: "Alert-level one-step counterfactual Double DQN on the hard dataset.", warning: "" },
  { name: "cql", title: "Conservative Q-Learning · CQL", tag: "CONSERVATIVE", detail: "Conservative offline Q-learning for the real historical alert distribution.", warning: "" },
  { name: "iql", title: "Implicit Q-Learning · IQL", tag: "OFFLINE", detail: "Expectile value learning with a reward-derived behavior proxy.", warning: "No historical agent-action field exists in the source data." },
  { name: "bcq", title: "Batch-Constrained Q-Learning · BCQ", tag: "OFFLINE", detail: "Batch-constrained offline policy learning with a reward-derived behavior proxy.", warning: "No historical agent-action field exists in the source data." },
];

export function TrainingLauncher() {
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const allSelected = selected.length === MODELS.length;
  const selectionLabel = useMemo(
    () => selected.length === 0 ? "No model selected" : `${selected.length} model${selected.length === 1 ? "" : "s"} selected`,
    [selected.length],
  );
  const toggle = (name: string) => setSelected(current => current.includes(name) ? current.filter(x => x !== name) : [...current, name]);
  const toggleAll = () => setSelected(allSelected ? [] : MODELS.map(x => x.name));
  async function start() {
    if (!selected.length) {
      setError("Select at least one algorithm before starting training.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await startAuthoritativeFullTraining(selected);
      navigate("/training/live");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }
  return <div className="lux-training">
    <section className="lux-hero">
      <div>
        <div className="lux-kicker">RL CONTROL ROOM · HARD-DATA MODEL LAB</div>
        <h1>Choose the algorithms to train</h1>
        <p>Select the offline-RL algorithms for the real alert-level experiment. Training streams the incident-disjoint hard dataset and the final champion is evaluated on the unseen TEST set and the 80-alert live holdout.</p>
      </div>
      <div className="lux-hero-actions">
        <button className="lux-button lux-button--ghost" onClick={toggleAll}>{allSelected ? "Clear selection" : "Select all 4"}</button>
        <button className="lux-button lux-button--primary" disabled={busy || !selected.length} onClick={() => void start()}>{busy ? "Launching…" : "Train selected models"}</button>
      </div>
    </section>
    {error && <div className="lux-alert">{error}</div>}
    <section className="lux-card">
      <div className="lux-card-head">
        <div><div className="lux-card-label">ALGORITHM SELECTION</div><h2>{selectionLabel}</h2></div>
        <span className="lux-pill">Hard data · no synthetic fallback</span>
      </div>
      <div className="lux-model-selector-grid lux-model-selector-grid--four">
        {MODELS.map(model => {
          const active = selected.includes(model.name);
          return <button key={model.name} type="button" className={`lux-model-choice ${active ? "lux-model-choice--selected" : ""}`} onClick={() => toggle(model.name)}>
            <div className="lux-model-choice__top"><span className="lux-model-choice__tag">{model.tag}</span><span className="lux-model-choice__check">{active ? "✓" : ""}</span></div>
            <strong>{model.title}</strong>
            <p>{model.detail}</p>
            {model.warning && <small className="lux-model-choice__warning">{model.warning}</small>}
            <small>{active ? "Selected for this experiment" : "Click to include"}</small>
          </button>;
        })}
      </div>
    </section>
    <section className="lux-main-grid">
      <article className="lux-card">
        <div className="lux-card-label">HARD-DATA EXECUTION</div>
        <h2>What happens after selection</h2>
        <div className="lux-rule"><b>01</b><div><strong>Alert-level streaming</strong><p>Training reads the full multi-million-row processed CSV in RAM-bounded chunks. It does not collapse the experiment to one representative row per incident.</p></div></div>
        <div className="lux-rule"><b>02</b><div><strong>Incident-disjoint validation</strong><p>The TRAIN/VALIDATION split is created at IncidentId level. The unseen TEST incidents remain isolated and are never used for model selection.</p></div></div>
        <div className="lux-rule"><b>03</b><div><strong>80-alert live holdout</strong><p>After the champion is selected, the live cycle processes all 80 real live alerts from data_alert/live_processed.csv.</p></div></div>
      </article>
      <article className="lux-card">
        <div className="lux-card-label">RESOURCE SAFETY</div>
        <h2>Single-flight training</h2>
        <p className="lux-muted">Only one experiment process may run at a time. The Stop control terminates the managed process group before another run can start.</p>
        <div className="lux-mini-grid" style={{ marginTop: 14 }}>
          <div><span>Algorithms</span><strong>4</strong></div>
          <div><span>Minimum</span><strong>1 selected</strong></div>
          <div><span>Maximum</span><strong>4 selected</strong></div>
          <div><span>Live holdout</span><strong>80 alerts</strong></div>
        </div>
        <div className="lux-explain"><strong>IQL / BCQ data note</strong><p>The source has no historical agent-action field. These algorithms therefore use the explicit reward-derived behavior proxy already recorded by the offline-RL pipeline.</p></div>
      </article>
    </section>
  </div>;
}

export default TrainingLauncher;
