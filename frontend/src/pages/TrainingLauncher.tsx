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

type NumericFieldProps = { label:string; value:number; onChange:(value:number)=>void; min:number; max:number; step:number; hint?:string; integer?:boolean };
function NumericField({label,value,onChange,min,max,step,hint,integer=false}:NumericFieldProps){
  const safe=Number.isFinite(value)?value:min;
  const set=(raw:number)=>onChange(integer?Math.round(raw):raw);
  return <div style={{display:"grid",gap:7}}>
    <div style={{display:"flex",justifyContent:"space-between",gap:12,alignItems:"center"}}><label style={{fontWeight:700,color:"#24324a"}}>{label}</label><input type="number" value={integer?Math.round(safe):safe} min={min} max={max} step={step} onChange={e=>set(Number(e.target.value))} style={{width:120,border:"1px solid #cfd8e6",borderRadius:10,padding:"8px 10px",fontWeight:700,textAlign:"right"}}/></div>
    <input type="range" value={safe} min={min} max={max} step={step} onChange={e=>set(Number(e.target.value))} style={{width:"100%"}}/>
    {hint&&<small style={{color:"#6b7b93"}}>{hint}</small>}
  </div>;
}

const DEFAULT_GLOBAL:TrainingGlobalConfig={max_epochs:4000,min_epochs:20,patience:10,validation_every:2,min_delta:0.001,max_total_updates:5_000_000,chunk_size:100_000,train_ratio:0.80,validation_seed:4242,seed:42,target_update:1,metric_sample_rows:10_000,telemetry_window:40};
const DEFAULT_REWARDS:RewardConfig={BenignPositive:{allow:1.5,block:-1,human_review:0.25},FalsePositive:{allow:1.5,block:-2,human_review:0.25},TruePositive:{allow:-2,block:2,human_review:1},Unknown:{allow:-1,block:0.5,human_review:1.5}};
const DEFAULT_MODEL=(name:string):TrainingModelConfig=>({name,learning_rate:0.001,gamma:0.95,batch_size:2048,hidden_dim:128,max_total_updates:5_000_000,cql_alpha:1,iql_expectile:0.7,iql_beta:3,bcq_threshold:0.05});
function modelInfo(name:string){return MODELS.find(m=>m.name===name)??MODELS[0];}

export function TrainingLauncher(){
  const navigate=useNavigate();
  const [selected,setSelected]=useState<string[]>([]);
  const [step,setStep]=useState(0);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [global,setGlobal]=useState<TrainingGlobalConfig>(DEFAULT_GLOBAL);
  const [modelConfigs,setModelConfigs]=useState<Record<string,TrainingModelConfig>>(Object.fromEntries(MODELS.map(m=>[m.name,DEFAULT_MODEL(m.name)])));
  const [rewards,setRewards]=useState<RewardConfig>(DEFAULT_REWARDS);

  const allSelected=selected.length===MODELS.length;
  const configured=selected[step];
  const complete=selected.length>0&&step>=selected.length;
  const selectionLabel=useMemo(()=>selected.length===0?"No model selected":`${selected.length} model${selected.length===1?"":"s"} selected`,[selected.length]);
  const toggle=(name:string)=>{setSelected(cur=>cur.includes(name)?cur.filter(x=>x!==name):[...cur,name]);setStep(0);};
  const toggleAll=()=>{setSelected(allSelected?[]:MODELS.map(m=>m.name));setStep(0);};
  const updateGlobal=<K extends keyof TrainingGlobalConfig>(key:K,value:TrainingGlobalConfig[K])=>setGlobal(cur=>({...cur,[key]:value}));
  const updateModel=<K extends keyof TrainingModelConfig>(name:string,key:K,value:TrainingModelConfig[K])=>setModelConfigs(cur=>({...cur,[name]:{...cur[name],[key]:value}}));
  const updateReward=(label:string,action:string,value:number)=>setRewards(cur=>({...cur,[label]:{...(cur[label]??{}),[action]:value}}));

  function next(){
    if(!configured)return;
    if(modelConfigs[configured].batch_size<=0){setError("Batch size must be positive.");return;}
    setError("");
    setStep(s=>s<selected.length-1?s+1:selected.length);
  }
  async function start(){
    if(!selected.length){setError("Select at least one algorithm before starting training.");return;}
    if(global.min_epochs>global.max_epochs){setError("Minimum epochs cannot exceed maximum epochs.");return;}
    setBusy(true);setError("");
    try{await startAuthoritativeFullTraining({modelNames:selected,training:global,modelConfigs:selected.map(n=>modelConfigs[n]),rewards});navigate("/training/live");}
    catch(e){setError(e instanceof Error?e.message:String(e));setBusy(false);}
  }

  return <div className="lux-training">
    <section className="lux-hero"><div><div className="lux-kicker">RL CONTROL ROOM · HARD-DATA MODEL LAB</div><h1>Choose algorithms & training parameters</h1><p>Build the run progressively: select models, configure them one at a time, then review the final training policy before launch.</p></div><div className="lux-hero-actions"><button className="lux-button lux-button--ghost" onClick={toggleAll}>{allSelected?"Clear selection":"Select all 4"}</button></div></section>
    {error&&<div className="lux-alert">{error}</div>}

    <section className="lux-card"><div className="lux-card-head"><div><div className="lux-card-label">STEP 1 · ALGORITHM SELECTION</div><h2>{selectionLabel}</h2></div><span className="lux-pill">Hard data · no synthetic fallback</span></div>
      <div className="lux-model-selector-grid lux-model-selector-grid--four">{MODELS.map(m=>{const active=selected.includes(m.name);return <button key={m.name} type="button" className={`lux-model-choice ${active?"lux-model-choice--selected":""}`} onClick={()=>toggle(m.name)}><div className="lux-model-choice__top"><span className="lux-model-choice__tag">{m.tag}</span><span className="lux-model-choice__check">{active?"✓":""}</span></div><strong>{m.title}</strong><p>{m.detail}</p>{m.warning&&<small className="lux-model-choice__warning">{m.warning}</small>}<small>{active?"Selected · configure below":"Click to include"}</small></button>;})}</div>
    </section>

    {configured&&!complete&&<section className="lux-card" style={{marginTop:18}}><div className="lux-card-head"><div><div className="lux-card-label">STEP {step+2} · MODEL CONFIGURATION</div><h2>{modelInfo(configured).title}</h2></div><span className="lux-pill">Model {step+1} of {selected.length}</span></div><p className="lux-muted">Only this model is shown now. Continue to unlock the next selected model.</p>{modelInfo(configured).warning&&<div className="lux-explain"><strong>Data note</strong><p>{modelInfo(configured).warning}</p></div>}
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(260px,1fr))",gap:22,marginTop:18}}><NumericField label="Learning rate" value={modelConfigs[configured].learning_rate} onChange={v=>updateModel(configured,"learning_rate",v)} min={0.0000001} max={1} step={0.0001}/><NumericField label="Discount factor γ" value={modelConfigs[configured].gamma} onChange={v=>updateModel(configured,"gamma",v)} min={0} max={1} step={0.01}/><NumericField label="Batch size" value={modelConfigs[configured].batch_size} onChange={v=>updateModel(configured,"batch_size",v)} min={32} max={16384} step={32} integer/><NumericField label="Hidden dimension" value={modelConfigs[configured].hidden_dim} onChange={v=>updateModel(configured,"hidden_dim",v)} min={16} max={2048} step={16} integer/><NumericField label="Candidate max updates" value={modelConfigs[configured].max_total_updates} onChange={v=>updateModel(configured,"max_total_updates",v)} min={1} max={100000000} step={1000} integer/>{configured==="cql"&&<NumericField label="CQL α" value={modelConfigs[configured].cql_alpha??1} onChange={v=>updateModel(configured,"cql_alpha",v)} min={0} max={100} step={0.01}/>} {configured==="iql"&&<><NumericField label="IQL expectile τ" value={modelConfigs[configured].iql_expectile??0.7} onChange={v=>updateModel(configured,"iql_expectile",v)} min={0.01} max={0.99} step={0.01}/><NumericField label="IQL behavior temperature β" value={modelConfigs[configured].iql_beta??3} onChange={v=>updateModel(configured,"iql_beta",v)} min={0.01} max={100} step={0.1}/></>} {configured==="bcq"&&<NumericField label="BCQ action threshold" value={modelConfigs[configured].bcq_threshold??0.05} onChange={v=>updateModel(configured,"bcq_threshold",v)} min={0} max={1} step={0.01}/>}</div>
      <div style={{display:"flex",justifyContent:"flex-end",marginTop:24}}><button className="lux-button lux-button--primary" onClick={next}>{step<selected.length-1?`Continue to ${modelInfo(selected[step+1]).title}`:"Continue to training policy"}</button></div>
    </section>}

    {complete&&<>
      <section className="lux-card" style={{marginTop:18}}><div className="lux-card-head"><div><div className="lux-card-label">STEP {selected.length+2} · TRAINING POLICY</div><h2>Shared training control</h2></div><span className="lux-pill">Defaults are pre-filled · editable</span></div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(260px,1fr))",gap:22}}><NumericField label="Maximum epochs" value={global.max_epochs} onChange={v=>updateGlobal("max_epochs",v)} min={1} max={100000} step={1} integer hint="Hard ceiling; early stopping can terminate earlier."/><NumericField label="Minimum epochs" value={global.min_epochs} onChange={v=>updateGlobal("min_epochs",v)} min={1} max={100000} step={1} integer/><NumericField label="Early-stop patience" value={global.patience} onChange={v=>updateGlobal("patience",v)} min={1} max={10000} step={1} integer/><NumericField label="Validation every N epochs" value={global.validation_every} onChange={v=>updateGlobal("validation_every",v)} min={1} max={10000} step={1} integer/><NumericField label="Minimum validation improvement" value={global.min_delta} onChange={v=>updateGlobal("min_delta",v)} min={0} max={10} step={0.0001}/><NumericField label="Maximum optimizer updates" value={global.max_total_updates} onChange={v=>updateGlobal("max_total_updates",v)} min={1} max={100000000} step={1000} integer/><NumericField label="Streaming chunk size" value={global.chunk_size} onChange={v=>updateGlobal("chunk_size",v)} min={1000} max={1000000} step={1000} integer/><NumericField label="TRAIN ratio" value={global.train_ratio} onChange={v=>updateGlobal("train_ratio",v)} min={0.5} max={0.95} step={0.01}/><NumericField label="Validation seed" value={global.validation_seed} onChange={v=>updateGlobal("validation_seed",v)} min={0} max={2147483647} step={1} integer/><NumericField label="Training seed" value={global.seed} onChange={v=>updateGlobal("seed",v)} min={0} max={2147483647} step={1} integer/><NumericField label="Target-network update interval" value={global.target_update} onChange={v=>updateGlobal("target_update",v)} min={1} max={10000} step={1} integer/><NumericField label="Metric sample rows" value={global.metric_sample_rows} onChange={v=>updateGlobal("metric_sample_rows",v)} min={0} max={1000000} step={1000} integer/><NumericField label="Telemetry window" value={global.telemetry_window} onChange={v=>updateGlobal("telemetry_window",v)} min={5} max={500} step={1} integer hint="How many persisted epochs the monitor shows."/></div>
      </section>

      <section className="lux-card" style={{marginTop:18}}><div className="lux-card-head"><div><div className="lux-card-label">STEP {selected.length+3} · REWARD POLICY</div><h2>Counterfactual action rewards</h2></div><span className="lux-pill">Current values are pre-filled</span></div><p className="lux-muted" style={{marginTop:0}}>Edit the action utility used by the contextual learner. TEST and live remain evaluation-only.</p><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",minWidth:720}}><thead><tr>{["Class","Allow","Block","Human review"].map(h=><th key={h} style={{textAlign:h==="Class"?"left":"right",padding:"10px 12px",borderBottom:"1px solid #dbe3ee",color:"#5e718c"}}>{h}</th>)}</tr></thead><tbody>{Object.entries(rewards).map(([label,values])=><tr key={label}><td style={{padding:"12px",fontWeight:700}}>{label}</td>{(["allow","block","human_review"] as const).map(action=><td key={action} style={{padding:"12px",textAlign:"right"}}><input type="number" value={values[action]??0} step="0.05" onChange={e=>updateReward(label,action,Number(e.target.value))} style={{width:110,border:"1px solid #cfd8e6",borderRadius:10,padding:"8px 10px",fontWeight:700,textAlign:"right"}}/></td>)}</tr>)}</tbody></table></div></section>

      <section className="lux-card" style={{marginTop:18}}><div className="lux-card-head"><div><div className="lux-card-label">FINAL STEP · DYNAMIC RUN SUMMARY</div><h2>Ready to train</h2></div><span className="lux-pill">Configuration frozen when launched</span></div><div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(230px,1fr))",gap:14}}><div className="lux-mini-grid"><div><span>Models</span><strong>{selected.length}</strong></div><div><span>Max epochs</span><strong>{global.max_epochs.toLocaleString()}</strong></div><div><span>Patience</span><strong>{global.patience}</strong></div><div><span>Telemetry window</span><strong>{global.telemetry_window}</strong></div></div><div className="lux-mini-grid"><div><span>Batch</span><strong>{selected.map(n=>modelConfigs[n].batch_size).join(" / ")}</strong></div><div><span>Validation</span><strong>Every {global.validation_every}</strong></div><div><span>Max updates</span><strong>{global.max_total_updates.toLocaleString()}</strong></div><div><span>Live holdout</span><strong>80 alerts</strong></div></div></div><div style={{display:"flex",justifyContent:"flex-end",gap:12,marginTop:20}}><button className="lux-button lux-button--ghost" onClick={()=>setStep(selected.length-1)}>Back to last model</button><button className="lux-button lux-button--primary" disabled={busy} onClick={()=>void start()}>{busy?"Launching…":`Train ${selected.length===1?modelInfo(selected[0]).title:`${selected.length} models`}`}</button></div></section>
    </>}
  </div>;
}

export default TrainingLauncher;
