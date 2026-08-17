import { humanize } from "../../utils/format";

type Tone = "critical" | "high" | "medium" | "low" | "success" | "warning" | "neutral" | "info";

const inferTone = (value: string): Tone => {
  const normalized = value.toLowerCase();
  if (normalized.includes("critical") || normalized.includes("p1") || normalized.includes("error")) return "critical";
  if (normalized.includes("high") || normalized.includes("danger")) return "high";
  if (normalized.includes("medium") || normalized.includes("pending") || normalized.includes("running")) return "medium";
  if (normalized.includes("low")) return "low";
  if (normalized.includes("online") || normalized.includes("healthy") || normalized.includes("ok") || normalized.includes("ready") || normalized.includes("completed") || normalized.includes("idle")) return "success";
  if (normalized.includes("offline") || normalized.includes("failed")) return "critical";
  if (normalized.includes("unknown")) return "neutral";
  return "info";
};

export function StatusBadge({ value, tone }: { value: string; tone?: Tone }) {
  const resolvedTone = tone ?? inferTone(value);
  return (
    <span className={`badge badge--${resolvedTone}`} aria-label={`Status: ${humanize(value)}`}>
      <span aria-hidden="true" className="badge__dot" />
      {humanize(value)}
    </span>
  );
}
