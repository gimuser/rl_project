import { useMemo, useState } from "react";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/ui/QueryState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useApi } from "../hooks/useApi";
import { liveAlertsService, type AnalystAction } from "../services/liveAlerts.service";
import { formatDateTime, formatDecimal, formatNumber } from "../utils/format";
import type { LiveAlert } from "../types/domain";

const CURRENT_ANALYST = "SA";

export function AnalystsPage() {
  const workload = useApi(liveAlertsService.getWorkload, { poll: true });
  const pending = useApi(() => liveAlertsService.getPendingForAnalyst(CURRENT_ANALYST, 100), { poll: true });
  const actions = useApi(() => liveAlertsService.getRecentAnalystActions(CURRENT_ANALYST, 100), { poll: true });
  const [busyAlert, setBusyAlert] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  const pendingItems = pending.data?.items ?? [];
  const actionItems = actions.data?.items ?? [];
  const assignedCount = useMemo(
    () => workload.data?.items?.find((item) => item.analyst_id === CURRENT_ANALYST)?.load ?? 0,
    [workload.data],
  );

  const applyAction = async (alert: LiveAlert, decision: "approve" | "block" | "escalate" | "close" | "delete") => {
    try {
      setBusyAlert(alert.alert_id);
      setNotice("");
      await liveAlertsService.review(alert.alert_id, {
        analyst_id: CURRENT_ANALYST,
        decision,
        action: decision,
        comment: `Applied by ${CURRENT_ANALYST} from analyst operations.`,
      });
      setNotice(`${alert.alert_id} → ${decision.toUpperCase()} recorded in MongoDB.`);
      await Promise.all([pending.refresh(), actions.refresh(), workload.refresh()]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyAlert(null);
    }
  };

  const assignToMe = async (alert: LiveAlert) => {
    try {
      setBusyAlert(alert.alert_id);
      setNotice("");
      await liveAlertsService.assign(alert.alert_id, CURRENT_ANALYST);
      setNotice(`${alert.alert_id} assigned to ${CURRENT_ANALYST}.`);
      await Promise.all([pending.refresh(), workload.refresh()]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyAlert(null);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="ANALYST OPERATIONS"
        title="Workload balancing"
        description="Current analyst identity, assignment, capacity, availability, live incoming alerts, and human actions are backed by MongoDB."
      />

      {notice && <div className="panel panel--notice" role="status">{notice}</div>}

      <section className="split-grid">
        <article className="panel">
          <div className="panel__header">
            <div><p className="eyebrow">ANALYST WORKLOAD</p><h2>Current allocation</h2></div>
          </div>
          <QueryState state={workload} empty={(data) => data.items.length === 0}>
            {(data) => (
              <div className="table-scroll">
                <table className="alerts-table">
                  <thead><tr><th>Analyst</th><th>Role</th><th>Load</th><th>Capacity</th><th>Available</th><th>Utilization</th></tr></thead>
                  <tbody>
                    {data.items.map((item) => (
                      <tr key={item.analyst_id}>
                        <td><strong>{item.name}</strong><div className="muted">{item.analyst_id}</div></td>
                        <td>{item.role}</td>
                        <td>{formatNumber(item.load)}</td>
                        <td>{formatNumber(item.capacity)}</td>
                        <td>{formatNumber(item.available)}</td>
                        <td><StatusBadge value={`${formatDecimal(item.utilization * 100, 0)}%`} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </QueryState>
        </article>

        <article className="panel">
          <div className="panel__header">
            <div><p className="eyebrow">LOAD BALANCING</p><h2>Distribution signals</h2></div>
          </div>
          <QueryState state={workload}>
            {(data) => (
              <dl className="detail-list">
                <Detail label="Current analyst" value={`${CURRENT_ANALYST} — SOC Analyst`} />
                <Detail label="Current assigned load" value={formatNumber(assignedCount)} />
                <Detail label="Average analyst load" value={formatDecimal(data.average_analyst_load, 2)} />
                <Detail label="Load variance" value={formatDecimal(data.load_variance, 2)} />
                <Detail label="Most loaded analyst" value={data.most_loaded_analyst ? `${data.most_loaded_analyst.name} (${data.most_loaded_analyst.load})` : "—"} />
                <Detail label="Least loaded analyst" value={data.least_loaded_analyst ? `${data.least_loaded_analyst.name} (${data.least_loaded_analyst.load})` : "—"} />
              </dl>
            )}
          </QueryState>
        </article>
      </section>

      <section className="panel">
        <div className="panel__header">
          <div><p className="eyebrow">ANALYST INBOX</p><h2>Alerts requiring human control</h2></div>
          <span className="pill">{pendingItems.length} pending</span>
        </div>
        <p className="muted">Incoming alerts assigned to {CURRENT_ANALYST} or still waiting for analyst control. Actions below are persisted as human decisions and MongoDB activity history.</p>

        <QueryState state={pending} empty={(data) => data.items.length === 0}>
          {(data) => (
            <div className="table-scroll">
              <table className="alerts-table">
                <thead>
                  <tr><th>Alert</th><th>Source characteristics</th><th>Agent action</th><th>Status</th><th>Analyst controls</th></tr>
                </thead>
                <tbody>
                  {data.items.map((alert) => {
                    const disabled = busyAlert === alert.alert_id;
                    return (
                      <tr key={alert.alert_id}>
                        <td>
                          <strong>{alert.alert_id}</strong>
                          <div>{String(alert.source.Category ?? "Unknown")}</div>
                          <div className="muted">Incident {alert.incident_id}</div>
                        </td>
                        <td>
                          <div><strong>MITRE:</strong> {String(alert.source.MitreTechniques ?? "Unknown")}</div>
                          <div><strong>Verdict:</strong> {String(alert.source.LastVerdict ?? "Unknown")}</div>
                          <div><strong>Entity:</strong> {String(alert.source.EntityType ?? "Unknown")}</div>
                        </td>
                        <td>
                          <StatusBadge value={alert.agent.action} />
                          <div className="muted">{alert.agent.confidence == null ? "Awaiting live inference" : `${(alert.agent.confidence * 100).toFixed(1)}% confidence`}</div>
                        </td>
                        <td><StatusBadge value={alert.status} /></td>
                        <td>
                          <div className="action-stack">
                            <button className="button button--compact" disabled={disabled || Boolean(alert.assigned_analyst)} onClick={() => assignToMe(alert)}>{alert.assigned_analyst ? `Assigned: ${alert.assigned_analyst}` : "Assign to me"}</button>
                            <div className="button-row">
                              <button className="button button--success button--compact" disabled={disabled} onClick={() => applyAction(alert, "approve")}>Allow</button>
                              <button className="button button--danger button--compact" disabled={disabled} onClick={() => applyAction(alert, "block")}>Block</button>
                              <button className="button button--compact" disabled={disabled} onClick={() => applyAction(alert, "escalate")}>Escalate</button>
                              <button className="button button--compact" disabled={disabled} onClick={() => applyAction(alert, "close")}>Close</button>
                              <button className="button button--danger button--compact" disabled={disabled} onClick={() => applyAction(alert, "delete")}>Delete</button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </QueryState>
      </section>

      <section className="panel">
        <div className="panel__header">
          <div><p className="eyebrow">AUDIT HISTORY</p><h2>Recent analyst actions</h2></div>
          <span className="pill">MongoDB activity</span>
        </div>
        <QueryState state={actions} empty={(data) => data.items.length === 0}>
          {(data) => (
            <div className="table-scroll">
              <table>
                <thead><tr><th>Time</th><th>Analyst</th><th>Alert</th><th>Action</th><th>Details</th></tr></thead>
                <tbody>
                  {data.items.map((entry: AnalystAction, index) => (
                    <tr key={`${entry.alert_id}-${entry.timestamp}-${index}`}>
                      <td>{formatDateTime(entry.timestamp)}</td>
                      <td>{entry.actor}</td>
                      <td>{entry.alert_id}</td>
                      <td><StatusBadge value={entry.action} /></td>
                      <td>{String(entry.details?.comment ?? entry.details?.action ?? "Recorded analyst action")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryState>
      </section>
    </>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

export default AnalystsPage;
