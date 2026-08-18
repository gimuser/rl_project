import { useMemo, useState } from "react";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/ui/QueryState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useApi } from "../hooks/useApi";
import { liveAlertsService, type AnalystAction } from "../services/liveAlerts.service";
import { formatDateTime, formatDecimal, formatNumber } from "../utils/format";
import type { LiveAlert } from "../types/domain";

const CURRENT_ANALYST = "SA";

const SOURCE_FIELDS = [
  ["IncidentId", "Incident ID"],
  ["AlertId", "Alert ID"],
  ["Timestamp", "Timestamp"],
  ["Category", "Category"],
  ["MitreTechniques", "MITRE Techniques"],
  ["IncidentGrade", "Incident Grade"],
  ["ActionGrouped", "Action Grouped"],
  ["ActionGranular", "Action Granular"],
  ["EntityType", "Entity Type"],
  ["EvidenceRole", "Evidence Role"],
  ["ThreatFamily", "Threat Family"],
  ["OSFamily", "OS Family"],
  ["SuspicionLevel", "Suspicion Level"],
] as const;

function sourceValue(alert: LiveAlert, key: string) {
  const value = alert.source?.[key];
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

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
        <p className="muted">Every alert shows the complete source record used for live inference. Review the original alert attributes first, then assign or apply the human decision.</p>

        <QueryState state={pending} empty={(data) => data.items.length === 0}>
          {(data) => (
            <div style={{ display: "grid", gap: 16 }}>
              {data.items.map((alert) => {
                const disabled = busyAlert === alert.alert_id;
                return (
                  <article key={alert.alert_id} className="panel" style={{ margin: 0, background: "#fbfdff" }}>
                    <div className="panel__header">
                      <div>
                        <p className="eyebrow">LIVE ALERT · SOURCE RECORD</p>
                        <h2>{alert.alert_id} · Incident {alert.incident_id}</h2>
                        <p className="muted">Received {formatDateTime(alert.timestamp)} · Status {alert.status}</p>
                      </div>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                        <StatusBadge value={alert.agent.action} />
                        <StatusBadge value={alert.status} />
                      </div>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 10 }}>
                      {SOURCE_FIELDS.map(([key, label]) => (
                        <div key={key} style={{ padding: "10px 12px", border: "1px solid #dfe6ef", borderRadius: 10, background: "#fff" }}>
                          <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", color: "#8191a4", marginBottom: 5 }}>{label}</div>
                          <div style={{ color: "#17233b", fontWeight: 700, fontSize: 13, wordBreak: "break-word" }}>{sourceValue(alert, key)}</div>
                        </div>
                      ))}
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 10, marginTop: 12 }}>
                      <div style={{ padding: "10px 12px", border: "1px solid #dfe6ef", borderRadius: 10, background: "#f8faff" }}>
                        <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", color: "#8191a4", marginBottom: 5 }}>Agent confidence</div>
                        <div style={{ color: "#17233b", fontWeight: 700 }}>{alert.agent.confidence == null ? "Awaiting live inference" : `${(alert.agent.confidence * 100).toFixed(1)}%`}</div>
                      </div>
                      <div style={{ padding: "10px 12px", border: "1px solid #dfe6ef", borderRadius: 10, background: "#f8faff" }}>
                        <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", color: "#8191a4", marginBottom: 5 }}>Assigned analyst</div>
                        <div style={{ color: "#17233b", fontWeight: 700 }}>{alert.assigned_analyst ?? "Not assigned"}</div>
                      </div>
                      <div style={{ padding: "10px 12px", border: "1px solid #dfe6ef", borderRadius: 10, background: "#f8faff" }}>
                        <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", color: "#8191a4", marginBottom: 5 }}>Model version</div>
                        <div style={{ color: "#17233b", fontWeight: 700 }}>{alert.agent.model_version ?? "—"}</div>
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14, paddingTop: 14, borderTop: "1px solid #e3e9f1" }}>
                      <button className="button button--compact" disabled={disabled || Boolean(alert.assigned_analyst)} onClick={() => assignToMe(alert)}>{alert.assigned_analyst ? `Assigned: ${alert.assigned_analyst}` : "Assign to me"}</button>
                      <button className="button button--success button--compact" disabled={disabled} onClick={() => applyAction(alert, "approve")}>Allow</button>
                      <button className="button button--danger button--compact" disabled={disabled} onClick={() => applyAction(alert, "block")}>Block</button>
                      <button className="button button--compact" disabled={disabled} onClick={() => applyAction(alert, "escalate")}>Escalate</button>
                      <button className="button button--compact" disabled={disabled} onClick={() => applyAction(alert, "close")}>Close</button>
                      <button className="button button--danger button--compact" disabled={disabled} onClick={() => applyAction(alert, "delete")}>Delete</button>
                    </div>
                  </article>
                );
              })}
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
