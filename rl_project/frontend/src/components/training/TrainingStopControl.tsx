import { useEffect, useState } from "react";
import { stopAuthoritativeFullTraining } from "../../services/training.service";

export function TrainingStopControl() {
  const [running, setRunning] = useState(false);
  const [stopping, setStopping] = useState(false);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const response = await fetch("/api/training-control", { headers: { Accept: "application/json" } });
        if (!response.ok) return;
        const data = await response.json() as { status?: string };
        if (active) setRunning(data.status === "running" || data.status === "starting");
      } catch {
        if (active) setRunning(false);
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const stop = async () => {
    if (!running || stopping) return;
    setStopping(true);
    try {
      await stopAuthoritativeFullTraining();
      setRunning(false);
    } finally {
      setStopping(false);
    }
  };

  return (
    <button
      className="live-btn live-btn--danger"
      disabled={!running || stopping}
      onClick={() => void stop()}
      title={running ? "Stop the active training run" : "No training run is active"}
    >
      {stopping ? "Stopping…" : running ? "Stop training" : "Stop training"}
    </button>
  );
}
