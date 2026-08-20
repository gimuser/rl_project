import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

export function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = window.localStorage.getItem("rl-agent-theme");
    return saved === "dark" ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.body.dataset.theme = theme;
    window.localStorage.setItem("rl-agent-theme", theme);
  }, [theme]);

  return (
    <div className="app-shell" data-theme={theme}>
      <Sidebar open={menuOpen} onNavigate={() => setMenuOpen(false)} />
      <div className="app-shell__content">
        <Header
          onMenu={() => setMenuOpen(true)}
          theme={theme}
          onToggleTheme={() => setTheme((current) => current === "light" ? "dark" : "light")}
        />
        <main className="main-content"><Outlet /></main>
      </div>
    </div>
  );
}
