import { useLocation } from "react-router-dom";
import { TrainingStopControl } from "./TrainingStopControl";

export function TrainingStopOverlay() {
  const location = useLocation();
  if (location.pathname !== "/training/live") return null;

  return (
    <div style={{ position: "fixed", top: 18, right: 18, zIndex: 1000 }}>
      <TrainingStopControl />
    </div>
  );
}
