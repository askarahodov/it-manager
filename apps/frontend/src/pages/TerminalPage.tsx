import { useCallback, useEffect, useState } from "react";

import TerminalPane from "../components/TerminalPane";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatError } from "../lib/errors";
import { useToast } from "../components/ui/ToastProvider";

type Host = {
  id: number;
  name: string;
  hostname: string;
  port: number;
  status: "online" | "offline" | "unknown";
};

function parseTerminalHostIdFromHash(hash: string): number | null {
  const m = hash.match(/^#\/terminal\/(\d+)\b/);
  if (!m) return null;
  const id = Number(m[1]);
  return Number.isFinite(id) && id > 0 ? id : null;
}

function TerminalPage() {
  const { token, status } = useAuth();
  const { pushToast } = useToast();
  const [hostId, setHostId] = useState<number | null>(() => parseTerminalHostIdFromHash(window.location.hash));
  const [host, setHost] = useState<Host | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [full, setFull] = useState(false);
  const [viewportHeight, setViewportHeight] = useState<number>(() => window.innerHeight);

  useEffect(() => {
    const onHash = () => setHostId(parseTerminalHostIdFromHash(window.location.hash));
    const onResize = () => setViewportHeight(window.innerHeight);
    window.addEventListener("hashchange", onHash);
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  const loadHost = useCallback(() => {
    if (!token || !hostId) return;
    setLoading(true);
    setError(null);
    apiFetch<Host>(`/api/v1/hosts/${hostId}`, { token })
      .then(setHost)
      .catch((err) => {
        const msg = formatError(err);
        setError(msg);
        pushToast({ title: "Не удалось загрузить хост", description: msg, variant: "error" });
      })
      .finally(() => setLoading(false));
  }, [token, hostId, pushToast]);

  useEffect(() => {
    loadHost();
  }, [loadHost]);

  useEffect(() => {
    if (!token) return;
    const onProjectChange = () => {
      loadHost();
    };
    window.addEventListener("itmgr:project-change", onProjectChange);
    return () => window.removeEventListener("itmgr:project-change", onProjectChange);
  }, [token, loadHost]);

  if (!hostId) {
    return (
      <div className="page-content">
        <header className="page-header">
          <div>
            <p className="page-kicker">SSH</p>
            <h1>Терминал</h1>
          </div>
        </header>
        <div className="panel">
          <p className="text-error">Не указан hostId в URL. Откройте через Hosts → Terminal → «Открыть в окне».</p>
        </div>
      </div>
    );
  }

  if (!token || status === "anonymous") {
    return (
      <div className="page-content">
        <header className="page-header">
          <div>
            <p className="page-kicker">SSH</p>
            <h1>Терминал</h1>
          </div>
        </header>
        <div className="panel">
          <p className="text-error">Для подключения требуется токен. Войдите в Settings и обновите страницу.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <p className="page-kicker">SSH</p>
          <h1>{host ? `Терминал: ${host.name}` : `Терминал: host ${hostId}`}</h1>
          {host && <p className="form-helper">{host.hostname}:{host.port} — {host.status}</p>}
        </div>
        <div className="row-actions">
          <button type="button" className="ghost-button" onClick={() => setFull((v) => !v)}>
            {full ? "Окно" : "На весь экран"}
          </button>
          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              // если это отдельное окно, пытаемся закрыть; иначе просто вернёмся в основную страницу
              window.location.hash = "";
              try {
                window.close();
              } catch {
                // ignore
              }
            }}
          >
            Закрыть
          </button>
        </div>
      </header>

      {loading && <p>Загружаем...</p>}
      {error && <p className="text-error">{error}</p>}
      <div className="panel" style={{ padding: 0 }}>
        <TerminalPane hostId={hostId} token={token} height={full ? Math.max(420, viewportHeight - 220) : 520} />
      </div>
    </div>
  );
}

export default TerminalPage;
