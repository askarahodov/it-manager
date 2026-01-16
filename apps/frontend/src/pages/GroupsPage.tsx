import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useConfirm } from "../components/ui/ConfirmProvider";
import { useToast } from "../components/ui/ToastProvider";
import EmptyState from "../components/ui/EmptyState";
import { formatError } from "../lib/errors";

type GroupType = "static" | "dynamic";

type Group = {
  id: number;
  name: string;
  type: GroupType;
  description?: string | null;
  rule?: Record<string, unknown> | null;
};

type Host = {
  id: number;
  name: string;
  hostname: string;
  environment: string;
  os_type: string;
  status: "online" | "offline" | "unknown";
};

type GroupFormState = {
  name: string;
  type: GroupType;
  description: string;
  ruleText: string;
  hostIds: number[];
};

const defaultRuleExample = JSON.stringify(
  {
    op: "and",
    rules: [
      { field: "environment", op: "eq", value: "prod" },
      { field: "os_type", op: "eq", value: "linux" },
      { field: "tags.env", op: "eq", value: "prod" },
    ],
  },
  null,
  2
);

const defaultForm: GroupFormState = {
  name: "",
  type: "static",
  description: "",
  ruleText: defaultRuleExample,
  hostIds: [],
};

function GroupsPage() {
  const { token, user, status } = useAuth();
  const { confirm } = useConfirm();
  const { pushToast } = useToast();
  const [groups, setGroups] = useState<Group[]>([]);
  const [hosts, setHosts] = useState<Host[]>([]);
  const [selected, setSelected] = useState<Group | null>(null);
  const [groupHosts, setGroupHosts] = useState<Host[]>([]);
  const [form, setForm] = useState<GroupFormState>(defaultForm);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hostFilter, setHostFilter] = useState<string>("");
  const [groupSearch, setGroupSearch] = useState("");
  const [groupPage, setGroupPage] = useState(1);
  const [groupPageSize, setGroupPageSize] = useState(25);
  const [selectedGroupIds, setSelectedGroupIds] = useState<Set<number>>(new Set());

  const canManageGroups = user?.role === "admin" || user?.role === "operator";

  const ruleJsonError = useMemo(() => {
    if (form.type !== "dynamic") return null;
    try {
      JSON.parse(form.ruleText || "{}");
      return null;
    } catch {
      return "Некорректный JSON в правиле (rule).";
    }
  }, [form.ruleText, form.type]);

  const dynamicHint = useMemo(
    () =>
      "Формат rules: { op: 'and'|'or', rules: [ {field, op, value}, ... ] }. Поля: name, hostname, environment, os_type, username, port, tags.<key>. Операторы: eq, neq, contains, in.",
    []
  );

  const totalPages = (items: number, pageSize: number) => Math.max(1, Math.ceil(items / pageSize));

  const filteredGroups = useMemo(() => {
    const query = groupSearch.trim().toLowerCase();
    if (!query) return groups;
    return groups.filter((group) => {
      const desc = group.description ?? "";
      return (
        group.name.toLowerCase().includes(query) ||
        group.type.toLowerCase().includes(query) ||
        desc.toLowerCase().includes(query)
      );
    });
  }, [groups, groupSearch]);

  const groupTotalPages = useMemo(() => totalPages(filteredGroups.length, groupPageSize), [filteredGroups.length, groupPageSize]);

  useEffect(() => {
    setGroupPage(1);
    setSelectedGroupIds(new Set());
  }, [groupSearch, groupPageSize, groups.length]);

  useEffect(() => {
    if (groupPage > groupTotalPages) {
      setGroupPage(groupTotalPages);
    }
  }, [groupPage, groupTotalPages]);

  const groupPageItems = useMemo(() => {
    const start = (groupPage - 1) * groupPageSize;
    return filteredGroups.slice(start, start + groupPageSize);
  }, [filteredGroups, groupPage, groupPageSize]);

  const loadAll = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [groupsData, hostsData] = await Promise.all([
        apiFetch<Group[]>("/api/v1/groups/", { token }),
        apiFetch<Host[]>("/api/v1/hosts/", { token }),
      ]);
      setGroups(groupsData);
      setHosts(hostsData);
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Не удалось загрузить данные", description: msg, variant: "error" });
    } finally {
      setLoading(false);
    }
  }, [token, pushToast]);

  useEffect(() => {
    if (!token) return;
    loadAll().catch(() => undefined);
  }, [token, loadAll]);

  useEffect(() => {
    if (!token) return;
    const onProjectChange = () => {
      loadAll().catch(() => undefined);
    };
    window.addEventListener("itmgr:project-change", onProjectChange);
    return () => window.removeEventListener("itmgr:project-change", onProjectChange);
  }, [token, loadAll]);

  const loadGroupHosts = async (groupId: number): Promise<Host[]> => {
    if (!token) return [];
    setError(null);
    try {
      const data = await apiFetch<Host[]>(`/api/v1/groups/${groupId}/hosts`, { token });
      setGroupHosts(data);
      return data;
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Не удалось загрузить состав группы", description: msg, variant: "error" });
      setGroupHosts([]);
      return [];
    }
  };

  const startCreate = () => {
    setSelected(null);
    setGroupHosts([]);
    setForm({ ...defaultForm });
    setError(null);
    setHostFilter("");
  };

  const startEdit = async (group: Group) => {
    setSelected(group);
    setError(null);
    setHostFilter("");
    setForm({
      name: group.name,
      type: group.type,
      description: group.description ?? "",
      ruleText: group.rule ? JSON.stringify(group.rule, null, 2) : defaultRuleExample,
      hostIds: [],
    });
    const members = await loadGroupHosts(group.id);
    if (group.type === "static") {
      setForm((prev) => ({ ...prev, hostIds: members.map((h) => h.id) }));
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!token) return;
    if (!canManageGroups) {
      setError("Требуются права admin для изменений.");
      return;
    }
    if (ruleJsonError) {
      setError(ruleJsonError);
      pushToast({ title: "Ошибка валидации", description: ruleJsonError, variant: "error" });
      return;
    }

    try {
      const payload: Record<string, unknown> = {
        name: form.name,
        type: form.type,
        description: form.description || null,
      };

      if (form.type === "dynamic") {
        payload.rule = JSON.parse(form.ruleText || "{}");
      } else {
        payload.host_ids = form.hostIds;
      }

      if (selected) {
        const updated = await apiFetch<Group>(`/api/v1/groups/${selected.id}`, {
          method: "PUT",
          token,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        setGroups((prev) => prev.map((g) => (g.id === updated.id ? updated : g)));
        setSelected(updated);
        await loadGroupHosts(updated.id);
        pushToast({ title: "Группа обновлена", description: updated.name, variant: "success" });
      } else {
        const created = await apiFetch<Group>("/api/v1/groups/", {
          method: "POST",
          token,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        setGroups((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
        setSelected(created);
        await loadGroupHosts(created.id);
        pushToast({ title: "Группа создана", description: created.name, variant: "success" });
      }
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка сохранения группы", description: msg, variant: "error" });
    }
  };

  const handleDelete = async () => {
    if (!token || !selected) return;
    if (!canManageGroups) {
      setError("Требуются права admin для удаления.");
      return;
    }
    const ok = await confirm({
      title: "Удалить группу?",
      description: `Будет удалена группа "${selected.name}".`,
      confirmText: "Удалить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!ok) return;
    setError(null);
    try {
      await apiFetch<void>(`/api/v1/groups/${selected.id}`, { method: "DELETE", token });
      setGroups((prev) => prev.filter((g) => g.id !== selected.id));
      startCreate();
      pushToast({ title: "Группа удалена", description: selected.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка удаления группы", description: msg, variant: "error" });
    }
  };

  const toggleGroupSelection = (groupId: number) => {
    setSelectedGroupIds((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      return next;
    });
  };

  const toggleAllGroupsOnPage = (checked: boolean) => {
    setSelectedGroupIds((prev) => {
      const next = new Set(prev);
      groupPageItems.forEach((group) => {
        if (checked) {
          next.add(group.id);
        } else {
          next.delete(group.id);
        }
      });
      return next;
    });
  };

  const bulkDeleteGroups = async () => {
    if (!token || !canManageGroups) return;
    const selectedGroups = groups.filter((group) => selectedGroupIds.has(group.id));
    if (selectedGroups.length === 0) {
      pushToast({ title: "Нет выбранных групп", description: "Выберите хотя бы одну группу.", variant: "warning" });
      return;
    }
    const ok = await confirm({
      title: "Удалить группы?",
      description: `Будут удалены ${selectedGroups.length} групп.`,
      confirmText: "Удалить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!ok) return;
    let failed = 0;
    for (const group of selectedGroups) {
      try {
        await apiFetch<void>(`/api/v1/groups/${group.id}`, { method: "DELETE", token });
      } catch {
        failed += 1;
      }
    }
    if (selected && selectedGroupIds.has(selected.id)) {
      startCreate();
    }
    setSelectedGroupIds(new Set());
    loadAll().catch(() => undefined);
    if (failed > 0) {
      pushToast({ title: "Часть групп не удалена", description: `Ошибок: ${failed}`, variant: "warning" });
      return;
    }
    pushToast({ title: "Группы удалены", description: `Удалено: ${selectedGroups.length}`, variant: "success" });
  };

  const handleRecompute = async () => {
    if (!token || !selected) return;
    if (!canManageGroups) {
      setError("Требуются права admin для пересчёта.");
      return;
    }
    setError(null);
    try {
      await apiFetch<void>(`/api/v1/groups/${selected.id}/recompute-dynamic`, { method: "POST", token });
      await loadGroupHosts(selected.id);
      pushToast({ title: "Пересчёт выполнен", description: selected.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка пересчёта", description: msg, variant: "error" });
    }
  };

  if (!token || status === "anonymous") {
    return (
      <div className="page-content">
        <header className="page-header">
          <div>
            <p className="page-kicker">Инвентаризация</p>
            <h1>Группы</h1>
          </div>
        </header>
        <div className="panel">
          <p>Для работы с группами нужно войти в Settings.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <p className="page-kicker">Инвентаризация</p>
          <h1>Группы</h1>
        </div>
        <div className="row-actions">
          <button type="button" className="ghost-button" onClick={startCreate}>
            Новая группа
          </button>
          <button type="button" className="ghost-button" onClick={loadAll}>
            Обновить
          </button>
          <a
            className="help-link"
            href="/docs/user-guide.html#groups"
            target="_blank"
            rel="noreferrer"
            aria-label="Справка по Groups"
            title="Справка по Groups"
          >
            ?
          </a>
        </div>
      </header>
      <div className="section-nav">
        <a href="#groups-list">Список</a>
        <a href="#groups-form">Форма</a>
      </div>

      {error && <p className="text-error">{error}</p>}
      <div className="grid">
        <div className="panel section-anchor" id="groups-list">
          <div className="panel-title">
            <h2>Список групп</h2>
            <p className="form-helper">Выберите группы для массовых действий или откройте редактирование через кнопку.</p>
          </div>
          <div className="table-toolbar">
            <div className="toolbar">
              <input
                value={groupSearch}
                onChange={(e) => setGroupSearch(e.target.value)}
                placeholder="Поиск: имя/описание/тип"
                aria-label="Поиск по группам"
              />
              <select value={groupPageSize} onChange={(e) => setGroupPageSize(Number(e.target.value))}>
                <option value={10}>10 / стр</option>
                <option value={25}>25 / стр</option>
                <option value={50}>50 / стр</option>
                <option value={100}>100 / стр</option>
              </select>
              <span className="form-helper">Найдено: {filteredGroups.length}</span>
            </div>
            <div className="toolbar">
              <button type="button" className="ghost-button" onClick={bulkDeleteGroups} disabled={!canManageGroups}>
                Удалить выбранные
              </button>
              <span className="form-helper">Выбрано: {selectedGroupIds.size}</span>
              <button type="button" className="ghost-button" onClick={() => setGroupPage((p) => Math.max(1, p - 1))} disabled={groupPage <= 1}>
                Назад
              </button>
              <span className="form-helper">
                Стр. {groupPage} / {groupTotalPages}
              </span>
              <button
                type="button"
                className="ghost-button"
                onClick={() => setGroupPage((p) => Math.min(groupTotalPages, p + 1))}
                disabled={groupPage >= groupTotalPages}
              >
                Далее
              </button>
            </div>
          </div>
          {loading && <p>Загружаем...</p>}
          {!loading && groups.length === 0 && (
            <EmptyState
              title="Групп пока нет"
              description="Создайте первую группу, чтобы управлять хостами по логике."
              actionLabel="Создать группу"
              onAction={() => {
                setSelected(null);
                setForm(defaultForm);
                setHostFilter("");
              }}
            />
          )}
          {!loading && groups.length > 0 && filteredGroups.length === 0 && (
            <p className="form-helper">По текущему фильтру групп не найдено.</p>
          )}
          {groupPageItems.length > 0 && (
            <div className="table-scroll">
              <table className="hosts-table">
                <thead>
                  <tr>
                    <th style={{ width: 40 }}>
                      <input
                        type="checkbox"
                        aria-label="Выбрать все группы на странице"
                        checked={groupPageItems.length > 0 && groupPageItems.every((group) => selectedGroupIds.has(group.id))}
                        onChange={(e) => toggleAllGroupsOnPage(e.target.checked)}
                      />
                    </th>
                    <th>Название</th>
                    <th>Тип</th>
                    <th>Описание</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {groupPageItems.map((group) => (
                    <tr key={group.id} onClick={() => toggleGroupSelection(group.id)}>
                      <td onClick={(event) => event.stopPropagation()}>
                        <input
                          type="checkbox"
                          aria-label={`Выбрать группу ${group.name}`}
                          checked={selectedGroupIds.has(group.id)}
                          onChange={() => toggleGroupSelection(group.id)}
                        />
                      </td>
                      <td>{group.name}</td>
                      <td>{group.type}</td>
                      <td>{group.description ?? ""}</td>
                      <td>
                        <div className="row-actions compact">
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={(event) => {
                              event.stopPropagation();
                              startEdit(group);
                            }}
                          >
                            Редактировать
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

        <div className="panel section-anchor" id="groups-form">
          <div className="panel-title">
            <h2>{selected ? `Группа: ${selected.name}` : "Создать группу"}</h2>
            <p className="form-helper">
              {selected ? `ID: ${selected.id}` : "Заполните форму и сохраните."}
            </p>
          </div>

          <form className="form-stack" onSubmit={handleSubmit}>
            <label>
              Название
              <input
                value={form.name}
                onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                minLength={2}
                required
              />
            </label>
            <label>
              Тип
              <select
                value={form.type}
                onChange={(e) => setForm((prev) => ({ ...prev, type: e.target.value as GroupType }))}
                disabled={Boolean(selected)}
              >
                <option value="static">static</option>
                <option value="dynamic">dynamic</option>
              </select>
            </label>
            <label>
              Описание
              <input
                value={form.description}
                onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
                placeholder="Опционально"
              />
            </label>

            {form.type === "static" && (
              <label>
                Хосты в группе
                <input
                  value={hostFilter}
                  onChange={(e) => setHostFilter(e.target.value)}
                  placeholder="Фильтр: имя или hostname"
                />
                <select
                  multiple
                  value={form.hostIds.map(String)}
                  onChange={(e) => {
                    const values = Array.from(e.target.selectedOptions).map((opt) => Number(opt.value));
                    setForm((prev) => ({ ...prev, hostIds: values }));
                  }}
                  className="multi-select"
                >
                  {hosts
                    .filter((host) => {
                      const query = hostFilter.trim().toLowerCase();
                      if (!query) return true;
                      return (
                        host.name.toLowerCase().includes(query) || host.hostname.toLowerCase().includes(query)
                      );
                    })
                    .map((host) => (
                      <option key={host.id} value={host.id}>
                        {host.name} ({host.hostname}) [{host.environment}/{host.os_type}]
                      </option>
                    ))}
                </select>
                <span className="form-helper">Можно выбрать несколько (Ctrl/Shift).</span>
              </label>
            )}

            {form.type === "dynamic" && (
              <label>
                Правило (JSON)
                <textarea
                  value={form.ruleText}
                  onChange={(e) => setForm((prev) => ({ ...prev, ruleText: e.target.value }))}
                  rows={10}
                  style={{ resize: "vertical" }}
                />
                <span className="form-helper">{dynamicHint}</span>
                {ruleJsonError && <span className="text-error">{ruleJsonError}</span>}
              </label>
            )}

            <div className="form-actions">
              <button type="submit" className="primary-button" disabled={!canManageGroups || Boolean(ruleJsonError)}>
                Сохранить
              </button>
              {selected && (
                <>
                  <button type="button" className="ghost-button" onClick={handleDelete} disabled={!canManageGroups}>
                    Удалить
                  </button>
                  {selected.type === "dynamic" && (
                    <button type="button" className="ghost-button" onClick={handleRecompute} disabled={!canManageGroups}>
                      Пересчитать
                    </button>
                  )}
                </>
              )}
            </div>
            {!canManageGroups && <p className="form-helper">Изменения доступны только пользователю с ролью admin/operator.</p>}
          </form>

          {selected && (
            <div className="stack">
              <div className="panel-title">
                <h2>Состав группы</h2>
                <p className="form-helper">
                  {selected.type === "dynamic"
                    ? "Для dynamic групп состав может обновляться воркером и по кнопке «Пересчитать»."
                    : "Для static групп состав задаётся вручную."}
                </p>
              </div>
              {groupHosts.length === 0 && <p>Хостов нет</p>}
              {groupHosts.length > 0 && (
                <div className="table-scroll">
                  <table className="hosts-table">
                    <thead>
                      <tr>
                        <th>Хост</th>
                        <th>Адрес</th>
                        <th>ENV/OS</th>
                        <th>Статус</th>
                      </tr>
                    </thead>
                    <tbody>
                      {groupHosts.map((h) => (
                        <tr key={h.id}>
                          <td>{h.name}</td>
                          <td>{h.hostname}</td>
                          <td>
                            {h.environment}/{h.os_type}
                          </td>
                          <td>{h.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default GroupsPage;
