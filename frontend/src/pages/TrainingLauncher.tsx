import "./TrainingLauncher.css";

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  startAuthoritativeFullTraining,
  type RewardConfig,
  type TrainingGlobalConfig,
  type TrainingModelConfig,
} from "../services/training.service";

const MODELS = [
  { name: "double_dqn", title: "Double DQN", tag: "BASELINE", detail: "Alert-level one-step counterfactual Double DQN on the hard dataset.", warning: "" },
  { name: "cql", title: "Conservative Q-Learning · CQL", tag: "CONSERVATIVE", detail: "Conservative offline Q-learning for the real historical alert distribution.", warning: "" },
  { name: "iql", title: "Implicit Q-Learning · IQL", tag: "OFFLINE", detail: "Expectile value learning with a reward-derived behavior proxy.", warning: "No historical agent-action field exists in the source data." },
  { name: "bcq", title: "Batch-Constrained Q-Learning · BCQ", tag: "OFFLINE", detail: "Batch-constrained offline policy learning with a reward-derived behavior proxy.", warning: "No historical agent-action field exists in the source data." },
] as const;

type NumericFieldProps = {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step: number;
  hint?: string;
  integer?: boolean;
};

function NumericField({ label, value, onChange, min, max, step, hint, integer = false }: NumericFieldProps) {
  const safe = Number.isFinite(value) ? value : min;
  return <div style={{ display: "grid", gap: 7 }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
      <label style={{ fontWeight: 700, color: "#24324a" }}>{label}</label>
      <input
        type="number"
        value={integer ? Math.round(safe) : safe}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(integer ? Math.round(Number(event.target.value)) : Number(event.target.value))}
        style={{ width: 120, border: "1px solid #cfd8e6", borderRadius: 10, padding: "8px 10px", fontWeight: 700, textAlign: "right" }}
      />
    </div>
    <input
      type="range"
      value={safe}
      min={min}
      max={max}
      step={step}
      onChange={(event) => onChange(integer ? Math.round(Number(event.target.value)) : Number(event.target.value))}
      style={{ width: "100%" }}
    />
    {hint && <small style={{ color: "#6b7b93" }}>{hint}</small>}
  </div>;
}

const DEFAULT_GLOBAL: TrainingGlobalConfig = {
  max_epochs: 4000,
  min_epochs: 20,
  patience: 10,
  validation_every: 2,
  min_delta: 0.001,
  max_total_updates: 5_000_000,
  chunk_size: 100_000,
  train_ratio: 0.80,
  validation_seed: 4242,
  seed: 42,
  target_update: 1,
  metric_sample_rows: 10_000,
  telemetry_window: 40,
};

const DEFAULT_REWARDS: RewardConfig = {
  BenignPositive: { allow: 1.5, block: -1, human_review: 0.25 },
  FalsePositive: { allow: 1.5, block: -2, human_review: 0.25 },
  TruePositive: { allow: -2, block: 2, human_review: 1 },
  Unknown: { allow: -1, block: 0.5, human_review: 1.5 },
};

const DEFAULT_MODEL = (name: string): TrainingModelConfig => ({
  name,
  learning_rate: 0.001,
  gamma: 0.95,
  batch_size: 2048,
  hidden_dim: 128,
  max_total_updates: 5_000_000,
  cql_alpha: 1,
  iql_expectile: 0.7,
  iql_beta: 3,
  bcq_threshold: 0.05,
});

function modelTitle(name: string) {
  return MODELS.find((model) => model.name === name)?.title ?? name;
}

export function TrainingLauncher() {
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [global, setGlobal] = useState<TrainingGlobalConfig>(DEFAULT_GLOBAL);
  const [modelConfigs, setModelConfigs] = useState<Record<string, TrainingModelConfig>>(
    Object.fromEntries(MODELS.map((model) => [model.name, DEFAULT_MODEL(model.name)])),
  );
  const [rewards, setRewards] = useState<RewardConfig>(DEFAULT_REWARDS);

  const allSelected = selected.length === MODELS.length;
  const selectionLabel = useMemo(
    () => selected.length === 0 ? "No model selected" : `${selected.length} model${selected.length === 1 ? "" : "s"} selected`,
    [selected.length],
  );

  const toggle = (name: string) => setSelected((current) => current.includes(name) ? current.filter((x) => x !== name) : [...current, name]);
  const toggleAll = () => setSelected(allSelected ? [] : MODELS.map((x) => x.name));

  const updateGlobal = <K extends keyof TrainingGlobalConfig>(key: K, value: TrainingGlobalConfig[K]) => {
    setGlobal((current) => ({ ...current, [key]: value }));
  };

  const updateModel = <K extends keyof TrainingModelConfig>(name: string, key: K, value: TrainingModelConfig[K]) => {
    setModelConfigs((current) => ({
      ...current,
      [name]: { ...current[name], [key]: value },
    }));
  };

  const updateReward = (label: string, action: string, value: number) => {
    setRewards((current) => ({
      ...current,
      [label]: { ...(current[label] ?? {}), [action]: value },
    }));
  };

  async function start() {
    if (!selected.length) {
      setError("Select at least one algorithm before starting training.");
      return;
    }
    if (global.min_epochs > global.max_epochs) {
      setError("Minimum epochs cannot exceed maximum epochs.");
      return;
    }
    if (selected.some((name) => modelConfigs[name].batch_size <= 0)) {
      setError("Batch size must be positive for every selected algorithm.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await startAuthoritativeFullTraining({
        modelNames: selected,
        training: global,
        modelConfigs: selected.map((name) => modelConfigs[name]),
        rewards,
      });
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
        <h1>Choose algorithms & training parameters</h1>
        <p>Every selected algorithm gets an explicit configuration. The run uses the incident-disjoint hard dataset, unseen TEST evaluation, and the complete 80-alert live holdout.</p>
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
        {MODELS.map((model) => {
          const active = selected.includes(model.name);
          return <button key={model.name} type="button" className={`lux-model-choice ${active ? "lux-model-choice--selected" : ""}`} onClick={() => toggle(model.name)}>
            <div className="lux-model-choice__top"><span className="lux-model-choice__tag">{model.tag}</span><span className="lux-model-choice__check">{active ? "✓" : ""}</span></div>
            <strong>{model.title}</strong>
            <p>{model.detail}</p>
            {model.warning && <small className="lux-model-choice__warning">{model.warning}</small>}
            <small>{active ? "Selected · configure below" : "Click to include"}</small>
          </button>;
        })}
      </div>
    </section>

    <section className="lux-card" style={{ marginTop: 18 }}>
      <div className="lux-card-head"><div><div className="lux-card-label">RUN-LEVEL PARAMETERS</div><h2>Training control</h2></div><span className="lux-pill">Applied to the real-data run</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 22 }}>
        <NumericField label="Maximum epochs" value={global.max_epochs} onChange={(v) => updateGlobal("max_epochs", v)} min={1} max={100000} step={1} integer hint="Hard ceiling; early stopping can terminate earlier." />
        <NumericField label="Minimum epochs" value={global.min_epochs} onChange={(v) => updateGlobal("min_epochs", v)} min={1} max={100000} step={1} integer hint="Early stopping is disabled before this epoch." />
        <NumericField label="Early-stop patience" value={global.patience} onChange={(v) => updateGlobal("patience", v)} min={1} max={10000} step={1} integer hint="Validation checks without improvement before stopping." />
        <NumericField label="Validation every N epochs" value={global.validation_every} onChange={(v) => updateGlobal("validation_every", v)} min={1} max={10000} step={1} integer />
        <NumericField label="Minimum validation improvement" value={global.min_delta} onChange={(v) => updateGlobal("min_delta", v)} min={0} max={10} step={0.0001} />
        <NumericField label="Maximum optimizer updates" value={global.max_total_updates} onChange={(v) => updateGlobal("max_total_updates", v)} min={1} max={100000000} step={1000} integer />
        <NumericField label="Streaming chunk size" value={global.chunk_size} onChange={(v) => updateGlobal("chunk_size", v)} min={1000} max={1000000} step={1000} integer hint="RAM/performance trade-off." />
        <NumericField label="TRAIN ratio inside TRAIN/VALIDATION" value={global.train_ratio} onChange={(v) => updateGlobal("train_ratio", v)} min={0.5} max={0.95} step={0.01} />
        <NumericField label="Validation seed" value={global.validation_seed} onChange={(v) => updateGlobal("validation_seed", v)} min={0} max={2147483647} step={1} integer />
        <NumericField label="Training seed" value={global.seed} onChange={(v) => updateGlobal("seed", v)} min={0} max={2147483647} step={1} integer />
        <NumericField label="Target-network update interval" value={global.target_update} onChange={(v) => updateGlobal("target_update", v)} min={1} max={10000} step={1} integer />
        <NumericField label="Metric sample rows" value={global.metric_sample_rows} onChange={(v) => updateGlobal("metric_sample_rows", v)} min={0} max={1000000} step={1000} integer />
        <NumericField label="Telemetry window" value={global.telemetry_window} onChange={(v) => updateGlobal("telemetry_window", v)} min={5} max={500} step={1} integer hint="How many persisted epochs the training monitor should show." />
      </div>
    </section>

    {selected.map((name) => {
      const cfg = modelConfigs[name];
      return <section key={name} className="lux-card" style={{ marginTop: 18 }}>
        <div className="lux-card-head"><div><div className="lux-card-label">ALGORITHM PARAMETERS</div><h2>{modelTitle(name)}</h2></div><span className="lux-pill">Independent candidate configuration</span></div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 22 }}>
          <NumericField label="Learning rate" value={cfg.learning_rate} onChange={(v) => updateModel(name, "learning_rate", v)} min={0.0000001} max={1} step={0.0001} />
          <NumericField label="Discount factor γ" value={cfg.gamma} onChange={(v) => updateModel(name, "gamma", v)} min={0} max={1} step={0.01} />
          <NumericField label="Batch size" value={cfg.batch_size} onChange={(v) => updateModel(name, "batch_size", v)} min={32} max={16384} step={32} integer />
          <NumericField label="Hidden dimension" value={cfg.hidden_dim} onChange={(v) => updateModel(name, "hidden_dim", v)} min={16} max={2048} step={16} integer />
          <NumericField label="Candidate max updates" value={cfg.max_total_updates} onChange={(v) => updateModel(name, "max_total_updates", v)} min={1} max={100000000} step={1000} integer />
          {name === "cql" && <NumericField label="CQL α" value={cfg.cql_alpha ?? 1} onChange={(v) => updateModel(name, "cql_alpha", v)} min={0} max={100} step={0.01} hint="Conservative penalty strength." />}
          {name === "iql" && <>
            <NumericField label="IQL expectile τ" value={cfg.iql_expectile ?? 0.7} onChange={(v) => updateModel(name, "iql_expectile", v)} min={0.01} max={0.99} step={0.01} />
            <NumericField label="IQL behavior temperature β" value={cfg.iql_beta ?? 3} onChange={(v) => updateModel(name, "iql_beta", v)} min={0.01} max={100} step={0.1} />
          </>}
          {name === "bcq" && <NumericField label="BCQ action threshold" value={cfg.bcq_threshold ?? 0.05} onChange={(v) => updateModel(name, "bcq_threshold", v)} min={0} max={1} step={0.01} hint="Minimum relative behavior probability." />}
        </div>
      </section>;
    })}

    <section className="lux-card" style={{ marginTop: 18 }}>
      <div className="lux-card-head"><div><div className="lux-card-label">REWARD POLICY</div><h2>Counterfactual action rewards</h2></div><span className="lux-pill">Applied consistently to TRAIN / VALIDATION / TEST / LIVE evaluation</span></div>
      <p className="lux-muted" style={{ marginTop: 0 }}>These values define the operational preference the one-step contextual learner optimizes. Test and live data are never used to tune them automatically.</p>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 720 }}>
          <thead><tr>{["Class", "Allow", "Block", "Human review"].map((header) => <th key={header} style={{ textAlign: header === "Class" ? "left" : "right", padding: "10px 12px", borderBottom: "1px solid #dbe3ee", color: "#5e718c" }}>{header}</th>)}</tr></thead>
          <tbody>{Object.entries(rewards).map(([label, values]) => <tr key={label}>
            <td style={{ padding: "12px", fontWeight: 800 }}>{label}</td>
            {(["allow", "block", "human_review"] as const).map((action) => <td key={action} style={{ padding: "12px", textAlign: "right" }}><input type="number" step="0.05" value={values[action] ?? 0} onChange={(e) => updateReward(label, action, Number(e.target.value))} style={{ width: 110, border: "1px solid #cfd8e6", borderRadius: 10, padding: "8px 10px", textAlign: "right" }} /></td>)}
          </tr>)}</tbody>
        </table>
      </div>
    </section>

    <section className="lux-main-grid" style={{ marginTop: 18 }}>
      <article className="lux-card">
        <div className="lux-card-label">EXECUTION CONTRACT</div>
        <h2>What each number actually changes</h2>
        <div className="lux-rule"><b>01</b><div><strong>Epoch / patience / min-delta</strong><p>Controls early stopping and best-checkpoint selection on validation.</p></div></div>
        <div className="lux-rule"><b>02</b><div><strong>Batch / chunk / thread-sensitive settings</strong><p>Controls RAM usage, CPU throughput, and optimizer update cadence without loading the full dataset.</p></div></div>
        <div className="lux-rule"><b>03</b><div><strong>Algorithm-specific controls</strong><p>CQL α, IQL expectile/β, and BCQ threshold are attached to the corresponding candidate only.</p></div></div>
        <div className="lux-rule"><b>04</b><div><strong>Reward matrix</strong><p>Changes the action utility the contextual learner optimizes; the 80-alert live set remains a final holdout.</p></div></div>
      </article>
      <article className="lux-card">
        <div className="lux-card-label">RESOURCE SAFETY</div>
        <h2>Dynamic does not mean unsafe</h2>
        <p className="lux-muted">The API validates bounds before launching the subprocess. One experiment remains active at a time, and the hard dataset is still streamed in bounded chunks.</p>
        <div className="lux-mini-grid" style={{ marginTop: 14 }}>
          <div><span>Algorithms</span><strong>4</strong></div>
          <div><span>Minimum</span><strong>1 selected</strong></div>
          <div><span>Maximum</span><strong>4 selected</strong></div>
          <div><span>Live holdout</span><strong>80 alerts</strong></div>
        </div>
      </article>
    </section>
  </div>;
}

export default TrainingLauncher;
