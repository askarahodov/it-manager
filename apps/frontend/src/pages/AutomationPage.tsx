import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

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

type Approval = {
  id: number;
  project_id: number;
  run_id: number;
  status: "pending" | "approved" | "rejected";
  reason?: string | null;
  requested_by?: number | null;
  decided_by?: number | null;
  created_at: string;
  decided_at?: string | null;
};

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

type PlaybookInstance = {
  id: number;
  name: string;
  description?: string | null;
  template_id: number;
  values: Record<string, unknown>;
  host_ids: number[];
  group_ids: number[];
  created_at: string;
};

type PlaybookTrigger = {
  id: number;
  project_id: number;
  playbook_id: number;
  type: "host_created" | "host_tags_changed" | "secret_rotated";
  enabled: boolean;
  filters: Record<string, unknown>;
  extra_vars: Record<string, unknown>;
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
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [triggers, setTriggers] = useState<PlaybookTrigger[]>([]);
  const [hosts, setHosts] = useState<Host[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [templates, setTemplates] = useState<PlaybookTemplate[]>([]);
  const [instances, setInstances] = useState<PlaybookInstance[]>([]);
  const [instanceRunPlaybookIds, setInstanceRunPlaybookIds] = useState<Record<number, number | "">>({});
  const [approvalReasons, setApprovalReasons] = useState<Record<number, string>>({});
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
  const [pbWebhookToken, setPbWebhookToken] = useState<string | null>(null);
  const [pbWebhookPath, setPbWebhookPath] = useState<string | null>(null);
  const [pbWebhookLoading, setPbWebhookLoading] = useState(false);

  const [editTemplateId, setEditTemplateId] = useState<number | null>(null);
  const [tplName, setTplName] = useState("");
  const [tplDescription, setTplDescription] = useState("");
  const [tplSchema, setTplSchema] = useState<string>("{}");
  const [tplDefaults, setTplDefaults] = useState<string>("{}");

  const [editInstanceId, setEditInstanceId] = useState<number | null>(null);
  const [instName, setInstName] = useState("");
  const [instDescription, setInstDescription] = useState("");
  const [instTemplateId, setInstTemplateId] = useState<number | "">("");
  const [instValues, setInstValues] = useState<string>("{}");
  const [instHostIds, setInstHostIds] = useState<number[]>([]);
  const [instGroupIds, setInstGroupIds] = useState<number[]>([]);

  const [editTriggerId, setEditTriggerId] = useState<number | null>(null);
  const [triggerPlaybookId, setTriggerPlaybookId] = useState<number | "">("");
  const [triggerType, setTriggerType] = useState<"host_created" | "host_tags_changed" | "secret_rotated">("host_created");
  const [triggerEnabled, setTriggerEnabled] = useState(true);
  const [triggerFilters, setTriggerFilters] = useState<string>('{"environments":["prod"],"tags":{"role":"db"}}');
  const [triggerExtraVars, setTriggerExtraVars] = useState<string>("{}");

  const [runModal, setRunModal] = useState<{ open: boolean; playbook: Playbook | null }>({
    open: false,
    playbook: null,
  });
  const [runHostIds, setRunHostIds] = useState<number[]>([]);
  const [runGroupIds, setRunGroupIds] = useState<number[]>([]);
  const [runExtraVars, setRunExtraVars] = useState<string>("{}");
  const [runDry, setRunDry] = useState(false);

  const [logModal, setLogModal] = useState<{ open: boolean; run: Run | null }>({ open: false, run: null });
  const [diffModal, setDiffModal] = useState<{ open: boolean; run: Run | null; diff: { added: Record<string, unknown>; removed: Record<string, unknown>; changed: Record<string, { before: unknown; after: unknown }> } | null }>({
    open: false,
    run: null,
    diff: null,
  });
  const [liveLogs, setLiveLogs] = useState<string>("");
  const [artifacts, setArtifacts] = useState<RunArtifact[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runModal.open && !logModal.open && !diffModal.open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (diffModal.open) {
        setDiffModal({ open: false, run: null, diff: null });
        return;
      }
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
  }, [runModal.open, logModal.open, diffModal.open]);

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

  const instanceValuesError = useMemo(() => {
    try {
      JSON.parse(instValues || "{}");
      return null;
    } catch {
      return "Некорректный JSON в values.";
    }
  }, [instValues]);

  const triggerFiltersError = useMemo(() => {
    try {
      JSON.parse(triggerFilters || "{}");
      return null;
    } catch {
      return "Некорректный JSON в filters.";
    }
  }, [triggerFilters]);

  const triggerVarsError = useMemo(() => {
    try {
      JSON.parse(triggerExtraVars || "{}");
      return null;
    } catch {
      return "Некорректный JSON в extra vars.";
    }
  }, [triggerExtraVars]);

  const triggerJsonError = triggerFiltersError || triggerVarsError;

  const selectedTemplate = useMemo(
    () => templates.find((tpl) => tpl.id === Number(instTemplateId)),
    [templates, instTemplateId]
  );

  const instValuesObject = useMemo(() => {
    try {
      return JSON.parse(instValues || "{}") as Record<string, unknown>;
    } catch {
      return null;
    }
  }, [instValues]);

  const schemaProperties = useMemo(() => {
    const schema = selectedTemplate?.vars_schema;
    if (!schema || typeof schema !== "object") return null;
    const props = (schema as Record<string, any>).properties;
    if (!props || typeof props !== "object") return null;
    return props as Record<string, any>;
  }, [selectedTemplate]);

  const refreshAll = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [pb, rr, aa, hh, gg, tt, ii, tr] = await Promise.all([
        apiFetch<Playbook[]>("/api/v1/playbooks/", { token }),
        apiFetch<Run[]>("/api/v1/runs/", { token }),
        apiFetch<Approval[]>("/api/v1/approvals/", { token }),
        apiFetch<Host[]>("/api/v1/hosts/", { token }),
        apiFetch<Group[]>("/api/v1/groups/", { token }),
        apiFetch<PlaybookTemplate[]>("/api/v1/playbook-templates/", { token }),
        apiFetch<PlaybookInstance[]>("/api/v1/playbook-instances/", { token }),
        apiFetch<PlaybookTrigger[]>("/api/v1/playbook-triggers/", { token }),
      ]);
      setPlaybooks(pb);
      setRuns(rr);
      setApprovals(aa);
      setHosts(hh);
      setGroups(gg);
      setTemplates(tt);
      setInstances(ii);
      setTriggers(tr);
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
    refreshAll().catch(() => undefined);
  }, [token, refreshAll, logModal.open, pushToast]);

  useEffect(() => {
    if (!token) return;
    const onProjectChange = () => {
      if (logModal.open) {
        eventSourceRef.current?.close();
        setLogModal({ open: false, run: null });
        setLiveLogs("");
        pushToast({ title: "Проект изменён", description: "Live-лог остановлен", variant: "warning" });
      }
      if (diffModal.open) {
        setDiffModal({ open: false, run: null, diff: null });
      }
      refreshAll().catch(() => undefined);
    };
    window.addEventListener("itmgr:project-change", onProjectChange);
    return () => window.removeEventListener("itmgr:project-change", onProjectChange);
  }, [token, refreshAll, logModal.open, diffModal.open, pushToast]);

  useEffect(() => {
    if (!playbooks.length || !instances.length) return;
    setInstanceRunPlaybookIds((prev) => {
      const next = { ...prev };
      instances.forEach((inst) => {
        if (!next[inst.id]) {
          next[inst.id] = playbooks[0].id;
        }
      });
      return next;
    });
  }, [instances, playbooks]);

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
    setPbWebhookToken(null);
    setPbWebhookPath(null);
  };

  const resetTemplateForm = () => {
    setEditTemplateId(null);
    setTplName("");
    setTplDescription("");
    setTplSchema("{}");
    setTplDefaults("{}");
  };

  const resetInstanceForm = () => {
    setEditInstanceId(null);
    setInstName("");
    setInstDescription("");
    setInstTemplateId("");
    setInstValues("{}");
    setInstHostIds([]);
    setInstGroupIds([]);
  };

  const resetTriggerForm = () => {
    setEditTriggerId(null);
    setTriggerPlaybookId("");
    setTriggerType("host_created");
    setTriggerEnabled(true);
    setTriggerFilters('{"environments":["prod"],"tags":{"role":"db"}}');
    setTriggerExtraVars("{}");
  };

  const startEditInstance = (inst: PlaybookInstance) => {
    setEditInstanceId(inst.id);
    setInstName(inst.name);
    setInstDescription(inst.description ?? "");
    setInstTemplateId(inst.template_id);
    setInstValues(JSON.stringify(inst.values ?? {}, null, 2));
    setInstHostIds(inst.host_ids ?? []);
    setInstGroupIds(inst.group_ids ?? []);
  };

  const startEditTemplate = (tpl: PlaybookTemplate) => {
    setEditTemplateId(tpl.id);
    setTplName(tpl.name);
    setTplDescription(tpl.description ?? "");
    setTplSchema(JSON.stringify(tpl.vars_schema ?? {}, null, 2));
    setTplDefaults(JSON.stringify(tpl.vars_defaults ?? {}, null, 2));
  };

  const startEditTrigger = (tr: PlaybookTrigger) => {
    setEditTriggerId(tr.id);
    setTriggerPlaybookId(tr.playbook_id);
    setTriggerType(tr.type);
    setTriggerEnabled(Boolean(tr.enabled));
    setTriggerFilters(JSON.stringify(tr.filters ?? {}, null, 2));
    setTriggerExtraVars(JSON.stringify(tr.extra_vars ?? {}, null, 2));
  };

  const startEditPlaybook = (pb: Playbook) => {
    setEditPlaybookId(pb.id);
    setPbName(pb.name);
    setPbDescription(pb.description ?? "");
    setPbYaml(pb.stored_content ?? defaultPlaybookYaml);
    setPbWebhookToken(null);
    setPbWebhookPath(null);
    const schedule = pb.schedule ?? null;
    setPbScheduleEnabled(Boolean(schedule?.enabled));
    setPbScheduleType(schedule?.type ?? "interval");
    setPbScheduleValue(schedule?.value ?? "300");
    setPbScheduleHostIds(schedule?.host_ids ?? []);
    setPbScheduleGroupIds(schedule?.group_ids ?? []);
    setPbScheduleExtraVars(JSON.stringify(schedule?.extra_vars ?? {}, null, 2));
    setPbScheduleDry(Boolean(schedule?.dry_run));
  };

  const fetchWebhookToken = async () => {
    if (!token || !editPlaybookId) return;
    setPbWebhookLoading(true);
    try {
      const resp = await apiFetch<{ token: string; url_path: string }>(`/api/v1/playbooks/${editPlaybookId}/webhook-token`, {
        token,
      });
      setPbWebhookToken(resp.token);
      setPbWebhookPath(resp.url_path);
    } catch (err) {
      const msg = formatError(err);
      pushToast({ title: "Не удалось получить webhook token", description: msg, variant: "error" });
    } finally {
      setPbWebhookLoading(false);
    }
  };

  const rotateWebhookToken = async () => {
    if (!token || !editPlaybookId) return;
    setPbWebhookLoading(true);
    try {
      const resp = await apiFetch<{ token: string; url_path: string }>(`/api/v1/playbooks/${editPlaybookId}/webhook-token`, {
        method: "POST",
        token,
      });
      setPbWebhookToken(resp.token);
      setPbWebhookPath(resp.url_path);
      pushToast({ title: "Webhook token обновлён", description: "Скопируйте новый токен.", variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      pushToast({ title: "Не удалось обновить webhook token", description: msg, variant: "error" });
    } finally {
      setPbWebhookLoading(false);
    }
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

  const submitInstance = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!token) return;
    if (!isAdmin) {
      setError("Требуются права admin.");
      return;
    }
    if (instanceValuesError) {
      setError(instanceValuesError);
      pushToast({ title: "Ошибка валидации", description: instanceValuesError, variant: "error" });
      return;
    }
    if (!instTemplateId) {
      const msg = "Нужно выбрать шаблон.";
      setError(msg);
      pushToast({ title: "Ошибка валидации", description: msg, variant: "error" });
      return;
    }
    try {
      const payload = {
        name: instName,
        description: instDescription || null,
        template_id: Number(instTemplateId),
        values: JSON.parse(instValues || "{}"),
        host_ids: instHostIds,
        group_ids: instGroupIds,
      };
      const url = editInstanceId ? `/api/v1/playbook-instances/${editInstanceId}` : "/api/v1/playbook-instances/";
      const method = editInstanceId ? "PUT" : "POST";
      const saved = await apiFetch<PlaybookInstance>(url, {
        method,
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setInstances((prev) => {
        if (editInstanceId) {
          return prev.map((i) => (i.id === saved.id ? saved : i));
        }
        return [...prev, saved].sort((a, b) => a.name.localeCompare(b.name));
      });
      resetInstanceForm();
      pushToast({ title: editInstanceId ? "Инстанс обновлён" : "Инстанс создан", description: saved.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка сохранения инстанса", description: msg, variant: "error" });
    }
  };

  const deleteInstance = async (inst: PlaybookInstance) => {
    if (!token || !isAdmin) return;
    const ok = await confirm({
      title: "Удалить инстанс?",
      description: `Будет удалён инстанс "${inst.name}".`,
      confirmText: "Удалить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!ok) return;
    try {
      await apiFetch<void>(`/api/v1/playbook-instances/${inst.id}`, { method: "DELETE", token });
      setInstances((prev) => prev.filter((i) => i.id !== inst.id));
      pushToast({ title: "Инстанс удалён", description: inst.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      pushToast({ title: "Ошибка удаления инстанса", description: msg, variant: "error" });
    }
  };

  const submitTrigger = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!token) return;
    if (!isAdmin) {
      setError("Требуются права admin.");
      return;
    }
    if (triggerJsonError) {
      setError(triggerJsonError);
      pushToast({ title: "Ошибка валидации", description: triggerJsonError, variant: "error" });
      return;
    }
    if (!triggerPlaybookId) {
      const msg = "Нужно выбрать плейбук.";
      setError(msg);
      pushToast({ title: "Ошибка валидации", description: msg, variant: "error" });
      return;
    }
    try {
      const payload = {
        playbook_id: Number(triggerPlaybookId),
        type: triggerType,
        enabled: triggerEnabled,
        filters: JSON.parse(triggerFilters || "{}"),
        extra_vars: JSON.parse(triggerExtraVars || "{}"),
      };
      const url = editTriggerId ? `/api/v1/playbook-triggers/${editTriggerId}` : "/api/v1/playbook-triggers/";
      const method = editTriggerId ? "PUT" : "POST";
      const saved = await apiFetch<PlaybookTrigger>(url, {
        method,
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setTriggers((prev) => {
        if (editTriggerId) {
          return prev.map((t) => (t.id === saved.id ? saved : t));
        }
        return [saved, ...prev];
      });
      resetTriggerForm();
      pushToast({ title: editTriggerId ? "Триггер обновлён" : "Триггер создан", description: `#${saved.id}`, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка сохранения триггера", description: msg, variant: "error" });
    }
  };

  const deleteTrigger = async (tr: PlaybookTrigger) => {
    if (!token || !isAdmin) return;
    const ok = await confirm({
      title: "Удалить триггер?",
      description: `Будет удалён триггер #${tr.id}.`,
      confirmText: "Удалить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!ok) return;
    try {
      await apiFetch<void>(`/api/v1/playbook-triggers/${tr.id}`, { method: "DELETE", token });
      setTriggers((prev) => prev.filter((t) => t.id !== tr.id));
      pushToast({ title: "Триггер удалён", description: `#${tr.id}`, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      pushToast({ title: "Ошибка удаления триггера", description: msg, variant: "error" });
    }
  };

  const runInstance = async (inst: PlaybookInstance) => {
    if (!token) return;
    const playbookId = instanceRunPlaybookIds[inst.id];
    if (!playbookId) {
      pushToast({ title: "Выберите плейбук", description: "Для запуска инстанса нужен плейбук.", variant: "warning" });
      return;
    }
    try {
      const payload = { playbook_id: Number(playbookId), dry_run: false, extra_vars: {} };
      const resp = await apiFetch<{ run_id: number }>(`/api/v1/playbook-instances/${inst.id}/run`, {
        method: "POST",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      pushToast({ title: "Запуск создан", description: `run #${resp.run_id}`, variant: "success" });
      refreshAll().catch(() => undefined);
    } catch (err) {
      const msg = formatError(err);
      pushToast({ title: "Ошибка запуска инстанса", description: msg, variant: "error" });
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

  const playbookById = useMemo(() => {
    const map = new Map<number, Playbook>();
    playbooks.forEach((pb) => map.set(pb.id, pb));
    return map;
  }, [playbooks]);

  const getApprovalStatus = (run: Run) => {
    const snapshot = run.target_snapshot as Record<string, unknown>;
    const status = snapshot?.approval_status;
    return typeof status === "string" ? status : null;
  };

  const getApprovalTargets = (run?: Run | null) => {
    if (!run) return "—";
    const snapshot = run.target_snapshot as Record<string, unknown>;
    const hostIds = Array.isArray(snapshot?.host_ids) ? snapshot.host_ids.length : 0;
    const groupIds = Array.isArray(snapshot?.group_ids) ? snapshot.group_ids.length : 0;
    const hosts = Array.isArray(snapshot?.hosts) ? snapshot.hosts.length : 0;
    const targetCount = hosts > 0 ? hosts : hostIds + groupIds;
    return targetCount > 0 ? `${targetCount} целей` : "—";
  };

  const normalizeRecord = (value: unknown) => {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return value as Record<string, unknown>;
    }
    return {};
  };

  const computeParamDiff = (before: Record<string, unknown>, after: Record<string, unknown>) => {
    const added: Record<string, unknown> = {};
    const removed: Record<string, unknown> = {};
    const changed: Record<string, { before: unknown; after: unknown }> = {};
    const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
    keys.forEach((key) => {
      const hasBefore = Object.prototype.hasOwnProperty.call(before, key);
      const hasAfter = Object.prototype.hasOwnProperty.call(after, key);
      if (!hasBefore && hasAfter) {
        added[key] = after[key];
        return;
      }
      if (hasBefore && !hasAfter) {
        removed[key] = before[key];
        return;
      }
      const beforeValue = before[key];
      const afterValue = after[key];
      if (JSON.stringify(beforeValue) !== JSON.stringify(afterValue)) {
        changed[key] = { before: beforeValue, after: afterValue };
      }
    });
    return { added, removed, changed };
  };

  const getRunParamsDiff = (run?: Run | null) => {
    if (!run) return null;
    const snapshot = run.target_snapshot as Record<string, unknown>;
    const before = normalizeRecord(snapshot?.params_before);
    const after = normalizeRecord(snapshot?.params_after);
    return computeParamDiff(before, after);
  };

  const getDiffCounts = (diff: { added: Record<string, unknown>; removed: Record<string, unknown>; changed: Record<string, unknown> } | null) => {
    if (!diff) return { added: 0, removed: 0, changed: 0 };
    return {
      added: Object.keys(diff.added).length,
      removed: Object.keys(diff.removed).length,
      changed: Object.keys(diff.changed).length,
    };
  };

  const hasParamDiff = (diff: { added: Record<string, unknown>; removed: Record<string, unknown>; changed: Record<string, unknown> } | null) => {
    if (!diff) return false;
    return Object.keys(diff.added).length > 0 || Object.keys(diff.removed).length > 0 || Object.keys(diff.changed).length > 0;
  };

  const formatJson = (value: unknown) => JSON.stringify(value, null, 2);

  const openDiffModal = (run: Run) => {
    const diff = getRunParamsDiff(run);
    setDiffModal({ open: true, run, diff: diff ? { ...diff } : null });
  };

  const decideApproval = async (approval: Approval, decision: "approved" | "rejected") => {
    if (!token) return;
    if (!isAdmin) {
      pushToast({ title: "Недостаточно прав", description: "Нужно право admin.", variant: "warning" });
      return;
    }
    try {
      const reason = approvalReasons[approval.id]?.trim() || null;
      await apiFetch<void>(`/api/v1/approvals/${approval.id}/decision`, {
        method: "POST",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: decision, reason }),
      });
      setApprovalReasons((prev) => {
        const next = { ...prev };
        delete next[approval.id];
        return next;
      });
      pushToast({
        title: decision === "approved" ? "Approval подтверждён" : "Approval отклонён",
        description: `Run #${approval.run_id}`,
        variant: decision === "approved" ? "success" : "warning",
      });
      refreshAll().catch(() => undefined);
    } catch (err) {
      const msg = formatError(err);
      pushToast({ title: "Ошибка approval", description: msg, variant: "error" });
    }
  };

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
          {loading && templates.length === 0 && (
            <table className="hosts-table">
              <thead>
                <tr>
                  <th>Название</th>
                  <th>Описание</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: 4 }).map((_, idx) => (
                  <tr key={`skeleton-template-${idx}`}>
                    <td><span className="skeleton-line" /></td>
                    <td><span className="skeleton-line" /></td>
                    <td><span className="skeleton-line" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
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
            {error && <span className="text-error form-error">{error}</span>}
          </form>
        </div>
      </div>

      <div className="grid">
        <div className="panel">
          <div className="panel-title">
            <h2>Инстансы плейбуков</h2>
            <p className="form-helper">Значения шаблонов + привязка целей. Для запуска выберите плейбук в строке.</p>
          </div>
          {instances.length === 0 && <p>Инстансов пока нет</p>}
          {loading && instances.length === 0 && (
            <table className="hosts-table">
              <thead>
                <tr>
                  <th>Название</th>
                  <th>Шаблон</th>
                  <th>Цели</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: 4 }).map((_, idx) => (
                  <tr key={`skeleton-instance-${idx}`}>
                    <td><span className="skeleton-line" /></td>
                    <td><span className="skeleton-line" /></td>
                    <td><span className="skeleton-line small" /></td>
                    <td><span className="skeleton-line" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {instances.length > 0 && (
            <table className="hosts-table">
              <thead>
                <tr>
                  <th>Название</th>
                  <th>Шаблон</th>
                  <th>Цели</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {instances.map((inst) => {
                  const templateName = templates.find((t) => t.id === inst.template_id)?.name ?? `#${inst.template_id}`;
                  return (
                    <tr key={inst.id}>
                      <td>{inst.name}</td>
                      <td>{templateName}</td>
                      <td>{(inst.host_ids?.length ?? 0) + (inst.group_ids?.length ?? 0)}</td>
                      <td>
                        <div className="row-actions">
                          <select
                            value={String(instanceRunPlaybookIds[inst.id] ?? "")}
                            onChange={(e) =>
                              setInstanceRunPlaybookIds((prev) => ({ ...prev, [inst.id]: e.target.value ? Number(e.target.value) : "" }))
                            }
                            title="Плейбук для запуска"
                          >
                            <option value="">плейбук…</option>
                            {playbooks.map((pb) => (
                              <option key={pb.id} value={pb.id}>
                                {pb.name}
                              </option>
                            ))}
                          </select>
                          <button type="button" className="ghost-button" onClick={() => startEditInstance(inst)} disabled={!isAdmin}>
                            Редактировать
                          </button>
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={() => runInstance(inst)}
                            disabled={!canRun || !instanceRunPlaybookIds[inst.id]}
                          >
                            Запуск
                          </button>
                          <button type="button" className="ghost-button" onClick={() => deleteInstance(inst)} disabled={!isAdmin}>
                            Удалить
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className="panel">
          <div className="panel-title">
            <h2>{editInstanceId ? "Редактировать инстанс" : "Создать инстанс"}</h2>
            {!isAdmin && <p className="form-helper">Создание/редактирование доступно только admin.</p>}
          </div>
          <form className="form-stack" onSubmit={submitInstance}>
            <label>
              Название
              <input value={instName} onChange={(e) => setInstName(e.target.value)} required minLength={3} disabled={!isAdmin} />
            </label>
            <label>
              Шаблон
              <select
                value={String(instTemplateId)}
                onChange={(e) => setInstTemplateId(e.target.value ? Number(e.target.value) : "")}
                disabled={!isAdmin}
              >
                <option value="">—</option>
                {templates.map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>
                    {tpl.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Описание
              <input value={instDescription} onChange={(e) => setInstDescription(e.target.value)} placeholder="Опционально" disabled={!isAdmin} />
            </label>
            <label>
              Values (JSON)
              {schemaProperties && instValuesObject && !instanceValuesError ? (
                <div className="stack">
                  {Object.entries(schemaProperties).map(([key, schema]) => {
                    const field = (schema || {}) as Record<string, any>;
                    const value = instValuesObject[key];
                    const enumValues = Array.isArray(field.enum) ? field.enum.map(String) : null;
                    const type = String(field.type || "string");
                    const onValueChange = (nextValue: unknown) => {
                      const updated = { ...instValuesObject, [key]: nextValue };
                      setInstValues(JSON.stringify(updated, null, 2));
                    };
                    if (enumValues) {
                      return (
                        <label key={key}>
                          {key}
                          <select value={String(value ?? "")} onChange={(e) => onValueChange(e.target.value)} disabled={!isAdmin}>
                            <option value="">—</option>
                            {enumValues.map((opt) => (
                              <option key={opt} value={opt}>
                                {opt}
                              </option>
                            ))}
                          </select>
                        </label>
                      );
                    }
                    if (type === "number" || type === "integer") {
                      const numericValue =
                        typeof value === "number"
                          ? value
                          : typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))
                            ? Number(value)
                            : "";
                      return (
                        <label key={key}>
                          {key}
                          <input
                            type="number"
                            value={numericValue}
                            onChange={(e) => onValueChange(e.target.value === "" ? "" : Number(e.target.value))}
                            disabled={!isAdmin}
                          />
                        </label>
                      );
                    }
                    if (type === "boolean") {
                      return (
                        <label key={key}>
                          {key}
                          <select
                            value={value === true ? "true" : value === false ? "false" : ""}
                            onChange={(e) => onValueChange(e.target.value === "" ? "" : e.target.value === "true")}
                            disabled={!isAdmin}
                          >
                            <option value="">—</option>
                            <option value="true">true</option>
                            <option value="false">false</option>
                          </select>
                        </label>
                      );
                    }
                    return (
                      <label key={key}>
                        {key}
                        <input
                          value={typeof value === "string" || typeof value === "number" ? value : value == null ? "" : String(value)}
                          onChange={(e) => onValueChange(e.target.value)}
                          disabled={!isAdmin}
                        />
                      </label>
                    );
                  })}
                  <span className="form-helper">Значения синхронизируются с JSON ниже.</span>
                </div>
              ) : (
                <textarea value={instValues} onChange={(e) => setInstValues(e.target.value)} rows={6} style={{ resize: "vertical" }} disabled={!isAdmin} />
              )}
              {instanceValuesError && <span className="text-error">{instanceValuesError}</span>}
              {schemaProperties && instValuesObject && !instanceValuesError && (
                <textarea value={instValues} onChange={(e) => setInstValues(e.target.value)} rows={6} style={{ resize: "vertical" }} disabled={!isAdmin} />
              )}
            </label>
            <label>
              Цели: хосты
              <select
                multiple
                value={instHostIds.map(String)}
                onChange={(e) => setInstHostIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
                style={{ minHeight: 140 }}
                disabled={!isAdmin}
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
                value={instGroupIds.map(String)}
                onChange={(e) => setInstGroupIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
                style={{ minHeight: 100 }}
                disabled={!isAdmin}
              >
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name} ({g.type})
                  </option>
                ))}
              </select>
            </label>
            <div className="form-actions">
              <button type="submit" className="primary-button" disabled={!isAdmin || Boolean(instanceValuesError)}>
                Сохранить
              </button>
              <button type="button" className="ghost-button" onClick={resetInstanceForm}>
                Сброс
              </button>
            </div>
            {error && <span className="text-error form-error">{error}</span>}
          </form>
        </div>
      </div>

      <div className="grid">
        <div className="panel">
          <div className="panel-title">
            <h2>Триггеры плейбуков</h2>
            <p className="form-helper">Автозапуск по событиям: создание хоста, изменение тегов.</p>
          </div>
          {triggers.length === 0 && <p>Триггеров пока нет</p>}
          {loading && triggers.length === 0 && (
            <table className="hosts-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Тип</th>
                  <th>Плейбук</th>
                  <th>Статус</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: 3 }).map((_, idx) => (
                  <tr key={`skeleton-trigger-${idx}`}>
                    <td><span className="skeleton-line small" /></td>
                    <td><span className="skeleton-line" /></td>
                    <td><span className="skeleton-line" /></td>
                    <td><span className="skeleton-line small" /></td>
                    <td><span className="skeleton-line" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {triggers.length > 0 && (
            <table className="hosts-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Тип</th>
                  <th>Плейбук</th>
                  <th>Статус</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {triggers.map((tr) => (
                  <tr key={tr.id}>
                    <td>{tr.id}</td>
                    <td>{tr.type}</td>
                    <td>{playbookById.get(tr.playbook_id)?.name ?? `#${tr.playbook_id}`}</td>
                    <td>
                      <span className={`status-pill ${tr.enabled ? "success" : "pending"}`}>{tr.enabled ? "enabled" : "disabled"}</span>
                    </td>
                    <td>
                      <div className="row-actions">
                        <button type="button" className="ghost-button" onClick={() => startEditTrigger(tr)} disabled={!isAdmin}>
                          Редактировать
                        </button>
                        <button type="button" className="ghost-button" onClick={() => deleteTrigger(tr)} disabled={!isAdmin}>
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
            <h2>{editTriggerId ? "Редактировать триггер" : "Создать триггер"}</h2>
            {!isAdmin && <p className="form-helper">Создание/редактирование доступно только admin.</p>}
          </div>
          <form className="form-stack" onSubmit={submitTrigger}>
            <label>
              Плейбук
              <select
                value={String(triggerPlaybookId)}
                onChange={(e) => setTriggerPlaybookId(e.target.value ? Number(e.target.value) : "")}
                disabled={!isAdmin}
              >
                <option value="">—</option>
                {playbooks.map((pb) => (
                  <option key={pb.id} value={pb.id}>
                    {pb.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Тип события
              <select
                value={triggerType}
                onChange={(e) => setTriggerType(e.target.value as "host_created" | "host_tags_changed" | "secret_rotated")}
                disabled={!isAdmin}
              >
                <option value="host_created">host_created</option>
                <option value="host_tags_changed">host_tags_changed</option>
                <option value="secret_rotated">secret_rotated</option>
              </select>
            </label>
            <label>
              Статус
              <select value={triggerEnabled ? "enabled" : "disabled"} onChange={(e) => setTriggerEnabled(e.target.value === "enabled")} disabled={!isAdmin}>
                <option value="enabled">enabled</option>
                <option value="disabled">disabled</option>
              </select>
            </label>
            <label>
              Filters (JSON)
              <textarea value={triggerFilters} onChange={(e) => setTriggerFilters(e.target.value)} rows={5} style={{ resize: "vertical" }} disabled={!isAdmin} />
              {triggerFiltersError && <span className="text-error">{triggerFiltersError}</span>}
              <span className="form-helper">Примеры: {"{\"environments\":[\"prod\"],\"tags\":{\"role\":\"db\"}}"} или {"{\"types\":[\"password\"],\"scopes\":[\"project\"]}"}.</span>
            </label>
            <label>
              Extra vars (JSON)
              <textarea value={triggerExtraVars} onChange={(e) => setTriggerExtraVars(e.target.value)} rows={5} style={{ resize: "vertical" }} disabled={!isAdmin} />
              {triggerVarsError && <span className="text-error">{triggerVarsError}</span>}
            </label>
            <div className="form-actions">
              <button type="submit" className="primary-button" disabled={!isAdmin || Boolean(triggerJsonError)}>
                Сохранить
              </button>
              <button type="button" className="ghost-button" onClick={resetTriggerForm}>
                Сброс
              </button>
            </div>
            {error && <span className="text-error form-error">{error}</span>}
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
          {loading && playbooks.length === 0 && (
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
                {Array.from({ length: 4 }).map((_, idx) => (
                  <tr key={`skeleton-playbook-${idx}`}>
                    <td><span className="skeleton-line" /></td>
                    <td><span className="skeleton-line" /></td>
                    <td><span className="skeleton-line small" /></td>
                    <td><span className="skeleton-line" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
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
            <div className="panel" style={{ padding: "0.75rem" }}>
              <div className="panel-title">
                <h2>Webhook запуск</h2>
                <p className="form-helper">Для внешних событий (HTTP POST).</p>
              </div>
              {!editPlaybookId && <p className="form-helper">Сохраните плейбук, чтобы сгенерировать webhook token.</p>}
              <div className="form-stack" style={{ marginTop: 0 }}>
                <div className="row-actions">
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={fetchWebhookToken}
                    disabled={!isAdmin || !editPlaybookId || pbWebhookLoading}
                  >
                    Показать
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={rotateWebhookToken}
                    disabled={!isAdmin || !editPlaybookId || pbWebhookLoading}
                  >
                    Сгенерировать
                  </button>
                </div>
                <label>
                  Token
                  <input value={pbWebhookToken ?? ""} readOnly placeholder="—" />
                </label>
                <label>
                  URL path
                  <input value={pbWebhookPath ?? ""} readOnly placeholder="—" />
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
            {error && <span className="text-error form-error">{error}</span>}
          </form>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">
          <h2>Approval запросы</h2>
          <p className="form-helper">Запуски на prod требуют подтверждения admin.</p>
        </div>
        {approvals.length === 0 && <p>Запросов на approval пока нет</p>}
        {loading && approvals.length === 0 && (
          <table className="hosts-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Run</th>
                <th>Плейбук</th>
                <th>Цели</th>
                <th>Статус</th>
                <th>Причина</th>
                <th>Параметры</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 3 }).map((_, idx) => (
                <tr key={`skeleton-approval-${idx}`}>
                  <td><span className="skeleton-line small" /></td>
                  <td><span className="skeleton-line small" /></td>
                  <td><span className="skeleton-line" /></td>
                  <td><span className="skeleton-line small" /></td>
                  <td><span className="skeleton-line small" /></td>
                  <td><span className="skeleton-line" /></td>
                  <td><span className="skeleton-line" /></td>
                  <td><span className="skeleton-line" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {approvals.length > 0 && (
          <table className="hosts-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Run</th>
                <th>Плейбук</th>
                <th>Цели</th>
                <th>Статус</th>
                <th>Причина</th>
                <th>Параметры</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {approvals.map((approval) => {
                const run = runs.find((item) => item.id === approval.run_id);
                const playbookName = run ? playbookById.get(run.playbook_id)?.name ?? `#${run.playbook_id}` : "—";
                const decisionDisabled = !isAdmin || approval.status !== "pending";
                const diff = getRunParamsDiff(run);
                const diffCounts = getDiffCounts(diff);
                return (
                  <tr key={approval.id}>
                    <td>{approval.id}</td>
                    <td>{approval.run_id}</td>
                    <td>{playbookName}</td>
                    <td>{getApprovalTargets(run)}</td>
                    <td>
                      <span className={`status-pill ${approval.status}`}>{approval.status}</span>
                    </td>
                    <td>
                      {approval.status === "pending" ? (
                        <input
                          value={approvalReasons[approval.id] ?? ""}
                          onChange={(e) => setApprovalReasons((prev) => ({ ...prev, [approval.id]: e.target.value }))}
                          placeholder="Комментарий"
                          disabled={decisionDisabled}
                        />
                      ) : (
                        approval.reason ?? "—"
                      )}
                    </td>
                    <td>
                      {hasParamDiff(diff) ? (
                        <div className="diff-summary">
                          <span className="diff-chip added">+{diffCounts.added}</span>
                          <span className="diff-chip removed">-{diffCounts.removed}</span>
                          <span className="diff-chip changed">~{diffCounts.changed}</span>
                          <button type="button" className="ghost-button" onClick={() => openDiffModal(run!)}>
                            Показать
                          </button>
                        </div>
                      ) : "—"}
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => decideApproval(approval, "approved")}
                          disabled={decisionDisabled}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => decideApproval(approval, "rejected")}
                          disabled={decisionDisabled}
                        >
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <div className="panel-title">
          <h2>История запусков</h2>
          <p className="form-helper">Live-лог: SSE `/runs/:id/stream`.</p>
        </div>
        {runs.length === 0 && <p>Запусков пока нет</p>}
        {loading && runs.length === 0 && (
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
              {Array.from({ length: 4 }).map((_, idx) => (
                <tr key={`skeleton-run-${idx}`}>
                  <td><span className="skeleton-line small" /></td>
                  <td><span className="skeleton-line" /></td>
                  <td><span className="skeleton-line small" /></td>
                  <td><span className="skeleton-line" /></td>
                  <td><span className="skeleton-line small" /></td>
                  <td><span className="skeleton-line" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
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
                  <td>
                    <span className={`status-pill ${r.status}`}>
                      {getApprovalStatus(r) === "pending" ? "pending (approval)" : r.status}
                    </span>
                  </td>
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

      {diffModal.open && diffModal.run && (
        <div className="modal-overlay">
          <div className="modal full">
            <div className="modal-header">
              <div>
                <strong>Diff параметров: run {diffModal.run.id}</strong>
                <div className="form-helper">Playbook #{diffModal.run.playbook_id}</div>
              </div>
              <div className="row-actions">
                <button type="button" className="ghost-button" onClick={() => setDiffModal({ open: false, run: null, diff: null })}>
                  Закрыть
                </button>
              </div>
            </div>
            <div className="diff-grid">
              <div className="diff-card added">
                <div className="diff-card-title">Добавлено</div>
                <pre>{formatJson(diffModal.diff?.added ?? {})}</pre>
              </div>
              <div className="diff-card removed">
                <div className="diff-card-title">Удалено</div>
                <pre>{formatJson(diffModal.diff?.removed ?? {})}</pre>
              </div>
              <div className="diff-card changed">
                <div className="diff-card-title">Изменено</div>
                <pre>{formatJson(diffModal.diff?.changed ?? {})}</pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AutomationPage;
