import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { ToastProvider } from "./components/ui/ToastProvider";
import { TrainingStopOverlay } from "./components/training/TrainingStopOverlay";
import { AgentPage } from "./pages/Agent";
import { AlertDetailsPage } from "./pages/AlertDetails";
import { AlertsPage } from "./pages/Alerts";
import { AnalystsPage } from "./pages/Analysts";
import { DashboardPage } from "./pages/Dashboard";
import { DecisionsPage } from "./pages/Decisions";
import { HistoryPage } from "./pages/History";
import { LoginPage } from "./pages/Login";
import { MetricsPage } from "./pages/Metrics";
import { SettingsPage } from "./pages/Settings";
import { TrainingLauncherLiveAccess } from "./pages/TrainingLauncherLiveAccess";
import { TrainingLive } from "./pages/TrainingLive";

export default function App() {
  return <ToastProvider><TrainingStopOverlay /><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<AppLayout />}>
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/alerts" element={<AlertsPage />} />
      <Route path="/alerts/:id" element={<AlertDetailsPage />} />
      <Route path="/agent" element={<AgentPage />} />
      <Route path="/decisions" element={<DecisionsPage />} />
      <Route path="/training" element={<TrainingLauncherLiveAccess />} />
      <Route path="/training/live" element={<TrainingLive />} />
      <Route path="/analysts" element={<AnalystsPage />} />
      <Route path="/metrics" element={<MetricsPage />} />
      <Route path="/history" element={<HistoryPage />} />
      <Route path="/settings" element={<SettingsPage />} />
    </Route>
    <Route path="*" element={<Navigate to="/dashboard" replace />} />
  </Routes></ToastProvider>;
}
