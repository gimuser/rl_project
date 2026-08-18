import { createPortal } from "react-dom";
import { useEffect, useState } from "react";
import { getAuthoritativeFullTrainingStatus, type AuthoritativeTrainingStatus } from "../services/training.service";
import { TrainingLauncher } from "./TrainingLauncher";
import "./TrainingLauncherLiveAccess.css";

function LiveAccessCard() {
  const [status, setStatus] = useState<AuthoritativeTrainingStatus | null>(null);
  const [slot, setSlot] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const host = document.querySelector(".lux-training");
    const hero = host?.querySelector(".lux-hero");
    if (!host || !hero) return;

    let target = host.querySelector<HTMLElement>("[data-training-live-access]");
    if (!target) {
      target = document.createElement("div");
      target.dataset.trainingLiveAccess = "true";
      hero.insertAdjacentElement("afterend", target);
    }
    setSlot(target);

    return () => target?.remove();
  }, []);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const next = await getAuthoritativeFullTrainingStatus();
        if (active) setStatus(next);
      } catch {
        if (active) setStatus(null);
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  if (!slot) return null;

  const running = status?.status === "running" || status?.status === "starting";
  if (!running) return null;

  const training = (status?.results?.training ?? {}) as Record<string, any>;
  const selectedModels = Array.isArray(training.selected_models) ? training.selected_models : [];
  const algorithm = training.display_name ?? training.algorithm ?? (selectedModels.length === 1 ? selectedModels[0] : "Training");
  const epoch = training.actual_epochs ?? training.final_epoch;
  const maxEpochs = training.epochs ?? training.max_epochs;
  const bestEpoch = training.best_epoch;
  const updates = training.total_updates_used ?? training.total_updates;

  return createPortal(
    <section className="training-live-access training-live-access--running" aria-live="polite">
      <div className="training-live-access__pulse" />
      <div className="training-live-access__main">
        <div className="training-live-access__eyebrow">LIVE MONITOR</div>
        <strong>{algorithm}</strong>
        <span>Training is currently running.</span>
      </div>
      <div className="training-live-access__stats">
        <div><span>Status</span><strong>RUNNING</strong></div>
        <div><span>Epoch</span><strong>{epoch !== undefined && epoch !== null ? `${epoch}${maxEpochs ? ` / ${Number(maxEpochs).toLocaleString()}` : ""}` : "—"}</strong></div>
        <div><span>Best</span><strong>{bestEpoch !== undefined && bestEpoch !== null ? bestEpoch : "—"}</strong></div>
        <div><span>Updates</span><strong>{typeof updates === "number" ? updates.toLocaleString() : "—"}</strong></div>
      </div>
      <a className="training-live-access__link" href="/training/live">Open live monitor →</a>
    </section>,
    slot,
  );
}

export function TrainingLauncherLiveAccess() {
  return (
    <>
      <TrainingLauncher />
      <LiveAccessCard />
    </>
  );
}
