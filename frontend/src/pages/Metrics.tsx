import { LineChart } from "../components/charts/LineChart";
import { KpiCard } from "../components/ui/KpiCard";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/ui/QueryState";
import { useApi } from "../hooks/useApi";
import { getAuthoritativeMetrics } from "../services/authoritativeMetrics.service";
import { formatDecimal, formatNumber } from "../utils/format";

export function MetricsPage() {
  const state = useApi(getAuthoritativeMetrics, { poll: true });

  return (
    <>
      <PageHeader
        eyebrow="MODEL EVALUATION"
        title="Metrics"
        description="Authoritative unseen-incident evaluation results persisted by the real-data RL pipeline."
      />

      <QueryState state={state}>
        {(data) => {
          const e = data.evaluation;
          const history = data.training.history ?? [];

          return (
            <>
              <section className="kpi-grid kpi-grid--four">
                <KpiCard
                  label="Average reward"
                  value={formatDecimal(e.average_reward)}
                  detail="Unseen-incident test set"
                  icon="✦"
                />
                <KpiCard
                  label="Policy optimality"
                  value={pct(e.policy_optimality)}
                  detail="Agent action vs best available action"
                  icon="◎"
                />
                <KpiCard
                  label="Reward efficiency"
                  value={pct(e.reward_efficiency)}
                  detail="Real-data evaluation"
                  icon="◇"
                />
                <KpiCard
                  label="Throughput"
                  value={
                    typeof e.throughput_rows_per_second === "number"
                      ? `${formatDecimal(e.throughput_rows_per_second)} rows/s`
                      : "—"
                  }
                  detail={`${formatNumber(e.samples)} evaluated rows`}
                  icon="◷"
                />
              </section>

              <section className="split-grid">
                <article className="panel">
                  <div className="panel__header">
                    <div>
                      <p className="eyebrow">TRAINING CURVE</p>
                      <h2>Loss history</h2>
                    </div>
                  </div>
                  {history.length ? (
                    <LineChart
                      label="Training loss"
                      points={history.map((row) => ({
                        label: `E${row.epoch}`,
                        value: row.loss,
                      }))}
                      valueFormatter={(value) => value.toFixed(4)}
                    />
                  ) : (
                    <p className="muted">No persisted epoch history.</p>
                  )}
                </article>

                <article className="panel">
                  <div className="panel__header">
                    <div>
                      <p className="eyebrow">TRAINING CURVE</p>
                      <h2>Reward history</h2>
                    </div>
                  </div>
                  {history.some((row) => typeof row.average_reward === "number") ? (
                    <LineChart
                      label="Average reward"
                      points={history
                        .filter((row) => typeof row.average_reward === "number")
                        .map((row) => ({
                          label: `E${row.epoch}`,
                          value: row.average_reward as number,
                        }))}
                      valueFormatter={(value) => value.toFixed(4)}
                    />
                  ) : (
                    <p className="muted">No persisted reward history.</p>
                  )}
                </article>
              </section>

              <section className="split-grid">
                <article className="panel">
                  <div className="panel__header">
                    <div>
                      <p className="eyebrow">FINAL POLICY</p>
                      <h2>Test action distribution</h2>
                    </div>
                  </div>
                  <div className="metric-list">
                    {Object.entries(e.action_distribution ?? {}).map(([name, value]) => (
                      <div key={name} className="metric-list__row">
                        <span>{name}</span>
                        <strong>{formatNumber(value)}</strong>
                      </div>
                    ))}
                  </div>
                </article>

                <article className="panel">
                  <div className="panel__header">
                    <div>
                      <p className="eyebrow">REWARD QUALITY</p>
                      <h2>Aggregate evaluation</h2>
                    </div>
                  </div>
                  <dl className="detail-list">
                    <Detail label="Average reward" value={formatDecimal(e.average_reward)} />
                    <Detail label="Policy optimality" value={pct(e.policy_optimality)} />
                    <Detail label="Reward efficiency" value={pct(e.reward_efficiency)} />
                    <Detail label="Reward regret" value={formatDecimal(e.reward_regret)} />
                    <Detail label="Samples" value={formatNumber(e.samples)} />
                  </dl>
                </article>
              </section>

              <section className="panel">
                <div className="panel__header">
                  <div>
                    <p className="eyebrow">UNSEEN-INCIDENT EVALUATION</p>
                    <h2>Per-class results</h2>
                  </div>
                </div>

                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Class</th>
                        <th>Rows</th>
                        <th>Average reward</th>
                        <th>Optimality</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(e.per_class ?? {}).map(([name, row]) => (
                        <tr key={name}>
                          <td><strong>{name}</strong></td>
                          <td>{formatNumber(row.rows)}</td>
                          <td>{formatDecimal(row.average_reward)}</td>
                          <td>{pct(row.optimality)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="panel">
                <div className="panel__header">
                  <div>
                    <p className="eyebrow">EXPLICITLY UNAVAILABLE</p>
                    <h2>Classification / operational KPIs</h2>
                  </div>
                </div>
                <p className="muted">
                  Accuracy, precision, recall, F1, MTTR, analyst-load comparison,
                  and a baseline comparison are shown only when the evaluator
                  persists those metrics. They are not fabricated from reward
                  values.
                </p>
              </section>
            </>
          );
        }}
      </QueryState>
    </>
  );
}

function pct(value: number | null | undefined) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
