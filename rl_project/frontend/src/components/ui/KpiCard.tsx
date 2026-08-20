import type { ReactNode } from "react";

export function KpiCard({
  label,
  value,
  detail,
  icon,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  detail: string;
  icon: string;
  tone?: "default" | "critical" | "success" | "warning";
}) {
  return (
    <article className={`kpi-card kpi-card--${tone}`}>
      <div className="kpi-card__top">
        <span>{label}</span>
        <span className="kpi-card__icon" aria-hidden="true">{icon}</span>
      </div>
      <strong className="kpi-card__value">{value}</strong>
      <p>{detail}</p>
    </article>
  );
}
