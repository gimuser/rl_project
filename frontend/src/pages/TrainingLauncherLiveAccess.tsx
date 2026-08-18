import { createPortal } from "react-dom";
import { useEffect, useState } from "react";
import { getAuthoritativeFullTrainingStatus, type AuthoritativeTrainingStatus } from "../services/training.service";
import { TrainingLauncher } from "./TrainingLauncher";
import "./TrainingLauncherLiveAccess.css";

type Props = {
  children?: React.ReactNode;
};

function LiveAccessCard() {
  const [status, setStatus] = useState<AuthoritativeTrainingStatus | null>(null);

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

  const running = status?.status === "running" || status?.status === "starting";
  if (!running) return null;

  const training = status?.results?.training;
  const selectedModels = status?.results?.training?.selected_models ?? status?.selected_models ?? [];
  const algorithm = training?.display_name ?? training?.algorithm ?? (selectedModels.length === 1 ? selectedModels[0] : "Selected models");
  const epoch = training?.actual_epochs ?? training?.final_epoch;
  const maxEpochs = training?.epochs ?? training?.max_epochs;
  const bestEpoch = training?.best_epoch;
  const updates = training?.total_updates_used ?? training?.total_updates;

  const host = document.querySelector(".lux-training");
  const hero = host?.querySelector(".lux-hero");
  if (!host || !hero) return null;

  let slot = host.querySelector<HTMLElement>("[data-training-live-access]");
  if (!slot) {
    slot = document.createElement("div");
    slot.dataset.trainingLiveAccess = "true";
    hero.insertAdjacentElement("afterend", slot);
  }

  return createPortal(
    <section className="training-live-access" aria-live="polite">
      <div className="training-live-access__pulse" />
      <div className="training-live-access__main">
        <div className="training-live-access__eyebrow">LIVE TRAINING</div>
        <strong>{algorithm}</strong>
        <span>Training is currently running.</span>
      </div>
      <div className="training-live-access__stats">
        <div><span>Epoch</span><strong>{epoch ?? "—"}{maxEpochs ? ` / ${maxEpochs.toLocaleString()}` : ""}</strong></div>
        <div><span>Best</span><strong>{bestEpoch ?? "—"}</strong></div>
        <div><span>Updates</span><strong>{typeof updates === "number" ? updates.toLocaleString() : "—"}</strong></div>
      </div>
      <a className="training-live-access__link" href="/training/live">Open live monitor →</a>
    </section>,
    slot,
  );
}

export function TrainingLauncherLiveAccess(_: Props) {
  return (
    <>
      <TrainingLauncher />
      <LiveAccessCard />
    </>
  );
}
