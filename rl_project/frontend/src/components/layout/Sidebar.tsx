import { NavLink } from "react-router-dom";

const items = [
  ["/dashboard", "Dashboard", "▦"],
  ["/alerts", "Alerts", "◇"],
  ["/agent", "Agent RL", "◉"],
  ["/decisions", "Decisions", "↗"],
  ["/training", "Training", "⌁"],
  ["/analysts", "Analysts", "♙"],
  ["/metrics", "Metrics", "⌁"],
  ["/history", "History", "◴"],
  ["/settings", "Settings", "⚙"],
] as const;

export function Sidebar({ open, onNavigate }: { open: boolean; onNavigate: () => void }) {
  return (
    <>
      <button
        className={`sidebar-backdrop${open ? " sidebar-backdrop--visible" : ""}`}
        aria-label="Close navigation"
        type="button"
        onClick={onNavigate}
      />
      <aside className={`sidebar${open ? " sidebar--open" : ""}`} aria-label="Primary navigation">
        <div className="brand">
          <div className="brand__mark" aria-hidden="true">S</div>
          <div>
            <strong>SOAR-RL</strong>
            <span>SOC COMMAND</span>
          </div>
        </div>
        <div className="sidebar__workspace">
          <span>WORKSPACE</span>
          <strong>Production SOC</strong>
        </div>
        <nav>
          <p className="nav-label">OPERATIONS</p>
          {items.map(([to, label, icon]) => (
            <NavLink
              end={to === "/dashboard"}
              className={({ isActive }) => `sidebar__link${isActive ? " sidebar__link--active" : ""}`}
              key={to}
              onClick={onNavigate}
              to={to}
            >
              <span className="sidebar__icon" aria-hidden="true">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__footer">
          <span className="status-light status-light--online" aria-hidden="true" />
          <span>Secure workspace</span>
        </div>
      </aside>
    </>
  );
}
