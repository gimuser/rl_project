import { useEffect, useState } from "react";

export function ChartHoverTooltip() {
  const [tip, setTip] = useState<{ x: number; y: number; title: string; detail: string } | null>(null);

  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      const target = event.target as Element | null;
      const circle = target?.closest?.(".legacy-line-chart circle") as SVGCircleElement | null;
      if (!circle) {
        setTip(null);
        return;
      }

      const chart = circle.closest(".legacy-chart-panel");
      const title = chart?.querySelector("h2")?.textContent?.trim() || "Training metric";
      const detail = circle.querySelector("title")?.textContent?.trim() || "";
      const rect = circle.getBoundingClientRect();

      setTip({
        x: Math.min(window.innerWidth - 240, Math.max(12, rect.left + rect.width / 2 + 12)),
        y: Math.max(12, rect.top - 12),
        title,
        detail,
      });
    };

    const onLeave = () => setTip(null);

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseleave", onLeave);
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseleave", onLeave);
    };
  }, []);

  if (!tip) return null;

  return (
    <div
      className="training-chart-hover-tooltip"
      style={{ left: tip.x, top: tip.y }}
      role="status"
      aria-live="polite"
    >
      <div className="training-chart-hover-tooltip__title">{tip.title}</div>
      <div className="training-chart-hover-tooltip__detail">{tip.detail}</div>
    </div>
  );
}
