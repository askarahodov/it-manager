import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import TerminalPane from "../components/TerminalPane";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useToast } from "../components/ui/ToastProvider";
import { formatError } from "../lib/errors";

type HostStatus = "online" | "offline" | "unknown";
type SecretOption = { id: number; name: string; type: string };

type Host = {
  id: number;
  name: string;
  hostname: string;
  port: number;
  username: string;
  os_type: string;
  environment: string;
  status: HostStatus;
  tags: Record<string, string>;
  description?: string | null;
  credential_id?: number | null;
  last_checked_at?: string | null;
  last_run_id?: number | null;
  last_run_status?: string | null;
  last_run_at?: string | null;
  health_snapshot?: Record<string, number | string> | null;
  health_checked_at?: string | null;
  facts_snapshot?: Record<string, any> | null;
  facts_checked_at?: string | null;
};

type HostHealthRecord = {
  id: number;
  host_id: number;
  status: HostStatus;
  snapshot?: Record<string, number | string> | null;
  checked_at: string;
};

type HostFormState = {
  name: string;
  hostname: string;
  port: number;
  username: string;
  os_type: string;
  environment: string;
  tags: string;
  description: string;
  credential_id?: number | "";
  check_method?: "ping" | "tcp" | "ssh";
};

function parseTags(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .reduce<Record<string, string>>((acc, part) => {
      const [key, val] = part.split("=").map((piece) => piece.trim());
      if (!key) return acc;
      acc[key] = val || "";
      return acc;
    }, {});
}

function formatKb(value?: number) {
  if (!value && value !== 0) return "—";
  const gb = value / 1024 / 1024;
  if (gb >= 1) {
    return `${gb.toFixed(1)} GB`;
  }
  const mb = value / 1024;
  return `${mb.toFixed(1)} MB`;
}

function formatUptime(seconds?: number) {
  if (!seconds && seconds !== 0) return "—";
  const total = Math.floor(seconds);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatFactValue(value?: string | number | null) {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function HostDetailsPage({ hostId }: { hostId: number }) {
  const { token, status, user } = useAuth();
  const { pushToast } = useToast();
  const canManageHosts = user?.role === "admin" || user?.role === "operator";
  const canSsh = user?.role === "admin" || user?.role === "operator";
  const canRunAutomation = user?.role === "admin" || user?.role === "operator" || user?.role === "automation-only";

  const [activeTab, setActiveTab] = useState<"details" | "terminal">("details");
  const [host, setHost] = useState<Host | null>(null);
  const [secrets, setSecrets] = useState<SecretOption[]>([]);
  const [healthHistory, setHealthHistory] = useState<HostHealthRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [factsLoading, setFactsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<HostFormState | null>(null);

  const sshSecretOptions = useMemo(
    () => secrets.filter((s) => s.type === "password" || s.type === "private_key"),
    [secrets]
  );

  const syncFormFromHost = (h: Host) => {
    setForm({
      name: h.name,
      hostname: h.hostname,
      port: h.port,
      username: h.username,
      os_type: h.os_type,
      environment: h.environment,
      tags: Object.entries(h.tags)
        .map(([k, v]) => `${k}=${v}`)
        .join(", "),
      description: h.description ?? "",
      credential_id: h.credential_id ?? "",
      check_method: (h as any).check_method ?? "tcp",
    });
  };

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [h, sec, hh] = await Promise.all([
        apiFetch<Host>(`/api/v1/hosts/${hostId}`, { token }),
        apiFetch<SecretOption[]>("/api/v1/secrets/", { token }),
        apiFetch<HostHealthRecord[]>(`/api/v1/hosts/${hostId}/health-history`, { token }),
      ]);
      setHost(h);
      syncFormFromHost(h);
      setSecrets(sec);
      setHealthHistory(hh);
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Не удалось загрузить хост", description: msg, variant: "error" });
    } finally {
      setLoading(false);
    }
  }, [token, hostId, pushToast]);

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  useEffect(() => {
    if (!token) return;
    const onProjectChange = () => {
      load().catch(() => undefined);
    };
    window.addEventListener("itmgr:project-change", onProjectChange);
    return () => window.removeEventListener("itmgr:project-change", onProjectChange);
  }, [token, load]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (activeTab === "terminal") setActiveTab("details");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeTab]);

  const handleChange = (event: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    if (!form) return;
    const { name, value } = event.target;
    setForm((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        [name]:
          name === "port"
            ? Number(value)
            : name === "credential_id"
              ? value === "" ? "" : Number(value)
              : value,
      } as HostFormState;
    });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!token || !form) return;
    if (!canManageHosts) {
      const msg = "Требуются права admin/operator для редактирования хоста.";
      setError(msg);
      pushToast({ title: "Недостаточно прав", description: msg, variant: "warning" });
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = {
        ...form,
        tags: parseTags(form.tags),
        credential_id: form.credential_id === "" ? null : form.credential_id,
        description: form.description || null,
      };
      const saved = await apiFetch<Host>(`/api/v1/hosts/${hostId}`, {
        method: "PUT",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setHost(saved);
      syncFormFromHost(saved);
      pushToast({ title: "Хост обновлён", description: saved.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка сохранения", description: msg, variant: "error" });
    } finally {
      setSaving(false);
    }
  };

  const checkStatus = async () => {
    if (!token) return;
    setError(null);
    try {
      if (!canManageHosts) {
        throw new Error("Недостаточно прав для проверки статуса (нужна роль admin/operator).");
      }
      const updated = await apiFetch<Host>(`/api/v1/hosts/${hostId}/status-check`, { method: "POST", token });
      setHost(updated);
      if (form) syncFormFromHost(updated);
      const history = await apiFetch<HostHealthRecord[]>(`/api/v1/hosts/${hostId}/health-history`, { token });
      setHealthHistory(history);
      pushToast({ title: "Статус обновлён", description: `${updated.name}: ${updated.status}`, variant: "info" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка проверки статуса", description: msg, variant: "error" });
    }
  };

  const refreshFacts = async () => {
    if (!token) return;
    setError(null);
    setFactsLoading(true);
    try {
      if (!canRunAutomation) {
        throw new Error("Недостаточно прав для запуска facts (нужна роль admin/operator/automation-only).");
      }
      const run = await apiFetch<{ id: number }>(`/api/v1/hosts/${hostId}/facts-refresh`, { method: "POST", token });
      pushToast({ title: "Сбор фактов запущен", description: `Run #${run.id}`, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка запуска facts", description: msg, variant: "error" });
    } finally {
      setFactsLoading(false);
    }
  };

  if (!token || status === "anonymous") {
    return (
      <div className="page-content">
        <header className="page-header">
          <div>
            <p className="page-kicker">Инвентаризация</p>
            <h1>Хост</h1>
          </div>
        </header>
        <div className="panel">
          <p className="text-error">Для просмотра требуется токен. Войдите в «Настройки».</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <p className="page-kicker">Инвентаризация</p>
          <h1>{host ? `Хост: ${host.name}` : `Хост #${hostId}`}</h1>
          {host && (
            <p className="form-helper">
              {host.hostname}:{host.port} · {host.username} · {host.environment}/{host.os_type} · статус: {host.status}
            </p>
          )}
        </div>
        <div className="row-actions">
          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              window.location.hash = "";
            }}
          >
            Назад
          </button>
          <button type="button" className="ghost-button" onClick={checkStatus} disabled={loading || !canManageHosts}>
            Проверить статус
          </button>
          <button type="button" className="ghost-button" onClick={refreshFacts} disabled={factsLoading || !canRunAutomation}>
            {factsLoading ? "Собираем факты..." : "Собрать факты"}
          </button>
        </div>
      </header>

      {error && <p className="text-error">{error}</p>}
      {loading && <p>Загружаем...</p>}

      <div className="row-actions" style={{ gap: 8 }}>
        <button
          type="button"
          className={`ghost-button ${activeTab === "details" ? "active" : ""}`}
          onClick={() => setActiveTab("details")}
          aria-label="Вкладка: детали"
        >
          Детали
        </button>
        <button
          type="button"
          className={`ghost-button ${activeTab === "terminal" ? "active" : ""}`}
          onClick={() => setActiveTab("terminal")}
          disabled={!canSsh || !host || host.status === "offline" || !host.credential_id}
          title={
            !canSsh
              ? "Недостаточно прав для SSH (нужна роль admin/operator)"
              : !host
              ? "Хост ещё не загружен"
              : host.status === "offline"
                ? "Хост offline"
                : !host.credential_id
                  ? "Для SSH нужен credential (password/private_key)"
                  : "Открыть терминал"
          }
          aria-label="Вкладка: терминал"
        >
          Терминал
        </button>
        <button
          type="button"
          className="ghost-button"
          onClick={() => window.open(`${window.location.origin}/#/terminal/${hostId}`, "_blank", "noopener,noreferrer")}
          title="Открыть терминал в отдельном окне"
        >
          Терминал в окне
        </button>
      </div>

      {activeTab === "details" && (
        <div className="grid">
          <div className="panel">
            <div className="panel-title">
              <h2>Редактирование</h2>
              {!canManageHosts && <p className="form-helper">Read-only: редактирование доступно только admin/operator.</p>}
            </div>
            {!form && <p className="form-helper">Форма ещё не загружена.</p>}
            {form && (
              <form className="form-stack" onSubmit={submit}>
                <label>
                  Название
                  <input name="name" value={form.name} onChange={handleChange} disabled={!canManageHosts} />
                </label>
                <label>
                  Hostname/IP
                  <input name="hostname" value={form.hostname} onChange={handleChange} disabled={!canManageHosts} />
                </label>
                <label>
                  Порт
                  <input name="port" type="number" value={form.port} onChange={handleChange} min={1} max={65535} disabled={!canManageHosts} />
                </label>
                <label>
                  Пользователь
                  <input name="username" value={form.username} onChange={handleChange} disabled={!canManageHosts} />
                </label>
                <label>
                  OS
                  <input name="os_type" value={form.os_type} onChange={handleChange} disabled={!canManageHosts} />
                </label>
                <label>
                  Среда
                  <select name="environment" value={form.environment} onChange={handleChange} disabled={!canManageHosts}>
                    <option value="prod">prod</option>
                    <option value="stage">stage</option>
                    <option value="dev">dev</option>
                  </select>
                </label>
                <label>
                  Описание
                  <textarea name="description" value={form.description} onChange={handleChange} rows={4} disabled={!canManageHosts} />
                </label>
                <label>
                  Теги (key=value, ...)
                  <input name="tags" value={form.tags} onChange={handleChange} disabled={!canManageHosts} />
                </label>
                <label>
                  Credential (из Secrets)
                  <select name="credential_id" value={form.credential_id} onChange={handleChange} disabled={!canManageHosts}>
                    <option value="">—</option>
                    {sshSecretOptions.map((secret) => (
                      <option key={secret.id} value={secret.id}>
                        {secret.name} ({secret.type})
                      </option>
                    ))}
                  </select>
                  <span className="form-helper">Показываются только secrets типов password/private_key (для SSH).</span>
                </label>
                <label>
                  Метод проверки статуса
                  <select name="check_method" value={form.check_method ?? "tcp"} onChange={handleChange} disabled={!canManageHosts}>
                    <option value="tcp">tcp</option>
                    <option value="ping">ping</option>
                    <option value="ssh">ssh</option>
                  </select>
                  <span className="form-helper">ssh использует credential (password/private_key).</span>
                </label>
                <div className="form-actions">
                  <button type="submit" className="primary-button" disabled={!canManageHosts || saving}>
                    {saving ? "Сохраняем..." : "Сохранить"}
                  </button>
                  <button type="button" className="ghost-button" onClick={() => host && syncFormFromHost(host)} disabled={saving}>
                    Сброс
                  </button>
                </div>
                {error && <span className="text-error form-error">{error}</span>}
              </form>
            )}
          </div>

          <div className="panel">
            <div className="panel-title">
              <h2>Информация</h2>
              <p className="form-helper">Терминал доступен только при статусе online и наличии credential.</p>
            </div>
            {host ? (
              <div className="stack">
                <div><strong>ID:</strong> {host.id}</div>
                <div><strong>Статус:</strong> {host.status}</div>
                <div><strong>Последняя проверка:</strong> {host.last_checked_at ? new Date(host.last_checked_at).toLocaleString() : "—"}</div>
                <div>
                  <strong>Последний Ansible-run:</strong>{" "}
                  {host.last_run_status ? `${host.last_run_status}${host.last_run_id ? ` (#${host.last_run_id})` : ""}` : "—"}
                </div>
                <div><strong>Время последнего run:</strong> {host.last_run_at ? new Date(host.last_run_at).toLocaleString() : "—"}</div>
                <div><strong>Метод проверки:</strong> {(host as any).check_method ?? "tcp"}</div>
                <div><strong>Credential ID:</strong> {host.credential_id ?? "—"}</div>
                <div><strong>Health snapshot:</strong> {host.health_checked_at ? new Date(host.health_checked_at).toLocaleString() : "—"}</div>
                {host.health_snapshot ? (
                  <div className="stack">
                    <div><strong>Uptime:</strong> {formatUptime(Number(host.health_snapshot.uptime_seconds))}</div>
                    <div>
                      <strong>Load:</strong>{" "}
                      {host.health_snapshot.load1 ?? "—"} / {host.health_snapshot.load5 ?? "—"} / {host.health_snapshot.load15 ?? "—"}
                    </div>
                    <div>
                      <strong>Memory:</strong>{" "}
                      {formatKb(Number(host.health_snapshot.mem_used_kb))} / {formatKb(Number(host.health_snapshot.mem_total_kb))}
                    </div>
                    <div>
                      <strong>Disk:</strong>{" "}
                      {formatKb(Number(host.health_snapshot.disk_used_kb))} / {formatKb(Number(host.health_snapshot.disk_total_kb))}{" "}
                      ({host.health_snapshot.disk_used_percent ?? "—"}%)
                    </div>
                  </div>
                ) : (
                  <div className="form-helper">Метрики доступны только при проверке по SSH.</div>
                )}
                <div><strong>Facts snapshot:</strong> {host.facts_checked_at ? new Date(host.facts_checked_at).toLocaleString() : "—"}</div>
                {host.facts_snapshot ? (
                  <div className="stack">
                    <div><strong>OS:</strong> {formatFactValue(host.facts_snapshot.ansible_distribution)} {formatFactValue(host.facts_snapshot.ansible_distribution_version)}</div>
                    <div><strong>Kernel:</strong> {formatFactValue(host.facts_snapshot.ansible_kernel)}</div>
                    <div><strong>CPU:</strong> {formatFactValue(host.facts_snapshot.ansible_processor_vcpus)} vCPU</div>
                    <details>
                      <summary>Показать факты</summary>
                      <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(host.facts_snapshot, null, 2)}</pre>
                    </details>
                  </div>
                ) : (
                  <div className="form-helper">Факты обновляются через Ansible.</div>
                )}
                <div className="panel">
                  <div className="panel-title">
                    <h2>История health checks</h2>
                  </div>
                  {healthHistory.length === 0 && <p className="form-helper">Истории проверок пока нет.</p>}
                  {healthHistory.length > 0 && (
                    <table className="hosts-table">
                      <thead>
                        <tr>
                          <th>Время</th>
                          <th>Статус</th>
                          <th>Load</th>
                          <th>Memory</th>
                          <th>Disk</th>
                        </tr>
                      </thead>
                      <tbody>
                        {healthHistory.map((row) => (
                          <tr key={row.id}>
                            <td>{new Date(row.checked_at).toLocaleString()}</td>
                            <td>{row.status}</td>
                            <td>
                              {row.snapshot
                                ? `${row.snapshot.load1 ?? "—"} / ${row.snapshot.load5 ?? "—"} / ${row.snapshot.load15 ?? "—"}`
                                : "—"}
                            </td>
                            <td>
                              {row.snapshot
                                ? `${formatKb(Number(row.snapshot.mem_used_kb))} / ${formatKb(Number(row.snapshot.mem_total_kb))}`
                                : "—"}
                            </td>
                            <td>
                              {row.snapshot
                                ? `${formatKb(Number(row.snapshot.disk_used_kb))} / ${formatKb(Number(row.snapshot.disk_total_kb))}`
                                : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            ) : (
              <p className="form-helper">Данные ещё не загружены.</p>
            )}
          </div>
        </div>
      )}

      {activeTab === "terminal" && (
        <div className="panel" style={{ padding: 0 }}>
          <TerminalPane
            hostId={hostId}
            token={token}
            disabled={!canSsh || !host || host.status === "offline" || !host.credential_id}
            height={560}
          />
        </div>
      )}
    </div>
  );
}

export default HostDetailsPage;
