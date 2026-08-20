import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { QueryState } from "../components/ui/QueryState";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useApi } from "../hooks/useApi";
import { liveAlertsService } from "../services/liveAlerts.service";
import { formatDateTime } from "../utils/format";

export function AlertDetailsPage() {
  const { id = "" } = useParams();
  const alert = useApi(() => liveAlertsService.getAlert(id), { poll: true });
  const workload = useApi(liveAlertsService.getWorkload, { poll: true });
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedAnalyst, setSelectedAnalyst] = useState("SA");

  async function review(decision: string) {
    setBusy(true);
    try {
      await liveAlertsService.review(id, {
        analyst_id: selectedAnalyst,
        decision,
        comment: `Decision made from the SOC supervision interface: ${decision}`,
      });
      setMessage(`Alert ${id} marked as ${decision}.`);
      await alert.refresh();
      await workload.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to update the alert.");
    } finally {
      setBusy(false);
    }
  }

  async function assign() {
    setBusy(true);
    try {
      await liveAlertsService.assign(id, selectedAnalyst);
      setMessage(`Alert ${id} assigned to ${selectedAnalyst}.`);
      await alert.refresh();
      await workload.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to assign the alert.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="ALERT INVESTIGATION" title={`Alert ${id || "details"}`} description="Original source characteristics stay visible alongside the exact processed representation used by the RL pipeline." actions={<Link className="button button--quiet" to="/alerts">← Back to alerts</Link>} />
      <QueryState state={alert}>
        {(data) => <div className="detail-grid">
          <section className="panel detail-panel">
            <div className="panel__header"><div><p className="eyebrow">REAL SOURCE ALERT</p><h2>{data.title}</h2></div><StatusBadge value={data.status} /></div>
            <dl className="detail-list">
              <Detail label="Alert ID" value={data.alert_id} />
              <Detail label="Incident ID" value={String(data.incident_id)} />
              <Detail label="Timestamp" value={data.timestamp} />
              <Detail label="Category" value={String(data.source.Category ?? "Unknown")} />
              <Detail label="MITRE technique" value={String(data.source.MitreTechniques ?? "Unknown")} />
              <Detail label="Incident grade" value={String(data.source.IncidentGrade ?? "Unknown")} />
              <Detail label="Action grouped" value={String(data.source.ActionGrouped ?? "Unknown")} />
              <Detail label="Action granular" value={String(data.source.ActionGranular ?? "Unknown")} />
              <Detail label="Entity type" value={String(data.source.EntityType ?? "Unknown")} />
              <Detail label="Evidence role" value={String(data.source.EvidenceRole ?? "Unknown")} />
              <Detail label="Threat family" value={String(data.source.ThreatFamily ?? "Unknown")} />
              <Detail label="OS family" value={String(data.source.OSFamily ?? "Unknown")} />
              <Detail label="Suspicion level" value={String(data.source.SuspicionLevel ?? "Unknown")} />
              <Detail label="Last verdict" value={String(data.source.LastVerdict ?? "Unknown")} />
            </dl>
          </section>

          <section className="panel decision-panel">
            <div className="panel__header"><div><p className="eyebrow">RL / HUMAN SUPERVISION</p><h2>Decision state</h2></div></div>
            <dl className="detail-list">
              <Detail label="Agent state" value={data.agent.status} />
              <Detail label="Recommended action" value={data.agent.action} />
              <Detail label="Confidence" value={data.agent.confidence === null ? "Awaiting inference" : String(data.agent.confidence)} />
              <Detail label="Model version" value={data.agent.model_version ?? "Awaiting inference"} />
              <Detail label="Assigned analyst" value={data.assigned_analyst ?? "Unassigned"} />
              <Detail label="Human review" value={data.agent.requires_human_review ? "Required" : "Completed"} />
            </dl>
            <div className="divider" />
            <div className="panel__header"><div><p className="eyebrow">ANALYST CONTROLS</p><h2>Assignment and human verification</h2></div></div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "12px" }}>
              <select value={selectedAnalyst} onChange={(event) => setSelectedAnalyst(event.target.value)} aria-label="Assign analyst">
                {(workload.data?.items ?? []).map((analyst) => <option key={analyst.analyst_id} value={analyst.analyst_id}>{analyst.name} — {analyst.role} ({analyst.available} available)</option>)}
              </select>
              <button className="button button--quiet" type="button" disabled={busy} onClick={() => void assign()}>Assign</button>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
              <button className="button" type="button" disabled={busy} onClick={() => void review("approve")}>Approve</button>
              <button className="button button--quiet" type="button" disabled={busy} onClick={() => void review("reject")}>Reject</button>
              <button className="button button--quiet" type="button" disabled={busy} onClick={() => void review("escalate")}>Escalate</button>
              <button className="button button--quiet" type="button" disabled={busy} onClick={() => void review("delete")}>Delete</button>
              <button className="button button--quiet" type="button" disabled={busy} onClick={() => void review("close")}>Close</button>
            </div>
            {message ? <p className="panel-note">{message}</p> : null}
          </section>

          <section className="panel detail-panel detail-panel--full">
            <div className="panel__header"><div><p className="eyebrow">PROCESSED RL INPUT</p><h2>Exact pipeline representation</h2></div></div>
            <div className="table-scroll"><table className="alerts-table"><thead><tr><th>Feature</th><th>Value passed/stored for the agent</th></tr></thead><tbody>
              {Object.entries(data.processed).filter(([key]) => key !== "alert_id").map(([key, value]) => <tr key={key}><td className="mono">{key}</td><td className="mono">{String(value)}</td></tr>)}
            </tbody></table></div>
            <p className="panel-note">The live holdout keeps the original alert and its processed representation linked by alert ID and lineage data; no model training is triggered here.</p>
          </section>

          <section className="panel detail-panel detail-panel--full">
            <div className="panel__header"><div><p className="eyebrow">ACTIVITY HISTORY</p><h2>Audit trail</h2></div></div>
            {data.history && data.history.length ? <div className="table-scroll"><table className="alerts-table"><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Details</th></tr></thead><tbody>{data.history.map((entry, index) => <tr key={`${String(entry.timestamp)}-${index}`}><td>{formatDateTime(String(entry.timestamp))}</td><td>{String(entry.actor ?? "system")}</td><td>{String(entry.action ?? "")}</td><td>{JSON.stringify(entry.details ?? {})}</td></tr>)}</tbody></table></div> : <EmptyState compact title="No activity yet" description="The first system import event should be recorded when the API seeds MongoDB." />}
          </section>
        </div>}
      </QueryState>
    </>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}
