import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/ui/QueryState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useApi } from "../hooks/useApi";
import { liveAlertsService, type AnalystAction } from "../services/liveAlerts.service";
import { formatDateTime, formatDecimal, formatNumber } from "../utils/format";
import type { LiveAlert } from "../types/domain";

const CURRENT_ANALYST = "SA";
const PAGE_SIZE = 5;

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

const IMPORTANT_SOURCE_FIELDS = new Set([
  "IncidentGrade",
  "SuspicionLevel",
  "MitreTechniques",
  "ThreatFamily",
  "Category",
  "EntityType",
]);

function sourceValue(alert: LiveAlert, key: string) {
  const raw = alert.source?.[key];
  if (raw !== null && raw !== undefined && raw !== "") return String(raw);
  if (key === "AlertId" && alert.alert_id) return String(alert.alert_id);
  if (key === "IncidentId" && alert.incident_id !== null && alert.incident_id !== undefined) return String(alert.incident_id);
  if (key === "Timestamp" && alert.timestamp) return String(alert.timestamp);
  return "—";
}

function priorityFor(alert: LiveAlert) {
  const grade = sourceValue(alert, "IncidentGrade").toLowerCase();
  const suspicion = sourceValue(alert, "SuspicionLevel").toLowerCase();
  if (grade.includes("truepositive") || suspicion.includes("critical") || suspicion.includes("high")) {
    return { level: "HIGH", label: "High-priority review", color: "#b42318", border: "#ef4444", background: "#fff5f5", soft: "#fee4e2" };
  }
  if (grade.includes("falsepositive") || suspicion.includes("medium") || suspicion.includes("suspicious")) {
    return { level: "MEDIUM", label: "Needs careful review", color: "#a15c00", border: "#f59e0b", background: "#fffaf0", soft: "#fef3c7" };
  }
  if (grade.includes("benignpositive") || suspicion.includes("low")) {
    return { level: "LOW", label: "Lower-risk review", color: "#177245", border: "#22c55e", background: "#f4fbf6", soft: "#dcfce7" };
  }
  return { level: "REVIEW", label: "Review context", color: "#245a9a", border: "#60a5fa", background: "#f6faff", soft: "#dbeafe" };
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

export function AnalystsPage() {
  const workload = useApi(liveAlertsService.getWorkload, { poll: true });
  const pending = useApi(() => liveAlertsService.getPendingForAnalyst(CURRENT_ANALYST, 100), { poll: true });
  const actions = useApi(() => liveAlertsService.getRecentAnalystActions(CURRENT_ANALYST, 100), { poll: true });
  const [busyAlert, setBusyAlert] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [page, setPage] = useState(1);

  const pendingItems = pending.data?.items ?? [];
  const actionItems = actions.data?.items ?? [];
  const totalPages = Math.max(1, Math.ceil(pendingItems.length / PAGE_SIZE));
  const pageItems = pendingItems.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const pageStart = pendingItems.length ? (page - 1) * PAGE_SIZE + 1 : 0;
  const pageEnd = Math.min(page * PAGE_SIZE, pendingItems.length);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  useEffect(() => {
    setPage(1);
  }, [pendingItems.length]);

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

  const go = (target: number) => setPage(Math.min(totalPages, Math.max(1, target)));

  return (
    <>
      <PageHeader
        eyebrow="ANALYST OPERATIONS"
        title="Workload balancing"
        description="Review the live analyst queue, inspect the original source record, and apply human control without losing the model decision context."
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
                    {data.items.map((item) => {
                      const overloaded = item.load > item.capacity;
                      return (
                        <tr key={item.analyst_id}>
                          <td><strong>{item.name}</strong><div className="muted">{item.analyst_id}</div></td>
                          <td>{item.role}</td>
                          <td>{formatNumber(item.load)}</td>
                          <td>{formatNumber(item.capacity)}</td>
                          <td>{formatNumber(item.available)}</td>
                          <td><StatusBadge value={`${formatDecimal(item.utilization * 100, 0)}%`} /></td>
                          {overloaded && <td><span className="badge badge--danger">OVER CAPACITY</span></td>}
                        </tr>
                      );
                    })}
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
                <Detail label="Queue size" value={formatNumber(pendingItems.length)} />
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
          <div><p className="eyebrow">ANALYST INBOX</p><h2>Alerts requiring human control</h2><p className="muted" style={{ marginTop: 6 }}>Showing {pageStart}–{pageEnd} of {pendingItems.length} pending alerts · 5 alerts per page.</p></div>
          <span className="pill">{pendingItems.length} pending</span>
        </div>
        <p className="muted">Every alert shows the complete original source record used for live inference. Review the source attributes first, then apply the human decision.</p>

        <QueryState state={pending} empty={(data) => data.items.length === 0}>
          {() => (
            <>
              <div style={{ display: "grid", gap: 16 }}>
                {pageItems.map((alert) => {
                  const disabled = busyAlert === alert.alert_id;
                  const priority = priorityFor(alert);
                  return (
                    <article key={alert.alert_id} className="panel" style={{ margin: 0, background: priority.background, border: `2px solid ${priority.border}`, boxShadow: `0 0 0 3px ${priority.soft}` }}>
                      <div className="panel__header">
                        <div>
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 6 }}>
                            <p className="eyebrow" style={{ margin: 0 }}>LIVE ALERT · SOURCE RECORD</p>
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 9px", borderRadius: 999, background: priority.soft, color: priority.color, fontSize: 11, fontWeight: 900, letterSpacing: ".07em" }}>{priority.level} · {priority.label}</span>
                          </div>
                          <h2>{sourceValue(alert, "AlertId")} · Incident {sourceValue(alert, "IncidentId")}</h2>
                          <p className="muted">Received {formatDateTime(alert.timestamp)} · Status {alert.status}</p>
                        </div>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                          <StatusBadge value={alert.agent.action} />
                          <StatusBadge value={alert.status} />
                        </div>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 10 }}>
                        {SOURCE_FIELDS.map(([key, label]) => {
                          const important = IMPORTANT_SOURCE_FIELDS.has(key);
                          return (
                            <div key={key} style={{ position: "relative", padding: important ? "12px 13px" : "10px 12px", border: `1px solid ${important ? priority.border : "#dfe6ef"}`, borderRadius: 10, background: important ? "rgba(255,255,255,.82)" : "#fff", boxShadow: important ? `inset 3px 0 0 ${priority.border}` : "none" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", fontSize: 10, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", color: important ? priority.color : "#8191a4", marginBottom: 5 }}><span>{label}</span>{important && <span style={{ fontSize: 9, fontWeight: 900 }}>KEY</span>}</div>
                              <div style={{ color: important ? "#17233b" : "#344054", fontWeight: important ? 800 : 700, fontSize: important ? 14 : 13, wordBreak: "break-word" }}>{sourceValue(alert, key)}</div>
                            </div>
                          );
                        })}
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 10, marginTop: 12 }}>
                        <div style={{ padding: "10px 12px", border: "1px solid #dfe6ef", borderRadius: 10, background: "#f8faff" }}><div className="eyebrow" style={{ marginBottom: 5 }}>Agent confidence</div><div style={{ color: "#17233b", fontWeight: 700 }}>{alert.agent.confidence == null ? "Awaiting live inference" : `${(alert.agent.confidence * 100).toFixed(1)}%`}</div></div>
                        <div style={{ padding: "10px 12px", border: "1px solid #dfe6ef", borderRadius: 10, background: "#f8faff" }}><div className="eyebrow" style={{ marginBottom: 5 }}>Assigned analyst</div><div style={{ color: "#17233b", fontWeight: 700 }}>{alert.assigned_analyst ?? "Not assigned"}</div></div>
                        <div style={{ padding: "10px 12px", border: "1px solid #dfe6ef", borderRadius: 10, background: "#f8faff" }}><div className="eyebrow" style={{ marginBottom: 5 }}>Model version</div><div style={{ color: "#17233b", fontWeight: 700 }}>{alert.agent.model_version ?? "—"}</div></div>
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

              {pendingItems.length > PAGE_SIZE && (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border, #e3e9f1)" }}>
                  <span className="muted">Page {page} of {totalPages}</span>
                  <nav aria-label="Alert pagination" style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                    <button className="button button--compact" disabled={page === 1} onClick={() => go(1)}>First</button>
                    <button className="button button--compact" disabled={page === 1} onClick={() => go(page - 1)}>Previous</button>
                    {Array.from({ length: totalPages }, (_, index) => index + 1).map((number) => (
                      <button key={number} className={`button button--compact ${number === page ? "button--primary" : ""}`} onClick={() => go(number)} aria-current={number === page ? "page" : undefined}>{number}</button>
                    ))}
                    <button className="button button--compact" disabled={page === totalPages} onClick={() => go(page + 1)}>Next</button>
                    <button className="button button--compact" disabled={page === totalPages} onClick={() => go(totalPages)}>Last</button>
                  </nav>
                </div>
              )}
            </>
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
                      <td>{formatDateTime(entry.timestamp)}</td><td>{entry.actor}</td><td>{entry.alert_id}</td><td><StatusBadge value={entry.action} /></td><td>{String(entry.details?.comment ?? entry.details?.action ?? "Recorded analyst action")}</td>
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

export default AnalystsPage;
