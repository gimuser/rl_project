import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getTrainingRuns, type TrainingRunSummary } from "../services/training.service";
import "./TrainingLive.css";

const nf = new Intl.NumberFormat("en-US");

export function TrainingHistory() {
  const [runs, setRuns] = useState<TrainingRunSummary[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    getTrainingRuns()
      .then((response) => {
        const ordered = [...(response.runs ?? [])].sort((a, b) => {
          const ta = Date.parse(String((a as TrainingRunSummary & { last_updated_at?: string }).last_updated_at ?? "")) || 0;
          const tb = Date.parse(String((b as TrainingRunSummary & { last_updated_at?: string }).last_updated_at ?? "")) || 0;
          return tb - ta;
        });
        setRuns(ordered);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <div className="live-page">
      <header className="live-hero">
        <div>
          <div className="live-kicker">RL CONTROL ROOM · TRAINING HISTORY</div>
          <h1>Previous training runs</h1>
          <p>Load a persisted run to inspect its epoch metrics, best checkpoint and evaluation results without starting another training job.</p>
        </div>
        <div className="live-actions">
          <Link className="live-btn" to="/training/live">Current monitor</Link>
          <Link className="live-btn" to="/training">New training</Link>
        </div>
      </header>

      {error && <div className="live-error">{error}</div>}

      <section className="run-history-list">
        {runs.length === 0 && <div className="chart-empty">No persisted training runs are available yet.</div>}
        {runs.map((run) => (
          <article key={run.run_id} className="best-card">
            <span>{run.current ? "CURRENT RUN" : "ARCHIVED RUN"}</span>
            <strong>{run.display_name ?? run.algorithm ?? "Training run"}</strong>
            <small>
              {run.actual_epochs ? `${nf.format(run.actual_epochs)} epochs` : "Epoch count unavailable"}
              {run.best_epoch ? ` · best epoch ${nf.format(run.best_epoch)}` : ""}
              {run.metric_count ? ` · ${nf.format(run.metric_count)} persisted metric points` : ""}
            </small>
            <div className="live-actions">
              <Link className="live-btn" to={`/training/runs/${encodeURIComponent(run.run_id)}`}>Load run</Link>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
