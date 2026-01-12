import { useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useToast } from "../components/ui/ToastProvider";
import { formatError } from "../lib/errors";

type Host = { id: number; status: "online" | "offline" | "unknown"; environment: string; last_run_status?: string | null };
type Run = { id: number; status: "pending" | "running" | "success" | "failed"; playbook_id: number; triggered_by: string; created_at: string };
type Secret = { id: number; name: string; expires_at?: string | null };
type Playbook = {
  id: number;
  name: string;
  schedule?: {
    enabled: boolean;
    type: "interval" | "cron";
    value: string;
    last_run_at?: string | null;
  } | null;
};
type AuditEvent = {
  id: number;
  actor: string;
  action: string;
  source_ip?: string | null;
  created_at: string;
  success: boolean;
};

const FALLBACK_CARDS = [
  { title: "Хосты", value: "—", hint: "Данные не загружены" },
  { title: "Автоматизация", value: "—", hint: "Запуски не загружены" },
  { title: "Секреты", value: "—", hint: "Секреты не загружены" },
];

function DashboardPage() {
  const { token, status, user } = useAuth();
  const { pushToast } = useToast();
  const isAdmin = user?.role === "admin";

  const [hosts, setHosts] = useState<Host[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [secrets, setSecrets] = useState<Secret[]>([]);
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [sshEvents, setSshEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const auditPromise = isAdmin
        ? apiFetch<AuditEvent[]>("/api/v1/audit/?limit=10&action=ssh.connect", { token })
        : Promise.resolve<AuditEvent[]>([]);
      const [h, r, s, p, a] = await Promise.all([
        apiFetch<Host[]>("/api/v1/hosts/", { token }),
        apiFetch<Run[]>("/api/v1/runs/", { token }),
        apiFetch<Secret[]>("/api/v1/secrets/", { token }),
        apiFetch<Playbook[]>("/api/v1/playbooks/", { token }),
        auditPromise,
      ]);
      setHosts(h ?? []);
      setRuns(r ?? []);
      setSecrets(s ?? []);
      setPlaybooks(p ?? []);
      if (isAdmin) {
        setSshEvents(a ?? []);
      }
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Не удалось загрузить дашборд", description: msg, variant: "error" });
    } finally {
      setLoading(false);
    }
  }, [token, isAdmin, pushToast]);

  useEffect(() => {
    if (!token) return;
    loadDashboard().catch(() => undefined);
  }, [token, loadDashboard]);

  useEffect(() => {
    if (!token) return;
    const onProjectChange = () => {
      loadDashboard().catch(() => undefined);
    };
    window.addEventListener("itmgr:project-change", onProjectChange);
    return () => window.removeEventListener("itmgr:project-change", onProjectChange);
  }, [token, loadDashboard]);

  const hostStats = useMemo(() => {
    const stats = { total: hosts.length, online: 0, offline: 0, unknown: 0 };
    hosts.forEach((h) => {
      if (h.status === "online") stats.online += 1;
      else if (h.status === "offline") stats.offline += 1;
      else stats.unknown += 1;
    });
    return stats;
  }, [hosts]);

  const lastRun = runs[0];
  const scheduledPlaybooks = playbooks.filter((pb) => pb.schedule?.enabled);
  const expiringSecrets = useMemo(() => {
    const now = Date.now();
    const threshold = now + 1000 * 60 * 60 * 24 * 30;
    return secrets
      .filter((sec) => sec.expires_at)
      .map((sec) => ({ ...sec, expires_at: sec.expires_at }))
      .filter((sec) => {
        const ts = new Date(sec.expires_at as string).getTime();
        return !Number.isNaN(ts) && ts <= threshold;
      })
      .sort((a, b) => new Date(a.expires_at as string).getTime() - new Date(b.expires_at as string).getTime())
      .slice(0, 5);
  }, [secrets]);

  const cards = token
    ? [
        { title: "Хосты", value: String(hostStats.total), hint: `${hostStats.online} online · ${hostStats.offline} offline` },
        { title: "Автоматизация", value: String(runs.length), hint: lastRun ? `Последний run #${lastRun.id} (${lastRun.status})` : "Запусков нет" },
        {
          title: "Секреты",
          value: String(secrets.length),
          hint: expiringSecrets.length ? `Скоро истекают: ${expiringSecrets.length}` : secrets.length ? "Хранилище активное" : "Секретов нет",
        },
      ]
    : FALLBACK_CARDS;

  if (!token || status === "anonymous") {
    return (
      <div className="page-content">
        <header className="page-header">
          <div>
            <p className="page-kicker">Обзор инфраструктуры</p>
            <h1>Дашборд IT Manager</h1>
          </div>
        </header>
        <div className="panel">
          <p>Для просмотра дашборда нужно войти в Settings.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <p className="page-kicker">Обзор инфраструктуры</p>
          <h1>Дашборд IT Manager</h1>
        </div>
        <div className="row-actions">
          <button type="button" className="ghost-button" onClick={loadDashboard} disabled={loading}>
            Обновить
          </button>
        </div>
      </header>

      {error && <p className="text-error">{error}</p>}
      {loading && <p>Загружаем...</p>}

      <div className="grid cards">
        {cards.map((card) => (
          <div key={card.title} className="metric-card">
            <p className="metric-title">{card.title}</p>
            <p className="metric-value">{card.value}</p>
            <p className="metric-hint">{card.hint}</p>
          </div>
        ))}
      </div>

      <div className="grid">
        <div className="panel">
          <div className="panel-title">
            <h2>Статус хостов</h2>
            <p className="form-helper">Онлайн/оффлайн распределение по проекту.</p>
          </div>
          <div className="status-summary">
            <div>
              <span className="status-pill mini online">online</span>
              <strong>{hostStats.online}</strong>
            </div>
            <div>
              <span className="status-pill mini offline">offline</span>
              <strong>{hostStats.offline}</strong>
            </div>
            <div>
              <span className="status-pill mini unknown">unknown</span>
              <strong>{hostStats.unknown}</strong>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">
            <h2>Последние запуски</h2>
            <p className="form-helper">Текущий статус automation.</p>
          </div>
          {runs.length === 0 && <p>Запусков пока нет</p>}
          {runs.length > 0 && (
            <table className="hosts-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Статус</th>
                  <th>Источник</th>
                  <th>Время</th>
                </tr>
              </thead>
              <tbody>
                {runs.slice(0, 5).map((run) => (
                  <tr key={run.id}>
                    <td>#{run.id}</td>
                    <td>
                      <span className={`status-pill ${run.status}`}>{run.status}</span>
                    </td>
                    <td>{run.triggered_by}</td>
                    <td>{new Date(run.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="grid">
        <div className="panel">
          <div className="panel-title">
            <h2>Расписания</h2>
            <p className="form-helper">Активные плейбуки с расписанием.</p>
          </div>
          {scheduledPlaybooks.length === 0 && <p>Активных расписаний нет</p>}
          {scheduledPlaybooks.length > 0 && (
            <table className="hosts-table">
              <thead>
                <tr>
                  <th>Плейбук</th>
                  <th>Тип</th>
                  <th>Значение</th>
                  <th>Последний запуск</th>
                </tr>
              </thead>
              <tbody>
                {scheduledPlaybooks.slice(0, 5).map((pb) => (
                  <tr key={pb.id}>
                    <td>{pb.name}</td>
                    <td>{pb.schedule?.type ?? "—"}</td>
                    <td>{pb.schedule?.value ?? "—"}</td>
                    <td>{pb.schedule?.last_run_at ? new Date(pb.schedule.last_run_at).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="panel">
          <div className="panel-title">
            <h2>SSH активность</h2>
            <p className="form-helper">Последние подключения к терминалу.</p>
          </div>
          {!isAdmin && <p className="form-helper">SSH события доступны только admin.</p>}
          {isAdmin && sshEvents.length === 0 && <p>Событий пока нет</p>}
          {isAdmin && sshEvents.length > 0 && (
            <table className="hosts-table">
              <thead>
                <tr>
                  <th>Время</th>
                  <th>Actor</th>
                  <th>IP</th>
                  <th>OK</th>
                </tr>
              </thead>
              <tbody>
                {sshEvents.map((event) => (
                  <tr key={event.id}>
                    <td>{new Date(event.created_at).toLocaleString()}</td>
                    <td>{event.actor}</td>
                    <td>{event.source_ip ?? "—"}</td>
                    <td>{event.success ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">
          <h2>Секреты, требующие внимания</h2>
          <p className="form-helper">Срок действия в ближайшие 30 дней.</p>
        </div>
        {expiringSecrets.length === 0 && <p>Секретов с истекающим сроком пока нет</p>}
        {expiringSecrets.length > 0 && (
          <table className="hosts-table">
            <thead>
              <tr>
                <th>Секрет</th>
                <th>Истекает</th>
              </tr>
            </thead>
            <tbody>
              {expiringSecrets.map((sec) => (
                <tr key={sec.id}>
                  <td>{sec.name}</td>
                  <td>{sec.expires_at ? new Date(sec.expires_at).toLocaleDateString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default DashboardPage;
