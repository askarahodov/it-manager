import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";
import TerminalPane from "../components/TerminalPane";
import { useConfirm } from "../components/ui/ConfirmProvider";
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
  credential_id?: number | null;
  check_method?: "ping" | "tcp" | "ssh";
};

type SortBy = "name" | "hostname" | "os_type" | "environment" | "status" | "id";
type SortDir = "asc" | "desc";

type HostFormState = {
  name: string;
  hostname: string;
  port: number;
  username: string;
  os_type: string;
  environment: string;
  tags: string;
  credential_id?: number | "";
  check_method?: "ping" | "tcp" | "ssh";
};

const statusBadge = {
  online: "Статус: онлайн",
  offline: "Хост недоступен",
  unknown: "Статус неизвестен",
} satisfies Record<HostStatus, string>;

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

const defaultForm: HostFormState = {
  name: "",
  hostname: "",
  port: 22,
  username: "root",
  os_type: "linux",
  environment: "prod",
  tags: "",
  credential_id: "",
  check_method: "tcp",
};

function HostsPage() {
  const { token, status, user } = useAuth();
  const { confirm } = useConfirm();
  const { pushToast } = useToast();
  const [hosts, setHosts] = useState<Host[]>([]);
  const [secrets, setSecrets] = useState<SecretOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<HostStatus | "">("");
  const [envFilter, setEnvFilter] = useState<string>("");
  const [osFilter, setOsFilter] = useState<string>("");
  const [tagKey, setTagKey] = useState<string>("");
  const [tagValue, setTagValue] = useState<string>("");
  const [sortBy, setSortBy] = useState<SortBy>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [limit, setLimit] = useState<number>(50);
  const [offset, setOffset] = useState<number>(0);
  const [hasNext, setHasNext] = useState<boolean>(false);
  const [formState, setFormState] = useState<HostFormState>(defaultForm);
  const [formMode, setFormMode] = useState<"create" | "edit">("create");
  const [activeHost, setActiveHost] = useState<Host | null>(null);
  const [terminalHost, setTerminalHost] = useState<Host | null>(null);
  const [showTerminal, setShowTerminal] = useState(false);
  const [terminalFull, setTerminalFull] = useState(false);
  const [hostsTab, setHostsTab] = useState<"list" | "form">("list");

  const canManageHosts = user?.role === "admin" || user?.role === "operator";
  const canCheckHosts = canManageHosts;
  const canSsh = user?.role === "admin" || user?.role === "operator";

  const sshSecretOptions = useMemo(
    () => secrets.filter((s) => s.type === "password" || s.type === "private_key"),
    [secrets]
  );

  const loadHosts = useCallback(async (abortSignal?: AbortSignal) => {
    if (!token) return;
    const params = new URLSearchParams();
    if (search.trim()) params.set("search", search.trim());
    if (statusFilter) params.set("status", statusFilter);
    if (envFilter) params.set("environment", envFilter);
    if (osFilter) params.set("os_type", osFilter);
    if (tagKey.trim()) params.set("tag_key", tagKey.trim());
    if (tagKey.trim() && tagValue.trim()) params.set("tag_value", tagValue.trim());
    params.set("sort_by", sortBy);
    params.set("sort_dir", sortDir);
    params.set("limit", String(limit));
    params.set("offset", String(offset));
    const path = `/api/v1/hosts/?${params.toString()}`;
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<Host[]>(path, { token, signal: abortSignal as any });
      setHosts(data);
      setHasNext(data.length === limit);
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Не удалось загрузить хосты", description: msg, variant: "error" });
    } finally {
      setLoading(false);
    }
  }, [token, search, statusFilter, envFilter, osFilter, tagKey, tagValue, sortBy, sortDir, limit, offset, pushToast]);

  useEffect(() => {
    setOffset(0);
  }, [search, statusFilter, envFilter, osFilter, tagKey, tagValue, sortBy, sortDir, limit]);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    const t = window.setTimeout(() => {
      loadHosts(controller.signal).catch(() => undefined);
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(t);
    };
  }, [token, loadHosts]);

  useEffect(() => {
    if (!token) return;
    const onProjectChange = () => {
      loadHosts().catch(() => undefined);
    };
    window.addEventListener("itmgr:project-change", onProjectChange);
    return () => window.removeEventListener("itmgr:project-change", onProjectChange);
  }, [token, loadHosts]);

  useEffect(() => {
    if (!token) return;
    apiFetch<SecretOption[]>("/api/v1/secrets/", { token })
      .then((list) => setSecrets(list))
      .catch((err) => {
        const msg = formatError(err);
        pushToast({ title: "Не удалось загрузить Secrets", description: msg, variant: "warning" });
      });
  }, [token, pushToast]);

  const totals = useMemo(() => {
    const summary: Record<HostStatus, number> = { online: 0, offline: 0, unknown: 0 };
    hosts.forEach((host) => {
      summary[host.status ?? "unknown"] += 1;
    });
    return summary;
  }, [hosts]);

  const toggleSort = (key: SortBy) => {
    if (sortBy === key) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(key);
      setSortDir("asc");
    }
  };

  const handleSelect = (host: Host) => {
    setActiveHost(host);
    setFormMode("edit");
    setFormState({
      name: host.name,
      hostname: host.hostname,
      port: host.port,
      os_type: host.os_type,
      environment: host.environment,
      username: host.username,
      tags: Object.entries(host.tags)
        .map(([key, val]) => `${key}=${val}`)
        .join(", "),
      credential_id: host.credential_id ?? "",
      check_method: host.check_method ?? "tcp",
    });
    setHostsTab("form");
  };

  const handleResetForm = () => {
    setFormMode("create");
    setActiveHost(null);
    setFormState({ ...defaultForm });
    setHostsTab("list");
  };

  const handleChange = (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = event.target;
    setFormState((prev) => ({
      ...prev,
      [name]:
        name === "port"
          ? Number(value)
          : name === "credential_id"
            ? value === "" ? "" : Number(value)
            : value,
    }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canManageHosts) {
      const msg = "Требуются права admin/operator для создания/редактирования хостов.";
      setError(msg);
      pushToast({ title: "Недостаточно прав", description: msg, variant: "warning" });
      return;
    }
    const payload = {
      ...formState,
      tags: parseTags(formState.tags),
      credential_id: formState.credential_id === "" ? null : formState.credential_id,
    };
    const url = formMode === "create" ? "/api/v1/hosts/" : `/api/v1/hosts/${activeHost?.id}`;
    const method = formMode === "create" ? "POST" : "PUT";
    try {
      if (!token) {
        throw new Error("Нужно войти в систему");
      }
      const saved = await apiFetch<Host>(url, {
        method,
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setHosts((prev) => {
        if (formMode === "edit") {
          return prev.map((host) => (host.id === saved.id ? saved : host));
        }
        return [...prev, saved];
      });
      pushToast({
        title: formMode === "edit" ? "Хост обновлён" : "Хост создан",
        description: `${saved.name} (${saved.hostname}:${saved.port})`,
        variant: "success",
      });
      handleResetForm();
      loadHosts().catch(() => undefined);
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка сохранения хоста", description: msg, variant: "error" });
    }
  };

  const handleCheckStatus = async (host: Host) => {
    try {
      if (!token) {
        throw new Error("Нужно войти в систему");
      }
      if (!canCheckHosts) {
        throw new Error("Недостаточно прав для проверки статуса (нужна роль admin/operator).");
      }
      const updated = await apiFetch<Host>(`/api/v1/hosts/${host.id}/status-check`, {
        method: "POST",
        token,
      });
      setHosts((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      pushToast({
        title: "Статус обновлён",
        description: `${updated.name}: ${updated.status}`,
        variant: updated.status === "online" ? "success" : updated.status === "offline" ? "warning" : "info",
      });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка проверки статуса", description: msg, variant: "error" });
    }
  };

  const handleDeleteHost = async (host: Host) => {
    setError(null);
    if (!token) return;
    if (!canManageHosts) {
      const msg = "Требуются права admin/operator для удаления хостов.";
      setError(msg);
      pushToast({ title: "Недостаточно прав", description: msg, variant: "warning" });
      return;
    }
    const ok = await confirm({
      title: "Удалить хост?",
      description: `Будет удалён хост "${host.name}" (${host.hostname}:${host.port}).`,
      confirmText: "Удалить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!ok) return;
    try {
      await apiFetch<void>(`/api/v1/hosts/${host.id}`, { method: "DELETE", token });
      setHosts((prev) => prev.filter((item) => item.id !== host.id));
      if (activeHost?.id === host.id) {
        handleResetForm();
      }
      pushToast({ title: "Хост удалён", description: host.name, variant: "success" });
      loadHosts().catch(() => undefined);
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка удаления хоста", description: msg, variant: "error" });
    }
  };

  const openDetails = (host: Host) => {
    window.location.hash = `#/hosts/${host.id}`;
  };

  useEffect(() => {
    if (!showTerminal) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setShowTerminal(false);
      setTerminalFull(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showTerminal]);

  return (
    <div className="page-content hosts-page">
      <header className="page-header">
        <div>
          <p className="page-kicker">Инвентаризация</p>
          <h1>Хосты</h1>
        </div>
        <div className="status-summary">
          {Object.entries(totals).map(([status, value]) => (
            <div key={status} className={`status-pill mini ${status}`}>
              {status}: {value}
            </div>
          ))}
        </div>
      </header>

      <div className="tabs">
        <button
          type="button"
          className={`tab-button ${hostsTab === "list" ? "active" : ""}`}
          onClick={() => setHostsTab("list")}
        >
          Инвентарь
        </button>
        <button
          type="button"
          className={`tab-button ${hostsTab === "form" ? "active" : ""}`}
          onClick={() => setHostsTab("form")}
        >
          {formMode === "create" ? "Добавить" : "Редактировать"}
        </button>
      </div>

      <div className="grid">
        {hostsTab === "list" && (
        <div className="panel hosts-list">
          <div className="panel-title">
            <h2>Список хостов</h2>
            <p>Нажмите на строку, чтобы отредактировать</p>
          </div>
          <div className="row-actions" style={{ alignItems: "center", flexWrap: "wrap" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="form-helper" style={{ margin: 0 }}>Поиск</span>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="имя/hostname"
                aria-label="Поиск по имени/hostname"
                style={{ minWidth: 220 }}
              />
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="form-helper" style={{ margin: 0 }}>Статус</span>
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as any)}>
                <option value="">все</option>
                <option value="online">online</option>
                <option value="offline">offline</option>
                <option value="unknown">unknown</option>
              </select>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="form-helper" style={{ margin: 0 }}>Среда</span>
              <input value={envFilter} onChange={(e) => setEnvFilter(e.target.value)} placeholder="prod" aria-label="Фильтр по environment" style={{ minWidth: 140 }} />
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="form-helper" style={{ margin: 0 }}>ОС</span>
              <input value={osFilter} onChange={(e) => setOsFilter(e.target.value)} placeholder="linux" aria-label="Фильтр по os_type" style={{ minWidth: 120 }} />
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="form-helper" style={{ margin: 0 }}>Тег: ключ</span>
              <input value={tagKey} onChange={(e) => setTagKey(e.target.value)} placeholder="env" aria-label="Фильтр по ключу тега" style={{ minWidth: 120 }} />
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="form-helper" style={{ margin: 0 }}>Тег: значение</span>
              <input value={tagValue} onChange={(e) => setTagValue(e.target.value)} placeholder="prod" aria-label="Фильтр по значению тега" style={{ minWidth: 120 }} />
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="form-helper" style={{ margin: 0 }}>Страница</span>
              <select value={String(limit)} onChange={(e) => setLimit(Number(e.target.value))} title="Размер страницы">
                <option value="25">25</option>
                <option value="50">50</option>
                <option value="100">100</option>
              </select>
            </label>
            <button type="button" className="ghost-button" onClick={() => loadHosts()}>
              Обновить
            </button>
          </div>
          <div className="row-actions" style={{ marginTop: 8, justifyContent: "space-between" }}>
            <div className="form-helper" style={{ marginTop: 0 }}>
              Показано: {hosts.length} (offset {offset})
            </div>
            <div className="row-actions">
              <button type="button" className="ghost-button" disabled={offset === 0 || loading} onClick={() => setOffset((v) => Math.max(0, v - limit))}>
                Назад
              </button>
              <button type="button" className="ghost-button" disabled={!hasNext || loading} onClick={() => setOffset((v) => v + limit)}>
                Вперёд
              </button>
            </div>
          </div>
          {!token && status === "anonymous" && (
            <p className="text-error">Нет токена. Перейдите в Settings и выполните вход.</p>
          )}
          {loading && <p>Загружаем хосты...</p>}
          {error && <p className="text-error">{error}</p>}
          {!loading && token && hosts.length === 0 && <p>Хосты отсутствуют</p>}
          {!loading && !token && <p className="text-error">Нет токена — войдите в Settings.</p>}
          {loading && hosts.length === 0 && (
            <div className="table-scroll" style={{ maxHeight: "clamp(320px, 55vh, 720px)" }}>
              <table className="hosts-table">
                <thead>
                  <tr>
                    <th>Название</th>
                    <th>Hostname/IP</th>
                    <th>ОС</th>
                    <th>Пользователь</th>
                    <th>Среда</th>
                    <th>Статус</th>
                    <th>Действие</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: 6 }).map((_, idx) => (
                    <tr key={`skeleton-host-${idx}`}>
                      <td><span className="skeleton-line" /></td>
                      <td><span className="skeleton-line" /></td>
                      <td><span className="skeleton-line small" /></td>
                      <td><span className="skeleton-line" /></td>
                      <td><span className="skeleton-line small" /></td>
                      <td><span className="skeleton-line small" /></td>
                      <td><span className="skeleton-line" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {hosts.length > 0 && (
            <div className="table-scroll" style={{ maxHeight: "clamp(320px, 55vh, 720px)" }}>
              <table className="hosts-table">
                <thead>
                  <tr>
                    <th aria-sort={sortBy === "name" ? (sortDir === "asc" ? "ascending" : "descending") : "none"} scope="col">
                      <button type="button" className="th-sort-button" onClick={() => toggleSort("name")} aria-label="Сортировать по названию">
                        <span>Название</span>
                        <span className={`sort-indicator ${sortBy === "name" ? "active" : ""}`}>{sortBy === "name" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span>
                      </button>
                    </th>
                    <th aria-sort={sortBy === "hostname" ? (sortDir === "asc" ? "ascending" : "descending") : "none"} scope="col">
                      <button type="button" className="th-sort-button" onClick={() => toggleSort("hostname")} aria-label="Сортировать по hostname/ip">
                        <span>Hostname/IP</span>
                        <span className={`sort-indicator ${sortBy === "hostname" ? "active" : ""}`}>{sortBy === "hostname" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span>
                      </button>
                    </th>
                    <th aria-sort={sortBy === "os_type" ? (sortDir === "asc" ? "ascending" : "descending") : "none"} scope="col">
                      <button type="button" className="th-sort-button" onClick={() => toggleSort("os_type")} aria-label="Сортировать по ОС">
                        <span>ОС</span>
                        <span className={`sort-indicator ${sortBy === "os_type" ? "active" : ""}`}>{sortBy === "os_type" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span>
                      </button>
                    </th>
                    <th scope="col">Пользователь</th>
                    <th aria-sort={sortBy === "environment" ? (sortDir === "asc" ? "ascending" : "descending") : "none"} scope="col">
                      <button type="button" className="th-sort-button" onClick={() => toggleSort("environment")} aria-label="Сортировать по среде">
                        <span>Среда</span>
                        <span className={`sort-indicator ${sortBy === "environment" ? "active" : ""}`}>{sortBy === "environment" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span>
                      </button>
                    </th>
                    <th aria-sort={sortBy === "status" ? (sortDir === "asc" ? "ascending" : "descending") : "none"} scope="col">
                      <button type="button" className="th-sort-button" onClick={() => toggleSort("status")} aria-label="Сортировать по статусу">
                        <span>Статус</span>
                        <span className={`sort-indicator ${sortBy === "status" ? "active" : ""}`}>{sortBy === "status" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span>
                      </button>
                    </th>
                    <th scope="col">Действие</th>
                  </tr>
                </thead>
                <tbody>
                  {hosts.map((host) => (
                    <tr key={host.id} onClick={() => handleSelect(host)}>
                      <td>{host.name}</td>
                      <td>{host.hostname}:{host.port}</td>
                      <td>{host.os_type}</td>
                      <td>{host.username}</td>
                      <td>{host.environment}</td>
                      <td>
                        <span className={`status-pill mini ${host.status}`}>{host.status}</span>
                      </td>
                      <td>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={(event) => {
                              event.stopPropagation();
                              handleCheckStatus(host);
                            }}
                          >
                            Проверить
                          </button>
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={(event) => {
                              event.stopPropagation();
                              openDetails(host);
                            }}
                            title="Открыть карточку хоста"
                          >
                            Детали
                          </button>
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={host.status === "offline" || !host.credential_id || !canSsh}
                          onClick={(event) => {
                            event.stopPropagation();
                            setTerminalHost(host);
                            setShowTerminal(true);
                          }}
                          title={
                            host.status === "offline"
                              ? "Хост offline"
                              : !host.credential_id
                                ? "Для SSH нужен credential (password/private_key)"
                                : !canSsh
                                  ? "Недостаточно прав для SSH (нужна роль admin/operator)"
                                : "Открыть терминал"
                          }
                        >
                          Терминал
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleDeleteHost(host);
                          }}
                          disabled={!canManageHosts}
                        >
                          Удалить
                        </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        )}
        {hostsTab === "form" && (
        <div className="panel hosts-form">
          <div className="panel-title">
            <h2>{formMode === "create" ? "Добавить хост" : "Редактировать хост"}</h2>
            <p>{statusBadge[activeHost?.status ?? "unknown"]}</p>
          </div>
          {!canManageHosts && <p className="form-helper">Режим read-only: создание/редактирование/удаление доступно только admin/operator.</p>}
          <form onSubmit={handleSubmit} className="form-stack">
            <label>
              Название
              <input name="name" value={formState.name} onChange={handleChange} required disabled={!canManageHosts} />
            </label>
            <label>
              Hostname/IP
              <input name="hostname" value={formState.hostname} onChange={handleChange} required disabled={!canManageHosts} />
            </label>
            <label>
              Порт
              <input name="port" type="number" value={formState.port} onChange={handleChange} min={1} max={65535} disabled={!canManageHosts} />
            </label>
            <label>
              Пользователь
              <input name="username" value={formState.username} onChange={handleChange} disabled={!canManageHosts} />
            </label>
            <label>
              OS
              <input name="os_type" value={formState.os_type} onChange={handleChange} disabled={!canManageHosts} />
            </label>
            <label>
              Среда
              <select name="environment" value={formState.environment} onChange={handleChange} disabled={!canManageHosts}>
                <option value="prod">prod</option>
                <option value="stage">stage</option>
                <option value="dev">dev</option>
              </select>
            </label>
            <label>
              Теги (key=value, ...)
              <input name="tags" value={formState.tags} onChange={handleChange} disabled={!canManageHosts} />
            </label>
            <label>
              Credential (из Secrets)
              <select name="credential_id" value={formState.credential_id} onChange={handleChange} disabled={!canManageHosts}>
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
              <select name="check_method" value={formState.check_method ?? "tcp"} onChange={handleChange} disabled={!canManageHosts}>
                <option value="tcp">tcp</option>
                <option value="ping">ping</option>
                <option value="ssh">ssh</option>
              </select>
              <span className="form-helper">ping требует `iputils-ping` в backend; ssh использует credential (password/private_key).</span>
            </label>
            <div className="form-actions">
              <button className="primary-button" type="submit" disabled={!canManageHosts}>
                Сохранить
              </button>
              {formMode === "edit" && (
                <button type="button" className="ghost-button" onClick={handleResetForm}>
                  Отменить
                </button>
              )}
            </div>
            {error && <span className="text-error form-error">{error}</span>}
          </form>
          <p className="form-helper">
            Изменения отправляются на backend; для действительных ответов предварительно выполните `POST /api/v1/auth/login`.
          </p>
        </div>
        )}
        {terminalHost && showTerminal && (
          <div className={`modal-overlay ${terminalFull ? "full" : ""}`}>
            <div className={`modal ${terminalFull ? "full" : ""}`}>
              <div className="modal-header">
                <div>
                  <h2>Терминал: {terminalHost.name}</h2>
                  <p className="form-helper">
                    {terminalHost.hostname}:{terminalHost.port} — {terminalHost.status}
                  </p>
                </div>
                <div className="row-actions">
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => {
                      const id = terminalHost.id;
                      window.open(`${window.location.origin}/#/terminal/${id}`, "_blank", "noopener,noreferrer");
                    }}
                    title="Открыть терминал в отдельном окне/вкладке"
                  >
                    В окне
                  </button>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => setTerminalFull((prev) => !prev)}
                  >
                    {terminalFull ? "Окно" : "На весь экран"}
                  </button>
                  <button
                    className="ghost-button"
                    type="button"
                    onClick={() => {
                      setShowTerminal(false);
                      setTerminalFull(false);
                    }}
                  >
                    Закрыть
                  </button>
                </div>
              </div>
              <TerminalPane
                hostId={terminalHost.id}
                token={token}
                disabled={terminalHost.status === "offline" || status !== "authenticated"}
                height={terminalFull ? 600 : 360}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default HostsPage;
