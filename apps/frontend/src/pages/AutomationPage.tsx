import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useConfirm } from "../components/ui/ConfirmProvider";
import { useToast } from "../components/ui/ToastProvider";
import { formatError } from "../lib/errors";
import { getProjectId } from "../lib/project";

type Playbook = {
  id: number;
  name: string;
  description?: string | null;
  stored_content?: string | null;
  variables: Record<string, unknown>;
  schedule?: {
    enabled: boolean;
    type: "interval" | "cron";
    value: string;
    host_ids: number[];
    group_ids: number[];
    extra_vars: Record<string, unknown>;
    dry_run: boolean;
    last_run_at?: string | null;
  } | null;
  created_at: string;
};

type Run = {
  id: number;
  playbook_id: number;
  triggered_by: string;
  status: "pending" | "running" | "success" | "failed";
  target_snapshot: Record<string, unknown>;
  logs: string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

type RunArtifact = { name: string; size: number; mtime: number };

type Host = {
  id: number;
  name: string;
  hostname: string;
  environment: string;
  os_type: string;
};

type Group = {
  id: number;
  name: string;
  type: "static" | "dynamic";
};

type PlaybookTemplate = {
  id: number;
  name: string;
  description?: string | null;
  vars_schema: Record<string, unknown>;
  vars_defaults: Record<string, unknown>;
  created_at: string;
};

const defaultPlaybookYaml = `---
- name: demo
  hosts: all
  gather_facts: false
  tasks:
    - name: ping
      ping:
`;

function AutomationPage() {
  const { token, user, status } = useAuth();
  const { confirm } = useConfirm();
  const { pushToast } = useToast();
  const isAdmin = user?.role === "admin";
  const canRun = user?.role === "admin" || user?.role === "operator" || user?.role === "automation-only";

  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [hosts, setHosts] = useState<Host[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [templates, setTemplates] = useState<PlaybookTemplate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [editPlaybookId, setEditPlaybookId] = useState<number | null>(null);
  const [pbName, setPbName] = useState("");
  const [pbDescription, setPbDescription] = useState("");
  const [pbYaml, setPbYaml] = useState(defaultPlaybookYaml);
  const [pbScheduleEnabled, setPbScheduleEnabled] = useState(false);
  const [pbScheduleType, setPbScheduleType] = useState<"interval" | "cron">("interval");
  const [pbScheduleValue, setPbScheduleValue] = useState("300");
  const [pbScheduleHostIds, setPbScheduleHostIds] = useState<number[]>([]);
  const [pbScheduleGroupIds, setPbScheduleGroupIds] = useState<number[]>([]);
  const [pbScheduleExtraVars, setPbScheduleExtraVars] = useState<string>("{}");
  const [pbScheduleDry, setPbScheduleDry] = useState(false);

  const [editTemplateId, setEditTemplateId] = useState<number | null>(null);
  const [tplName, setTplName] = useState("");
  const [tplDescription, setTplDescription] = useState("");
  const [tplSchema, setTplSchema] = useState<string>("{}");
  const [tplDefaults, setTplDefaults] = useState<string>("{}");

  const [runModal, setRunModal] = useState<{ open: boolean; playbook: Playbook | null }>({
    open: false,
    playbook: null,
  });
  const [runHostIds, setRunHostIds] = useState<number[]>([]);
  const [runGroupIds, setRunGroupIds] = useState<number[]>([]);
  const [runExtraVars, setRunExtraVars] = useState<string>("{}");
  const [runDry, setRunDry] = useState(false);

  const [logModal, setLogModal] = useState<{ open: boolean; run: Run | null }>({ open: false, run: null });
  const [liveLogs, setLiveLogs] = useState<string>("");
  const [artifacts, setArtifacts] = useState<RunArtifact[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runModal.open && !logModal.open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (logModal.open) {
        eventSourceRef.current?.close();
        setLogModal({ open: false, run: null });
        setLiveLogs("");
        return;
      }
      if (runModal.open) {
        setRunModal({ open: false, playbook: null });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [runModal.open, logModal.open]);

  const scheduleExtraVarsError = useMemo(() => {
    if (!pbScheduleEnabled) return null;
    try {
      JSON.parse(pbScheduleExtraVars || "{}");
      return null;
    } catch {
      return "Некорректный JSON в extra vars (расписание).";
    }
  }, [pbScheduleExtraVars, pbScheduleEnabled]);

  const runExtraVarsError = useMemo(() => {
    try {
      JSON.parse(runExtraVars || "{}");
      return null;
    } catch {
      return "Некорректный JSON в extra vars.";
    }
  }, [runExtraVars]);

  const templateSchemaError = useMemo(() => {
    try {
      JSON.parse(tplSchema || "{}");
      return null;
    } catch {
      return "Некорректный JSON в vars schema.";
    }
  }, [tplSchema]);

  const templateDefaultsError = useMemo(() => {
    try {
      JSON.parse(tplDefaults || "{}");
      return null;
    } catch {
      return "Некорректный JSON в vars defaults.";
    }
  }, [tplDefaults]);

  const templateJsonError = templateSchemaError || templateDefaultsError;

  const refreshAll = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [pb, rr, hh, gg, tt] = await Promise.all([
        apiFetch<Playbook[]>("/api/v1/playbooks/", { token }),
        apiFetch<Run[]>("/api/v1/runs/", { token }),
        apiFetch<Host[]>("/api/v1/hosts/", { token }),
        apiFetch<Group[]>("/api/v1/groups/", { token }),
        apiFetch<PlaybookTemplate[]>("/api/v1/playbook-templates/", { token }),
      ]);
      setPlaybooks(pb);
      setRuns(rr);
      setHosts(hh);
      setGroups(gg);
      setTemplates(tt);
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Не удалось загрузить данные", description: msg, variant: "error" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!token) return;
    refreshAll().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const resetPlaybookForm = () => {
    setEditPlaybookId(null);
    setPbName("");
    setPbDescription("");
    setPbYaml(defaultPlaybookYaml);
    setPbScheduleEnabled(false);
    setPbScheduleType("interval");
    setPbScheduleValue("300");
    setPbScheduleHostIds([]);
    setPbScheduleGroupIds([]);
    setPbScheduleExtraVars("{}");
    setPbScheduleDry(false);
  };

  const resetTemplateForm = () => {
    setEditTemplateId(null);
    setTplName("");
    setTplDescription("");
    setTplSchema("{}");
    setTplDefaults("{}");
  };

  const startEditTemplate = (tpl: PlaybookTemplate) => {
    setEditTemplateId(tpl.id);
    setTplName(tpl.name);
    setTplDescription(tpl.description ?? "");
    setTplSchema(JSON.stringify(tpl.vars_schema ?? {}, null, 2));
    setTplDefaults(JSON.stringify(tpl.vars_defaults ?? {}, null, 2));
  };

  const startEditPlaybook = (pb: Playbook) => {
    setEditPlaybookId(pb.id);
    setPbName(pb.name);
    setPbDescription(pb.description ?? "");
    setPbYaml(pb.stored_content ?? defaultPlaybookYaml);
    const schedule = pb.schedule ?? null;
    setPbScheduleEnabled(Boolean(schedule?.enabled));
    setPbScheduleType(schedule?.type ?? "interval");
    setPbScheduleValue(schedule?.value ?? "300");
    setPbScheduleHostIds(schedule?.host_ids ?? []);
    setPbScheduleGroupIds(schedule?.group_ids ?? []);
    setPbScheduleExtraVars(JSON.stringify(schedule?.extra_vars ?? {}, null, 2));
    setPbScheduleDry(Boolean(schedule?.dry_run));
  };

  const submitPlaybook = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!token) return;
    if (!isAdmin) {
      setError("Требуются права admin.");
      return;
    }
    if (scheduleExtraVarsError) {
      setError(scheduleExtraVarsError);
      pushToast({ title: "Ошибка валидации", description: scheduleExtraVarsError, variant: "error" });
      return;
    }

    try {
      const scheduleExtraVars = JSON.parse(pbScheduleExtraVars || "{}") as Record<string, unknown>;
      const payload = {
        name: pbName,
        description: pbDescription || null,
        stored_content: pbYaml,
        variables: {},
        inventory_scope: [],
        schedule: pbScheduleEnabled
          ? {
              enabled: true,
              type: pbScheduleType,
              value: pbScheduleValue,
              host_ids: pbScheduleHostIds,
              group_ids: pbScheduleGroupIds,
              extra_vars: scheduleExtraVars,
              dry_run: pbScheduleDry,
            }
          : { enabled: false, type: pbScheduleType, value: pbScheduleValue, host_ids: [], group_ids: [], extra_vars: {}, dry_run: false },
      };
      if (editPlaybookId) {
        const updated = await apiFetch<Playbook>(`/api/v1/playbooks/${editPlaybookId}`, {
          method: "PUT",
          token,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        setPlaybooks((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
        pushToast({ title: "Плейбук обновлён", description: updated.name, variant: "success" });
      } else {
        const created = await apiFetch<Playbook>("/api/v1/playbooks/", {
          method: "POST",
          token,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        setPlaybooks((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
        pushToast({ title: "Плейбук создан", description: created.name, variant: "success" });
      }
      resetPlaybookForm();
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка сохранения плейбука", description: msg, variant: "error" });
    }
  };

  const submitTemplate = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!token) return;
    if (!isAdmin) {
      setError("Требуются права admin.");
      return;
    }
    if (templateJsonError) {
      setError(templateJsonError);
      pushToast({ title: "Ошибка валидации", description: templateJsonError, variant: "error" });
      return;
    }
    try {
      const payload = {
        name: tplName,
        description: tplDescription || null,
        vars_schema: JSON.parse(tplSchema || "{}"),
        vars_defaults: JSON.parse(tplDefaults || "{}"),
      };
      const url = editTemplateId ? `/api/v1/playbook-templates/${editTemplateId}` : "/api/v1/playbook-templates/";
      const method = editTemplateId ? "PUT" : "POST";
      const saved = await apiFetch<PlaybookTemplate>(url, {
        method,
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setTemplates((prev) => {
        if (editTemplateId) {
          return prev.map((t) => (t.id === saved.id ? saved : t));
        }
        return [...prev, saved].sort((a, b) => a.name.localeCompare(b.name));
      });
      resetTemplateForm();
      pushToast({ title: editTemplateId ? "Шаблон обновлён" : "Шаблон создан", description: saved.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка сохранения шаблона", description: msg, variant: "error" });
    }
  };

  const deleteTemplate = async (tpl: PlaybookTemplate) => {
    if (!token) return;
    if (!isAdmin) return;
    const ok = await confirm({
      title: "Удалить шаблон?",
      description: `Будет удалён шаблон "${tpl.name}".`,
      confirmText: "Удалить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!ok) return;
    try {
      await apiFetch<void>(`/api/v1/playbook-templates/${tpl.id}`, { method: "DELETE", token });
      setTemplates((prev) => prev.filter((t) => t.id !== tpl.id));
      pushToast({ title: "Шаблон удалён", description: tpl.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      pushToast({ title: "Ошибка удаления шаблона", description: msg, variant: "error" });
    }
  };

  const deletePlaybook = async (pb: Playbook) => {
    if (!token) return;
    if (!isAdmin) {
      setError("Требуются права admin.");
      return;
    }
    const ok = await confirm({
      title: "Удалить плейбук?",
      description: `Будет удалён плейбук "${pb.name}".`,
      confirmText: "Удалить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!ok) return;
    setError(null);
    try {
      await apiFetch<void>(`/api/v1/playbooks/${pb.id}`, { method: "DELETE", token });
      setPlaybooks((prev) => prev.filter((p) => p.id !== pb.id));
      if (editPlaybookId === pb.id) resetPlaybookForm();
      pushToast({ title: "Плейбук удалён", description: pb.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка удаления плейбука", description: msg, variant: "error" });
    }
  };

  const openRunModal = (pb: Playbook) => {
    setRunModal({ open: true, playbook: pb });
    setRunHostIds([]);
    setRunGroupIds([]);
    setRunExtraVars("{}");
    setRunDry(false);
  };

  const submitRun = async () => {
    if (!token || !runModal.playbook) return;
    setError(null);
    if (!canRun) {
      const msg = "Недостаточно прав для запуска (нужна роль admin/operator/automation-only).";
      setError(msg);
      pushToast({ title: "Недостаточно прав", description: msg, variant: "warning" });
      return;
    }
    if (runExtraVarsError) {
      setError(runExtraVarsError);
      pushToast({ title: "Ошибка валидации", description: runExtraVarsError, variant: "error" });
      return;
    }
    try {
      const extra_vars = JSON.parse(runExtraVars || "{}");
      const run = await apiFetch<Run>(`/api/v1/playbooks/${runModal.playbook.id}/run`, {
        method: "POST",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          host_ids: runHostIds,
          group_ids: runGroupIds,
          extra_vars,
          dry_run: runDry,
        }),
      });
      setRuns((prev) => [run, ...prev]);
      setRunModal({ open: false, playbook: null });
      pushToast({ title: "Запуск создан", description: `Run #${run.id}`, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка запуска", description: msg, variant: "error" });
    }
  };

  const openLogs = async (run: Run) => {
    setLogModal({ open: true, run });
    setLiveLogs(run.logs || "");
    setArtifacts([]);
    if (token && isAdmin) {
      try {
        const list = await apiFetch<RunArtifact[]>(`/api/v1/runs/${run.id}/artifacts`, { token });
        setArtifacts(list);
      } catch (err) {
        const msg = formatError(err);
        pushToast({ title: "Не удалось получить артефакты", description: msg, variant: "warning" });
      }
    }
  };

  useEffect(() => {
    if (!logModal.open || !logModal.run || !token) return;
    eventSourceRef.current?.close();
    const projectId = getProjectId() ?? 1;
    const es = new EventSource(
      `/api/v1/runs/${logModal.run.id}/stream?token=${encodeURIComponent(token)}&project_id=${projectId}`
    );
    eventSourceRef.current = es;
    es.onmessage = (event) => {
      const text = (event.data as string).replaceAll("\\r", "\r").replaceAll("\\n", "\n");
      setLiveLogs((prev) => prev + text);
    };
    es.addEventListener("done", () => {
      es.close();
    });
    es.onerror = () => {
      // не спамим, просто закрываем; пользователь может открыть снова
      es.close();
      pushToast({ title: "Live-лог остановлен", description: "Поток SSE прерван", variant: "warning" });
    };
    return () => {
      es.close();
    };
  }, [logModal.open, logModal.run, token, pushToast]);

  const runsByPlaybook = useMemo(() => {
    const map = new Map<number, number>();
    runs.forEach((r) => map.set(r.playbook_id, (map.get(r.playbook_id) ?? 0) + 1));
    return map;
  }, [runs]);

  if (!token || status === "anonymous") {
    return (
      <div className="page-content">
        <header className="page-header">
          <div>
            <p className="page-kicker">Автоматизация</p>
            <h1>Плейбуки</h1>
          </div>
        </header>
        <div className="panel">
          <p>Для работы с автоматизацией нужно войти в Settings.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <p className="page-kicker">Автоматизация</p>
          <h1>Плейбуки и запуски</h1>
        </div>
        <div className="row-actions">
          <button type="button" className="ghost-button" onClick={refreshAll}>
            Обновить
          </button>
        </div>
      </header>

      {error && <p className="text-error">{error}</p>}
      {loading && <p>Загружаем...</p>}

      <div className="grid">
        <div className="panel">
          <div className="panel-title">
            <h2>Шаблоны плейбуков</h2>
            <p className="form-helper">Vars schema и defaults для будущих инстансов.</p>
          </div>
          {templates.length === 0 && <p>Шаблонов пока нет</p>}
          {templates.length > 0 && (
            <table className="hosts-table">
              <thead>
                <tr>
                  <th>Название</th>
                  <th>Описание</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {templates.map((tpl) => (
                  <tr key={tpl.id}>
                    <td>{tpl.name}</td>
                    <td>{tpl.description ?? ""}</td>
                    <td>
                      <div className="row-actions">
                        <button type="button" className="ghost-button" onClick={() => startEditTemplate(tpl)} disabled={!isAdmin}>
                          Редактировать
                        </button>
                        <button type="button" className="ghost-button" onClick={() => deleteTemplate(tpl)} disabled={!isAdmin}>
                          Удалить
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="panel">
          <div className="panel-title">
            <h2>{editTemplateId ? "Редактировать шаблон" : "Создать шаблон"}</h2>
            {!isAdmin && <p className="form-helper">Создание/редактирование доступно только admin.</p>}
          </div>
          <form className="form-stack" onSubmit={submitTemplate}>
            <label>
              Название
              <input value={tplName} onChange={(e) => setTplName(e.target.value)} required minLength={3} disabled={!isAdmin} />
            </label>
            <label>
              Описание
              <input value={tplDescription} onChange={(e) => setTplDescription(e.target.value)} placeholder="Опционально" disabled={!isAdmin} />
            </label>
            <label>
              Vars schema (JSON)
              <textarea value={tplSchema} onChange={(e) => setTplSchema(e.target.value)} rows={6} style={{ resize: "vertical" }} disabled={!isAdmin} />
              {templateSchemaError && <span className="text-error">{templateSchemaError}</span>}
            </label>
            <label>
              Vars defaults (JSON)
              <textarea value={tplDefaults} onChange={(e) => setTplDefaults(e.target.value)} rows={6} style={{ resize: "vertical" }} disabled={!isAdmin} />
              {templateDefaultsError && <span className="text-error">{templateDefaultsError}</span>}
            </label>
            <div className="form-actions">
              <button type="submit" className="primary-button" disabled={!isAdmin || Boolean(templateJsonError)}>
                Сохранить
              </button>
              <button type="button" className="ghost-button" onClick={resetTemplateForm}>
                Сброс
              </button>
            </div>
          </form>
        </div>
      </div>

      <div className="grid">
        <div className="panel">
          <div className="panel-title">
            <h2>Плейбуки</h2>
            <p className="form-helper">MVP: хранение как YAML (stored_content).</p>
          </div>
          {playbooks.length === 0 && <p>Плейбуков пока нет</p>}
          {playbooks.length > 0 && (
            <table className="hosts-table">
              <thead>
                <tr>
                  <th>Название</th>
                  <th>Описание</th>
                  <th>Запуски</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {playbooks.map((pb) => (
                  <tr key={pb.id}>
                    <td>{pb.name}</td>
                    <td>{pb.description ?? ""}</td>
                    <td>{runsByPlaybook.get(pb.id) ?? 0}</td>
                    <td>
                      <div className="row-actions">
                        <button type="button" className="ghost-button" onClick={() => startEditPlaybook(pb)} disabled={!isAdmin}>
                          Редактировать
                        </button>
                        <button type="button" className="ghost-button" onClick={() => openRunModal(pb)} disabled={!canRun}>
                          Запуск
                        </button>
                        <button type="button" className="ghost-button" disabled={!isAdmin} onClick={() => deletePlaybook(pb)}>
                          Удалить
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="panel">
          <div className="panel-title">
            <h2>{editPlaybookId ? "Редактировать плейбук" : "Создать плейбук"}</h2>
            {!isAdmin && <p className="form-helper">Создание/редактирование доступно только admin.</p>}
          </div>
          <form className="form-stack" onSubmit={submitPlaybook}>
            <label>
              Название
              <input value={pbName} onChange={(e) => setPbName(e.target.value)} required minLength={2} />
            </label>
            <label>
              Описание
              <input value={pbDescription} onChange={(e) => setPbDescription(e.target.value)} placeholder="Опционально" />
            </label>
            <label>
              YAML (playbook.yml)
              <textarea value={pbYaml} onChange={(e) => setPbYaml(e.target.value)} rows={14} style={{ resize: "vertical" }} />
            </label>
            <div className="panel" style={{ padding: "0.75rem" }}>
              <div className="panel-title">
                <h2>Расписание (MVP)</h2>
                <p className="form-helper">Хранится в плейбуке; выполняется воркером.</p>
              </div>
              <div className="form-stack" style={{ marginTop: 0 }}>
                <label>
                  Включено
                  <select value={pbScheduleEnabled ? "yes" : "no"} onChange={(e) => setPbScheduleEnabled(e.target.value === "yes")}>
                    <option value="no">нет</option>
                    <option value="yes">да</option>
                  </select>
                </label>
                <label>
                  Тип
                  <select value={pbScheduleType} onChange={(e) => setPbScheduleType(e.target.value as "interval" | "cron")}>
                    <option value="interval">interval</option>
                    <option value="cron">cron</option>
                  </select>
                </label>
                <label>
                  Значение
                  <input
                    value={pbScheduleValue}
                    onChange={(e) => setPbScheduleValue(e.target.value)}
                    placeholder={pbScheduleType === "interval" ? "секунды, например 300" : "cron, например */5 * * * *"}
                  />
                </label>
                <label>
                  Цели: хосты
                  <select
                    multiple
                    value={pbScheduleHostIds.map(String)}
                    onChange={(e) => setPbScheduleHostIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
                    style={{ minHeight: 140 }}
                    disabled={!pbScheduleEnabled}
                  >
                    {hosts.map((h) => (
                      <option key={h.id} value={h.id}>
                        {h.name} ({h.hostname}) [{h.environment}/{h.os_type}]
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Цели: группы
                  <select
                    multiple
                    value={pbScheduleGroupIds.map(String)}
                    onChange={(e) => setPbScheduleGroupIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
                    style={{ minHeight: 100 }}
                    disabled={!pbScheduleEnabled}
                  >
                    {groups.map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.name} ({g.type})
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Dry-run (--check)
                  <select value={pbScheduleDry ? "yes" : "no"} onChange={(e) => setPbScheduleDry(e.target.value === "yes")} disabled={!pbScheduleEnabled}>
                    <option value="no">нет</option>
                    <option value="yes">да</option>
                  </select>
                </label>
                <label>
                  Extra vars (JSON)
                  <textarea
                    value={pbScheduleExtraVars}
                    onChange={(e) => setPbScheduleExtraVars(e.target.value)}
                    rows={6}
                    style={{ resize: "vertical" }}
                    disabled={!pbScheduleEnabled}
                  />
                  {scheduleExtraVarsError && <span className="text-error">{scheduleExtraVarsError}</span>}
                </label>
              </div>
            </div>
            <div className="form-actions sticky-actions">
              <button type="submit" className="primary-button" disabled={!isAdmin || Boolean(scheduleExtraVarsError)}>
                Сохранить
              </button>
              <button type="button" className="ghost-button" onClick={resetPlaybookForm}>
                Сброс
              </button>
            </div>
          </form>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">
          <h2>История запусков</h2>
          <p className="form-helper">Live-лог: SSE `/runs/:id/stream`.</p>
        </div>
        {runs.length === 0 && <p>Запусков пока нет</p>}
        {runs.length > 0 && (
          <table className="hosts-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Плейбук</th>
                <th>Статус</th>
                <th>Источник</th>
                <th>Время</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.playbook_id}</td>
                  <td>{r.status}</td>
                  <td>{r.triggered_by}</td>
                  <td>{r.started_at ? "запущен" : "в очереди"}</td>
                  <td>
                    <div className="row-actions">
                      <button type="button" className="ghost-button" onClick={() => openLogs(r)}>
                        Логи
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {runModal.open && runModal.playbook && (
        <div className="modal-overlay">
          <div className="modal">
              <div className="modal-header">
                <div>
                  <strong>Запуск: {runModal.playbook.name}</strong>
                  <div className="form-helper">Выберите цели и параметры.</div>
                </div>
                <div className="row-actions">
                  <button type="button" className="ghost-button" onClick={submitRun} disabled={Boolean(runExtraVarsError)}>
                    Старт
                  </button>
                  <button type="button" className="ghost-button" onClick={() => setRunModal({ open: false, playbook: null })}>
                    Закрыть
                  </button>
                </div>
              </div>
            <div className="grid">
              <div className="panel">
                <div className="panel-title">
                  <h2>Цели</h2>
                </div>
                <div className="form-stack">
                  <label>
                    Хосты
                    <select
                      multiple
                      value={runHostIds.map(String)}
                      onChange={(e) => setRunHostIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
                      style={{ minHeight: 180 }}
                    >
                      {hosts.map((h) => (
                        <option key={h.id} value={h.id}>
                          {h.name} ({h.hostname}) [{h.environment}/{h.os_type}]
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Группы
                    <select
                      multiple
                      value={runGroupIds.map(String)}
                      onChange={(e) => setRunGroupIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
                      style={{ minHeight: 120 }}
                    >
                      {groups.map((g) => (
                        <option key={g.id} value={g.id}>
                          {g.name} ({g.type})
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Dry-run (--check)
                    <select value={runDry ? "yes" : "no"} onChange={(e) => setRunDry(e.target.value === "yes")}>
                      <option value="no">нет</option>
                      <option value="yes">да</option>
                    </select>
                  </label>
                </div>
              </div>
              <div className="panel">
                <div className="panel-title">
                  <h2>Extra vars (JSON)</h2>
                  <p className="form-helper">Поддержка ссылок: <code>{"{{ secret:ID }}"}</code></p>
                </div>
                <textarea value={runExtraVars} onChange={(e) => setRunExtraVars(e.target.value)} rows={14} style={{ width: "100%", resize: "vertical" }} />
                {runExtraVarsError && <p className="text-error">{runExtraVarsError}</p>}
              </div>
            </div>
          </div>
        </div>
      )}

      {logModal.open && logModal.run && (
        <div className="modal-overlay">
          <div className="modal full">
            <div className="modal-header">
              <div>
                <strong>Логи: run {logModal.run.id}</strong>
                <div className="form-helper">Live обновление по SSE.</div>
                {isAdmin && artifacts.length > 0 && token && (
                  <div className="form-helper" style={{ marginTop: 6 }}>
                    Артефакты:{" "}
                    {artifacts.map((a) => (
                      <a
                        key={a.name}
                        href={`/api/v1/runs/${logModal.run!.id}/artifacts/${encodeURIComponent(a.name)}?token=${encodeURIComponent(token)}&project_id=${getProjectId() ?? 1}`}
                        className="ghost-button"
                        style={{ marginRight: 8, display: "inline-block", padding: "0.25rem 0.5rem" }}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {a.name}
                      </a>
                    ))}
                  </div>
                )}
              </div>
              <div className="row-actions">
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => {
                    eventSourceRef.current?.close();
                    setLogModal({ open: false, run: null });
                    setLiveLogs("");
                  }}
                >
                  Закрыть
                </button>
              </div>
            </div>
            <div className="panel" style={{ flex: 1, overflow: "auto" }}>
              <pre style={{ whiteSpace: "pre-wrap" }}>{liveLogs}</pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AutomationPage;
