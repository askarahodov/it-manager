import { useEffect, useMemo, useRef, useState } from "react";

import DashboardPage from "./pages/DashboardPage";
import AutomationPage from "./pages/AutomationPage";
import GroupsPage from "./pages/GroupsPage";
import HostsPage from "./pages/HostsPage";
import HostDetailsPage from "./pages/HostDetailsPage";
import SecretsPage from "./pages/SecretsPage";
import SettingsPage from "./pages/SettingsPage";
import TerminalPage from "./pages/TerminalPage";
import { apiFetch } from "./lib/api";
import { useAuth } from "./lib/auth";
import TopBar from "./components/TopBar";
import { ConfirmProvider } from "./components/ui/ConfirmProvider";
import { ToastProvider } from "./components/ui/ToastProvider";
import { formatError } from "./lib/errors";
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

type HostItem = { id: number; name: string; hostname: string; environment: string; os_type: string };
type GroupItem = { id: number; name: string; type: "static" | "dynamic" };
type SecretItem = { id: number; name: string; type: string; scope: string };
type PlaybookItem = { id: number; name: string };

type PaletteItem = {
  id: string;
  label: string;
  description?: string;
  type: "nav" | "host" | "group" | "secret" | "playbook";
  action: () => void;
};

function App() {
  const { status, token } = useAuth();
  const [active, setActive] = useState<keyof typeof pageComponents>(status === "anonymous" ? "Settings" : "Dashboard");
  const [terminalRoute, setTerminalRoute] = useState(false);
  const [hostDetailsId, setHostDetailsId] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [paletteLoading, setPaletteLoading] = useState(false);
  const [paletteError, setPaletteError] = useState<string | null>(null);
  const [paletteHosts, setPaletteHosts] = useState<HostItem[]>([]);
  const [paletteGroups, setPaletteGroups] = useState<GroupItem[]>([]);
  const [paletteSecrets, setPaletteSecrets] = useState<SecretItem[]>([]);
  const [palettePlaybooks, setPalettePlaybooks] = useState<PlaybookItem[]>([]);
  const paletteInputRef = useRef<HTMLInputElement | null>(null);

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

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
      if (event.key === "Escape" && paletteOpen) {
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [paletteOpen]);

  useEffect(() => {
    if (!paletteOpen) return;
    setTimeout(() => paletteInputRef.current?.focus(), 0);
  }, [paletteOpen]);

  useEffect(() => {
    if (!paletteOpen || !token) return;
    setPaletteLoading(true);
    setPaletteError(null);
    Promise.all([
      apiFetch<HostItem[]>("/api/v1/hosts/", { token }),
      apiFetch<GroupItem[]>("/api/v1/groups/", { token }),
      apiFetch<SecretItem[]>("/api/v1/secrets/", { token }),
      apiFetch<PlaybookItem[]>("/api/v1/playbooks/", { token }),
    ])
      .then(([hosts, groups, secrets, playbooks]) => {
        setPaletteHosts(hosts);
        setPaletteGroups(groups);
        setPaletteSecrets(secrets);
        setPalettePlaybooks(playbooks);
      })
      .catch((err) => {
        setPaletteError(formatError(err));
      })
      .finally(() => setPaletteLoading(false));
  }, [paletteOpen, token]);

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

  const staticActions: PaletteItem[] = [
    {
      id: "nav-dashboard",
      label: "Открыть: Обзор",
      type: "nav",
      action: () => {
        window.location.hash = "";
        setActive("Dashboard");
      },
    },
    {
      id: "nav-hosts",
      label: "Открыть: Хосты",
      type: "nav",
      action: () => {
        window.location.hash = "";
        setActive("Hosts");
      },
    },
    {
      id: "nav-groups",
      label: "Открыть: Группы",
      type: "nav",
      action: () => {
        window.location.hash = "";
        setActive("Groups");
      },
    },
    {
      id: "nav-automation",
      label: "Открыть: Автоматизация",
      type: "nav",
      action: () => {
        window.location.hash = "";
        setActive("Automation");
      },
    },
    {
      id: "nav-secrets",
      label: "Открыть: Секреты",
      type: "nav",
      action: () => {
        window.location.hash = "";
        setActive("Secrets");
      },
    },
    {
      id: "nav-settings",
      label: "Открыть: Настройки",
      type: "nav",
      action: () => {
        window.location.hash = "";
        setActive("Settings");
      },
    },
  ];

  const paletteItems = useMemo(() => {
    const query = paletteQuery.trim().toLowerCase();
    const matches = (value: string) => value.toLowerCase().includes(query);
    const items: PaletteItem[] = [];
    staticActions.forEach((action) => {
      if (!query || matches(action.label)) items.push(action);
    });
    paletteHosts.forEach((host) => {
      if (!query || matches(host.name) || matches(host.hostname)) {
        items.push({
          id: `host-${host.id}`,
          label: host.name,
          description: `${host.hostname} · ${host.environment}/${host.os_type}`,
          type: "host",
          action: () => {
            window.location.hash = `#/hosts/${host.id}`;
          },
        });
      }
    });
    paletteGroups.forEach((group) => {
      if (!query || matches(group.name)) {
        items.push({
          id: `group-${group.id}`,
          label: group.name,
          description: `Группа · ${group.type}`,
          type: "group",
          action: () => {
            window.location.hash = "";
            setActive("Groups");
          },
        });
      }
    });
    paletteSecrets.forEach((secret) => {
      if (!query || matches(secret.name)) {
        items.push({
          id: `secret-${secret.id}`,
          label: secret.name,
          description: `Secret · ${secret.type}/${secret.scope}`,
          type: "secret",
          action: () => {
            window.location.hash = "";
            setActive("Secrets");
          },
        });
      }
    });
    palettePlaybooks.forEach((playbook) => {
      if (!query || matches(playbook.name)) {
        items.push({
          id: `playbook-${playbook.id}`,
          label: playbook.name,
          description: "Плейбук",
          type: "playbook",
          action: () => {
            window.location.hash = "";
            setActive("Automation");
          },
        });
      }
    });
    return items.slice(0, 30);
  }, [paletteQuery, paletteHosts, paletteGroups, paletteSecrets, palettePlaybooks, staticActions]);

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

  const closePalette = () => {
    setPaletteOpen(false);
    setPaletteQuery("");
  };

  const palette = paletteOpen ? (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal command-palette">
        <div className="modal-header">
          <div>
            <strong>Поиск и команды</strong>
            <div className="form-helper">Хосты, группы, плейбуки, секреты.</div>
          </div>
          <div className="row-actions">
            <button type="button" className="ghost-button" onClick={closePalette}>
              Закрыть
            </button>
          </div>
        </div>
        <div className="panel" style={{ padding: "0.75rem" }}>
          <input
            ref={paletteInputRef}
            className="palette-input"
            placeholder="Введите имя или действие…"
            value={paletteQuery}
            onChange={(e) => setPaletteQuery(e.target.value)}
          />
          {paletteLoading && <p className="form-helper">Загружаем...</p>}
          {paletteError && <p className="text-error">{paletteError}</p>}
          {!paletteLoading && paletteItems.length === 0 && <p className="form-helper">Ничего не найдено</p>}
          {paletteItems.length > 0 && (
            <ul className="palette-list">
              {paletteItems.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`palette-item palette-${item.type}`}
                    onClick={() => {
                      item.action();
                      closePalette();
                    }}
                  >
                    <div>
                      <div className="palette-title">{item.label}</div>
                      {item.description && <div className="palette-description">{item.description}</div>}
                    </div>
                    <span className="palette-tag">{item.type}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  ) : null;

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
              <TopBar
                sidebarOpen={sidebarOpen}
                onToggleSidebar={() => setSidebarOpen((v) => !v)}
                onOpenSearch={() => setPaletteOpen(true)}
              />
              <section className="section-shell">
                <HostDetailsPage hostId={hostDetailsId} />
              </section>
            </main>
          </div>
          {palette}
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
            <TopBar
              sidebarOpen={sidebarOpen}
              onToggleSidebar={() => setSidebarOpen((v) => !v)}
              onOpenSearch={() => setPaletteOpen(true)}
            />
            <section className="section-shell">
              <ActivePage />
            </section>
          </main>
        </div>
        {palette}
      </ConfirmProvider>
    </ToastProvider>
  );
}

export default App;
