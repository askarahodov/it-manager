import { useEffect, useMemo, useState } from "react";

import DashboardPage from "./pages/DashboardPage";
import AutomationPage from "./pages/AutomationPage";
import GroupsPage from "./pages/GroupsPage";
import HostsPage from "./pages/HostsPage";
import HostDetailsPage from "./pages/HostDetailsPage";
import SecretsPage from "./pages/SecretsPage";
import SettingsPage from "./pages/SettingsPage";
import TerminalPage from "./pages/TerminalPage";
import { useAuth } from "./lib/auth";
import TopBar from "./components/TopBar";
import { ConfirmProvider } from "./components/ui/ConfirmProvider";
import { ToastProvider } from "./components/ui/ToastProvider";
import "./styles.css";

const sections = [
  { key: "Dashboard", label: "Обзор" },
  { key: "Hosts", label: "Хосты" },
  { key: "Groups", label: "Группы" },
  { key: "Automation", label: "Автоматизация" },
  { key: "Secrets", label: "Секреты" },
  { key: "Settings", label: "Настройки" },
] as const;

const pageComponents = {
  Dashboard: DashboardPage,
  Hosts: HostsPage,
  Groups: GroupsPage,
  Automation: AutomationPage,
  Secrets: SecretsPage,
  Settings: SettingsPage,
};

function App() {
  const { status } = useAuth();
  const [active, setActive] = useState<keyof typeof pageComponents>(status === "anonymous" ? "Settings" : "Dashboard");
  const [terminalRoute, setTerminalRoute] = useState(false);
  const [hostDetailsId, setHostDetailsId] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const syncFromHash = () => {
      const hash = window.location.hash || "";
      setTerminalRoute(/^#\/terminal\/\d+\b/.test(hash));
      const m = hash.match(/^#\/hosts\/(\d+)\b/);
      if (!m) {
        setHostDetailsId(null);
        return;
      }
      const id = Number(m[1]);
      setHostDetailsId(Number.isFinite(id) && id > 0 ? id : null);
    };
    syncFromHash();
    window.addEventListener("hashchange", syncFromHash);
    return () => window.removeEventListener("hashchange", syncFromHash);
  }, []);

  const sidebar = useMemo(
    () =>
      sections.map((item) => (
        <button
          key={item.key}
          className={`menu-button ${active === item.key ? "active" : ""}`}
          onClick={() => {
            window.location.hash = "";
            setActive(item.key);
            setSidebarOpen(false);
          }}
          aria-label={item.label}
        >
          {item.label}
        </button>
      )),
    [active]
  );

  const ActivePage = pageComponents[active];

  if (terminalRoute) {
    return (
      <ToastProvider>
        <ConfirmProvider>
          <div className="page-content" style={{ padding: 0, minHeight: "100vh" }}>
            <TerminalPage />
          </div>
        </ConfirmProvider>
      </ToastProvider>
    );
  }

  if (hostDetailsId) {
    return (
      <ToastProvider>
        <ConfirmProvider>
          <div className={`app-shell ${sidebarOpen ? "sidebar-open" : ""}`}>
            <aside className="sidebar">
              <div className="brand">IT Manager</div>
              <div className="menu">{sidebar}</div>
            </aside>
            <div
              className={`sidebar-backdrop ${sidebarOpen ? "open" : ""}`}
              onClick={() => setSidebarOpen(false)}
              aria-hidden="true"
            />
            <main className="content">
              <TopBar sidebarOpen={sidebarOpen} onToggleSidebar={() => setSidebarOpen((v) => !v)} />
              <section className="section-shell">
                <HostDetailsPage hostId={hostDetailsId} />
              </section>
            </main>
          </div>
        </ConfirmProvider>
      </ToastProvider>
    );
  }

  return (
    <ToastProvider>
      <ConfirmProvider>
        <div className={`app-shell ${sidebarOpen ? "sidebar-open" : ""}`}>
          <aside className="sidebar">
            <div className="brand">IT Manager</div>
            <div className="menu">{sidebar}</div>
          </aside>
          <div
            className={`sidebar-backdrop ${sidebarOpen ? "open" : ""}`}
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
          <main className="content">
            <TopBar sidebarOpen={sidebarOpen} onToggleSidebar={() => setSidebarOpen((v) => !v)} />
            <section className="section-shell">
              <ActivePage />
            </section>
          </main>
        </div>
      </ConfirmProvider>
    </ToastProvider>
  );
}

export default App;
