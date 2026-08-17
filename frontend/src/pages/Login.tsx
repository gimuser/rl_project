import { Link } from "react-router-dom";

export function LoginPage() {
  return <main className="login-page"><section className="login-card"><div className="brand"><div className="brand__mark">S</div><div><strong>SOAR-RL</strong><span>SOC COMMAND</span></div></div><p className="eyebrow">ACCESS STATUS</p><h1>Authentication is not configured</h1><p>The FastAPI backend does not currently expose a login or token endpoint. This route is reserved so authentication can be integrated without changing the application navigation.</p><Link className="button button--primary" to="/dashboard">Continue to dashboard →</Link></section></main>;
}
