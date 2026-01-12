import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useConfirm } from "../components/ui/ConfirmProvider";
import { useToast } from "../components/ui/ToastProvider";
import { formatError } from "../lib/errors";

type SecretType = "text" | "password" | "token" | "private_key";
type SecretScope = "project" | "global";

type Secret = {
  id: number;
  project_id: number | null;
  name: string;
  type: SecretType;
  scope: SecretScope;
  description?: string | null;
  tags: Record<string, string>;
  expires_at?: string | null;
  rotation_interval_days?: number | null;
  dynamic_enabled?: boolean;
  dynamic_ttl_seconds?: number | null;
  last_rotated_at?: string | null;
  next_rotated_at?: string | null;
  created_at: string;
};

type SecretFormState = {
  name: string;
  type: SecretType;
  scope: SecretScope;
  description: string;
  tags: string;
  expires_at: string;
  rotation_interval_days: string;
  dynamic_enabled: boolean;
  dynamic_ttl_seconds: string;
  value: string;
  passphrase: string;
};

const defaultForm: SecretFormState = {
  name: "",
  type: "password",
  scope: "project",
  description: "",
  tags: "",
  expires_at: "",
  rotation_interval_days: "",
  dynamic_enabled: false,
  dynamic_ttl_seconds: "",
  value: "",
  passphrase: "",
};

function toInputDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}

function toIsoDate(value: string) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

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

function SecretsPage() {
  const { token, user, status } = useAuth();
  const { confirm } = useConfirm();
  const { pushToast } = useToast();
  const [secrets, setSecrets] = useState<Secret[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<SecretFormState>(defaultForm);
  const [revealValue, setRevealValue] = useState<string | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [rotateId, setRotateId] = useState<number | null>(null);
  const [rotateTarget, setRotateTarget] = useState<Secret | null>(null);
  const [rotateValue, setRotateValue] = useState("");
  const [rotatePassphrase, setRotatePassphrase] = useState("");
  const [rotateApply, setRotateApply] = useState(false);
  const [secretsTab, setSecretsTab] = useState<"list" | "manage">("list");
  const [leaseValue, setLeaseValue] = useState<string | null>(null);
  const [leaseExpiresAt, setLeaseExpiresAt] = useState<string | null>(null);
  const [leaseSecretName, setLeaseSecretName] = useState<string | null>(null);

  const isAdmin = user?.role === "admin";
  const canReveal = isAdmin;
  const scopeLabel = (secret: Secret) => (secret.project_id == null ? "global" : "project");

  const stats = useMemo(() => {
    const summary: Record<SecretType, number> = { text: 0, password: 0, token: 0, private_key: 0 };
    secrets.forEach((secret) => {
      summary[secret.type] += 1;
    });
    return summary;
  }, [secrets]);

  const loadSecrets = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    apiFetch<Secret[]>("/api/v1/secrets/", { token })
      .then(setSecrets)
      .catch((err) => {
        const msg = formatError(err);
        setError(msg);
        pushToast({ title: "Не удалось загрузить секреты", description: msg, variant: "error" });
      })
      .finally(() => setLoading(false));
  }, [token, pushToast]);

  useEffect(() => {
    loadSecrets().catch(() => undefined);
  }, [loadSecrets]);

  useEffect(() => {
    if (!token) return;
    const onProjectChange = () => {
      loadSecrets().catch(() => undefined);
    };
    window.addEventListener("itmgr:project-change", onProjectChange);
    return () => window.removeEventListener("itmgr:project-change", onProjectChange);
  }, [token, loadSecrets]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (!token) return;
    if (!isAdmin) {
      const msg = "Требуются права admin для создания/редактирования секретов.";
      setError(msg);
      pushToast({ title: "Недостаточно прав", description: msg, variant: "warning" });
      return;
    }

    try {
      const url = editId ? `/api/v1/secrets/${editId}` : "/api/v1/secrets/";
      const method = editId ? "PUT" : "POST";
      const payload: Record<string, unknown> = {
        name: form.name,
        type: form.type,
        scope: form.scope,
        description: form.description || null,
        tags: parseTags(form.tags),
      };
      if (form.expires_at) {
        payload.expires_at = toIsoDate(form.expires_at);
      } else {
        payload.expires_at = null;
      }
      if (form.rotation_interval_days) {
        payload.rotation_interval_days = Number(form.rotation_interval_days);
      } else {
        payload.rotation_interval_days = null;
      }
      payload.dynamic_enabled = Boolean(form.dynamic_enabled);
      if (form.dynamic_enabled && form.dynamic_ttl_seconds) {
        payload.dynamic_ttl_seconds = Number(form.dynamic_ttl_seconds);
      } else {
        payload.dynamic_ttl_seconds = null;
      }
      if (form.value) {
        payload.value = form.value;
      }
      if (form.passphrase) {
        payload.passphrase = form.passphrase;
      }
      const saved = await apiFetch<Secret>(url, {
        method,
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSecrets((prev) => {
        if (editId) {
          return prev.map((s) => (s.id === saved.id ? saved : s));
        }
        return [...prev, saved];
      });
      setForm({ ...defaultForm });
      setEditId(null);
      setRevealValue(null);
      pushToast({ title: editId ? "Секрет обновлён" : "Секрет создан", description: saved.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка сохранения секрета", description: msg, variant: "error" });
    }
  };

  const handleReveal = async (secret: Secret) => {
    setRevealValue(null);
    setError(null);
    if (!token) return;
    try {
      const response = await apiFetch<{ value: string }>(`/api/v1/secrets/${secret.id}/reveal`, {
        method: "POST",
        token,
      });
      setRevealValue(response.value);
      pushToast({ title: "Секрет раскрыт", description: secret.name, variant: "warning", durationMs: 7000 });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка раскрытия секрета", description: msg, variant: "error" });
    }
  };

  const handleDelete = async (secret: Secret) => {
    setError(null);
    if (!token) return;
    if (!isAdmin) {
      const msg = "Требуются права admin для удаления секретов.";
      setError(msg);
      pushToast({ title: "Недостаточно прав", description: msg, variant: "warning" });
      return;
    }
    const ok = await confirm({
      title: "Удалить секрет?",
      description: `Будет удалён секрет "${secret.name}". Это действие необратимо.`,
      confirmText: "Удалить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!ok) return;
    try {
      await apiFetch<void>(`/api/v1/secrets/${secret.id}`, { method: "DELETE", token });
      setSecrets((prev) => prev.filter((item) => item.id !== secret.id));
      setRevealValue(null);
      pushToast({ title: "Секрет удалён", description: secret.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка удаления секрета", description: msg, variant: "error" });
    }
  };

  const handleEdit = (secret: Secret) => {
    setEditId(secret.id);
    setForm({
      name: secret.name,
      type: secret.type,
      scope: scopeLabel(secret),
      description: secret.description ?? "",
      tags: Object.entries(secret.tags)
        .map(([k, v]) => `${k}=${v}`)
        .join(", "),
      expires_at: toInputDate(secret.expires_at),
      rotation_interval_days: secret.rotation_interval_days ? String(secret.rotation_interval_days) : "",
      dynamic_enabled: Boolean(secret.dynamic_enabled),
      dynamic_ttl_seconds: secret.dynamic_ttl_seconds ? String(secret.dynamic_ttl_seconds) : "",
      value: "",
      passphrase: "",
    });
    setRevealValue(null);
    setSecretsTab("manage");
  };

  const handleReset = () => {
    setEditId(null);
    setForm({ ...defaultForm });
    setError(null);
    setRevealValue(null);
    setLeaseValue(null);
    setLeaseExpiresAt(null);
    setLeaseSecretName(null);
    setSecretsTab("list");
  };

  const startRotate = (secret: Secret) => {
    setRotateId(secret.id);
    setRotateTarget(secret);
    setRotateValue("");
    setRotatePassphrase("");
    setRotateApply(secret.type === "password");
  };

  const performRotate = async () => {
    if (!token || !rotateId) return;
    if (!rotateValue) {
      const msg = "Введите новое значение для ротации.";
      setError(msg);
      pushToast({ title: "Ошибка ротации", description: msg, variant: "error" });
      return;
    }
    try {
      const payload: Record<string, unknown> = { value: rotateValue };
      if (rotatePassphrase) payload.passphrase = rotatePassphrase;
      if (rotateApply && rotateTarget?.type === "password") {
        const run = await apiFetch<{ id: number }>(`/api/v1/secrets/${rotateId}/rotate-apply`, {
          method: "POST",
          token,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        setRotateId(null);
        setRotateTarget(null);
        setRotateApply(false);
        setRotateValue("");
        setRotatePassphrase("");
        pushToast({
          title: "Ротация запущена",
          description: `Run #${run.id} создан для применения на хосты`,
          variant: "success",
        });
        return;
      }
      const rotated = await apiFetch<Secret>(`/api/v1/secrets/${rotateId}/rotate`, {
        method: "POST",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSecrets((prev) => prev.map((s) => (s.id === rotated.id ? rotated : s)));
      setRotateId(null);
      setRotateTarget(null);
      setRotateApply(false);
      setRotateValue("");
      setRotatePassphrase("");
      pushToast({ title: "Секрет ротирован", description: rotated.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка ротации", description: msg, variant: "error" });
    }
  };

  const issueLease = async (secret: Secret) => {
    if (!token) return;
    if (!secret.dynamic_enabled) {
      pushToast({ title: "Dynamic secrets отключены", description: secret.name, variant: "warning" });
      return;
    }
    try {
      const lease = await apiFetch<{ value: string; expires_at: string }>(`/api/v1/secrets/${secret.id}/lease`, {
        method: "POST",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      setLeaseValue(lease.value);
      setLeaseExpiresAt(lease.expires_at);
      setLeaseSecretName(secret.name);
      pushToast({ title: "Lease создан", description: secret.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      pushToast({ title: "Ошибка lease", description: msg, variant: "error" });
    }
  };

  if (!token || status === "anonymous") {
    return (
      <div className="page-content">
        <header className="page-header">
          <div>
            <p className="page-kicker">Vault</p>
            <h1>Секреты</h1>
          </div>
        </header>
        <div className="panel">
          <p>Для просмотра секретов нужно войти в Settings.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <p className="page-kicker">Vault</p>
          <h1>Секреты</h1>
        </div>
        <div className="status-summary">
          {Object.entries(stats).map(([key, value]) => (
            <div key={key} className="status-pill mini unknown">
              {key}: {value}
            </div>
          ))}
        </div>
      </header>

      <div className="tabs">
        <button
          type="button"
          className={`tab-button ${secretsTab === "list" ? "active" : ""}`}
          onClick={() => setSecretsTab("list")}
        >
          Список
        </button>
        <button
          type="button"
          className={`tab-button ${secretsTab === "manage" ? "active" : ""}`}
          onClick={() => setSecretsTab("manage")}
        >
          {editId ? "Редактировать" : "Создать"}
        </button>
      </div>

      {error && <p className="text-error">{error}</p>}
      <div className="grid">
        {secretsTab === "list" && (
        <div className="panel">
          <div className="panel-title">
            <h2>Список секретов</h2>
            <p>Значения не отображаются. Reveal доступен только admin.</p>
          </div>
          {loading && <p>Загружаем...</p>}
          {!loading && secrets.length === 0 && <p>Секретов пока нет</p>}
          {loading && secrets.length === 0 && (
            <div className="table-scroll">
              <table className="hosts-table">
                <thead>
                  <tr>
                    <th>Название</th>
                    <th>Тип</th>
                    <th>Scope</th>
                    <th>Истекает</th>
                    <th>Ротация</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: 5 }).map((_, idx) => (
                    <tr key={`skeleton-secret-${idx}`}>
                      <td><span className="skeleton-line" /></td>
                      <td><span className="skeleton-line small" /></td>
                      <td><span className="skeleton-line small" /></td>
                      <td><span className="skeleton-line small" /></td>
                      <td><span className="skeleton-line small" /></td>
                      <td><span className="skeleton-line" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {secrets.length > 0 && (
            <div className="table-scroll">
              <table className="hosts-table">
                <thead>
                  <tr>
                    <th>Название</th>
                    <th>Тип</th>
                    <th>Scope</th>
                    <th>Истекает</th>
                    <th>Ротация</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {secrets.map((secret) => (
                    <tr key={secret.id}>
                      <td>{secret.name}</td>
                      <td>{secret.type}</td>
                      <td>{scopeLabel(secret)}</td>
                      <td>{secret.expires_at ? new Date(secret.expires_at).toLocaleDateString() : "—"}</td>
                      <td>{secret.next_rotated_at ? new Date(secret.next_rotated_at).toLocaleDateString() : "—"}</td>
                      <td>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={() => handleEdit(secret)}
                            disabled={!isAdmin}
                            title={isAdmin ? "Редактировать" : "Требуется роль admin"}
                          >
                            Редактировать
                          </button>
                          <button
                            type="button"
                            className="ghost-button"
                            disabled={!canReveal}
                            onClick={() => handleReveal(secret)}
                            title={canReveal ? "Раскрыть значение" : "Требуется роль admin"}
                          >
                            Раскрыть
                          </button>
                          <button
                            type="button"
                            className="ghost-button"
                            disabled={!isAdmin}
                            onClick={() => handleDelete(secret)}
                            title={isAdmin ? "Удалить" : "Требуется роль admin"}
                          >
                            Удалить
                          </button>
                          <button
                            type="button"
                            className="ghost-button"
                            disabled={!isAdmin}
                            onClick={() => startRotate(secret)}
                            title={isAdmin ? "Ротация секрета" : "Требуется роль admin"}
                          >
                            Ротация
                          </button>
                          <button
                            type="button"
                            className="ghost-button"
                            disabled={!isAdmin || !secret.dynamic_enabled}
                            onClick={() => issueLease(secret)}
                            title={secret.dynamic_enabled ? "Выдать lease" : "Dynamic secrets отключены"}
                          >
                            Lease
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {revealValue && (
            <div className="panel small reveal-panel">
              <h3>Значение</h3>
              <pre className="reveal-value">{revealValue}</pre>
              <p className="form-helper">Не вставляйте секреты в чаты. Закройте панель после использования.</p>
            </div>
          )}
          {leaseValue && (
            <div className="panel small reveal-panel">
              <h3>Lease: {leaseSecretName ?? "секрет"}</h3>
              <pre className="reveal-value">{leaseValue}</pre>
              <p className="form-helper">
                Истекает: {leaseExpiresAt ? new Date(leaseExpiresAt).toLocaleString() : "—"}
              </p>
            </div>
          )}
        </div>
        )}
        {secretsTab === "manage" && (
        <div className="panel">
            <div className="panel-title">
            <h2>{editId ? "Редактировать секрет" : "Создать секрет"}</h2>
            <p>Значение сохранится в зашифрованном виде (AES-GCM).</p>
            </div>
          {!isAdmin && <p className="form-helper">Режим read-only: создание/редактирование/удаление доступно только admin.</p>}
          <form className="form-stack" onSubmit={handleSubmit}>
            <label>
              Название
              <input value={form.name} onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))} required disabled={!isAdmin} />
            </label>
            <label>
              Тип
              <select value={form.type} onChange={(e) => setForm((prev) => ({ ...prev, type: e.target.value as SecretType }))} disabled={!isAdmin}>
                <option value="password">password</option>
                <option value="token">token</option>
                <option value="text">text</option>
                <option value="private_key">private_key</option>
              </select>
            </label>
            <label>
              Scope
              <select
                value={form.scope}
                onChange={(e) => setForm((prev) => ({ ...prev, scope: e.target.value as SecretScope }))}
                disabled={!isAdmin}
              >
                <option value="project">project</option>
                <option value="global">global</option>
              </select>
              <span className="form-helper">project — секрет виден только в текущем проекте; global — виден во всех проектах.</span>
            </label>
            <label>
              Описание
              <input value={form.description} onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))} disabled={!isAdmin} />
            </label>
            <label>
              Теги (key=value, ...)
              <input value={form.tags} onChange={(e) => setForm((prev) => ({ ...prev, tags: e.target.value }))} disabled={!isAdmin} />
            </label>
            <label>
              Истекает
              <input
                type="datetime-local"
                value={form.expires_at}
                onChange={(e) => setForm((prev) => ({ ...prev, expires_at: e.target.value }))}
                disabled={!isAdmin}
              />
              <span className="form-helper">Оставьте пустым, если срок не задан.</span>
            </label>
            <label>
              Интервал ротации (дней)
              <input
                type="number"
                min={1}
                value={form.rotation_interval_days}
                onChange={(e) => setForm((prev) => ({ ...prev, rotation_interval_days: e.target.value }))}
                disabled={!isAdmin}
              />
              <span className="form-helper">Если задан — планируется next rotation.</span>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.dynamic_enabled}
                onChange={(e) => setForm((prev) => ({ ...prev, dynamic_enabled: e.target.checked }))}
                disabled={!isAdmin}
              />
              <span>Dynamic secret (leases)</span>
            </label>
            {form.dynamic_enabled && (
              <label>
                TTL для lease (секунды)
                <input
                  type="number"
                  min={60}
                  value={form.dynamic_ttl_seconds}
                  onChange={(e) => setForm((prev) => ({ ...prev, dynamic_ttl_seconds: e.target.value }))}
                  disabled={!isAdmin}
                />
                <span className="form-helper">Если пусто — TTL не задан, lease не выдаётся.</span>
              </label>
            )}
          <label>
            Значение
            {form.type === "private_key" ? (
              <textarea
                value={form.value}
                onChange={(e) => setForm((prev) => ({ ...prev, value: e.target.value }))}
                rows={6}
                style={{ background: "#0f172a", color: "#e2e8f0", borderRadius: 8, padding: "0.65rem" }}
                disabled={!isAdmin}
              />
            ) : (
                <input value={form.value} onChange={(e) => setForm((prev) => ({ ...prev, value: e.target.value }))} disabled={!isAdmin} />
            )}
          </label>
          <p className="form-helper">
              При редактировании значение не показывается; оставьте поле пустым, чтобы не менять секрет.
          </p>
            {form.type === "private_key" && (
              <label>
                Passphrase (опционально)
                <input value={form.passphrase} onChange={(e) => setForm((prev) => ({ ...prev, passphrase: e.target.value }))} disabled={!isAdmin} />
              </label>
            )}
            {error && <span className="text-error form-error">{error}</span>}
            <button className="primary-button" type="submit" disabled={!isAdmin}>
              {editId ? "Сохранить" : "Создать"}
            </button>
            {editId && (
              <button className="ghost-button" type="button" onClick={handleReset}>
                Отменить
              </button>
            )}
          </form>
          {rotateId && (
            <div className="panel small">
              <h3>Ротация секрета</h3>
              <label>
                Новое значение
                <input value={rotateValue} onChange={(e) => setRotateValue(e.target.value)} disabled={!isAdmin} />
              </label>
              <label>
                Passphrase (если private_key)
                <input value={rotatePassphrase} onChange={(e) => setRotatePassphrase(e.target.value)} disabled={!isAdmin} />
              </label>
              {rotateTarget?.type === "password" && (
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={rotateApply}
                    onChange={(e) => setRotateApply(e.target.checked)}
                    disabled={!isAdmin}
                  />
                  <span>Применить ротацию на хостах, которые используют этот секрет</span>
                </label>
              )}
              <div className="row-actions">
                <button type="button" className="primary-button" onClick={performRotate} disabled={!isAdmin}>
                  Ротировать
                </button>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => {
                    setRotateId(null);
                    setRotateTarget(null);
                    setRotateApply(false);
                  }}
                >
                  Отмена
                </button>
              </div>
            </div>
          )}
        </div>
        )}
      </div>
    </div>
  );
}

export default SecretsPage;
