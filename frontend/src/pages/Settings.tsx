import { PageHeader } from "../components/ui/PageHeader";
import { dashboardService } from "../services/dashboard.service";

const apiUrl = import.meta.env.VITE_API_BASE_URL || "Same-origin /api proxy";
const polling = import.meta.env.VITE_POLL_INTERVAL_MS || "30000";
const mockMode = import.meta.env.VITE_USE_MOCKS === "true";

export function SettingsPage() {
  return <>
    <PageHeader eyebrow="CONFIGURATION" title="Frontend settings" description="Runtime settings are configured through environment variables at build or deployment time." />
    <section className="split-grid"><article className="panel"><div className="panel__header"><div><p className="eyebrow">CONNECTION</p><h2>API configuration</h2></div></div><dl className="detail-list"><Detail label="API base URL" value={apiUrl} /><Detail label="Polling interval" value={`${polling} ms`} /><Detail label="Mock mode" value={mockMode ? "Enabled (development only)" : "Disabled"} /></dl></article><article className="panel"><div className="panel__header"><div><p className="eyebrow">AUTHENTICATION</p><h2>Access control</h2></div></div><p className="muted">The backend does not currently expose an authentication contract. The UI therefore does not create, store, or simulate tokens.</p></article></section>
    <section className="panel"><div className="panel__header"><div><p className="eyebrow">API SURFACE</p><h2>Current integration</h2></div></div><ul className="contract-list"><li><code>/api/dashboard/summary</code><span>Dashboard KPI values</span></li><li><code>/api/alerts</code><span>Alert queue and detail</span></li><li><code>/api/decisions</code><span>Decision records</span></li><li><code>/api/rewards</code><span>Reward records and statistics</span></li><li><code>/api/training/*</code><span>Status, loss history, checkpoints, commands</span></li></ul></section>
  </>;
}
function Detail({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
