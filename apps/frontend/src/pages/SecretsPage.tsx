import { FormEvent, useEffect, useMemo, useState } from "react";

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
  created_at: string;
};

type SecretFormState = {
  name: string;
  type: SecretType;
  scope: SecretScope;
  description: string;
  tags: string;
  value: string;
  passphrase: string;
};

const defaultForm: SecretFormState = {
  name: "",
  type: "password",
  scope: "project",
  description: "",
  tags: "",
  value: "",
  passphrase: "",
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

  useEffect(() => {
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
      value: "",
      passphrase: "",
    });
    setRevealValue(null);
  };

  const handleReset = () => {
    setEditId(null);
    setForm({ ...defaultForm });
    setError(null);
    setRevealValue(null);
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

      {error && <p className="text-error">{error}</p>}
      <div className="grid">
        <div className="panel">
          <div className="panel-title">
            <h2>Список секретов</h2>
            <p>Значения не отображаются. Reveal доступен только admin.</p>
          </div>
          {loading && <p>Загружаем...</p>}
          {!loading && secrets.length === 0 && <p>Секретов пока нет</p>}
          {secrets.length > 0 && (
            <div className="table-scroll">
              <table className="hosts-table">
                <thead>
                  <tr>
                    <th>Название</th>
                    <th>Тип</th>
                    <th>Scope</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {secrets.map((secret) => (
                    <tr key={secret.id}>
                      <td>{secret.name}</td>
                      <td>{secret.type}</td>
                      <td>{scopeLabel(secret)}</td>
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
        </div>

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
            <button className="primary-button" type="submit" disabled={!isAdmin}>
              {editId ? "Сохранить" : "Создать"}
            </button>
            {editId && (
              <button className="ghost-button" type="button" onClick={handleReset}>
                Отменить
              </button>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}

export default SecretsPage;
