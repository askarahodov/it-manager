import { FormEvent, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useConfirm } from "../components/ui/ConfirmProvider";
import { useToast } from "../components/ui/ToastProvider";
import { formatError } from "../lib/errors";
import { getProjectId, setProjectId } from "../lib/project";

type AuditEvent = {
  id: number;
  actor: string;
  actor_role?: string | null;
  action: string;
  entity_type?: string | null;
  entity_id?: number | null;
  success: boolean;
  meta: Record<string, unknown>;
  source_ip?: string | null;
  created_at: string;
};

type UserRole = "admin" | "operator" | "viewer" | "automation-only" | "user";
type UserItem = {
  id: number;
  email: string;
  role: UserRole;
  allowed_environments?: string[] | null;
  allowed_group_ids?: number[] | null;
  allowed_project_ids?: number[] | null;
  created_at: string;
};

type GroupItem = {
  id: number;
  name: string;
  type: "static" | "dynamic";
};

type ProjectItem = {
  id: number;
  name: string;
  description?: string | null;
  created_at: string;
};

type NotificationEndpoint = {
  id: number;
  name: string;
  type: string;
  url: string;
  secret?: string | null;
  events: string[];
  enabled: boolean;
  created_at: string;
};

type GlobalSettings = {
  maintenance_mode: boolean;
  banner_message?: string | null;
  banner_level: "info" | "warning" | "error";
  default_project_id?: number | null;
};

type PluginDefinition = {
  id: string;
  type: "inventory" | "secrets" | "automation";
  name: string;
  description?: string | null;
  config_schema: Array<Record<string, unknown>>;
};

type PluginInstance = {
  id: number;
  project_id: number;
  name: string;
  type: "inventory" | "secrets" | "automation";
  definition_id: string;
  enabled: boolean;
  is_default: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at?: string | null;
};

const ENV_OPTIONS = ["prod", "stage", "dev"] as const;
const NOTIFICATION_EVENTS = [
  "run.failed",
  "run.success",
  "approval.requested",
  "approval.approved",
  "approval.rejected",
  "host.offline",
  "secret.rotated",
  "secret.expiring",
] as const;

function SettingsPage() {
  const { status, user, token, login, logout, refresh } = useAuth();
  const { confirm } = useConfirm();
  const { pushToast } = useToast();
  const [email, setEmail] = useState("admin@it.local");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditLimit, setAuditLimit] = useState(100);
  const [auditAction, setAuditAction] = useState("");
  const [auditEntityType, setAuditEntityType] = useState("");
  const [auditActor, setAuditActor] = useState("");
  const [auditSourceIp, setAuditSourceIp] = useState("");
  const [users, setUsers] = useState<UserItem[]>([]);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [usersLoading, setUsersLoading] = useState(false);
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState<UserRole>("user");
  const [groups, setGroups] = useState<GroupItem[]>([]);

  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDescription, setNewProjectDescription] = useState("");
  const [compactTables, setCompactTables] = useState<boolean>(() => localStorage.getItem("it_manager_compact_tables") === "1");

  const [accessUserId, setAccessUserId] = useState<number | null>(null);
  const [accessEnvRestricted, setAccessEnvRestricted] = useState(false);
  const [accessEnvironments, setAccessEnvironments] = useState<string[]>([]);
  const [accessGroupsRestricted, setAccessGroupsRestricted] = useState(false);
  const [accessGroupIds, setAccessGroupIds] = useState<number[]>([]);
  const [accessProjectsRestricted, setAccessProjectsRestricted] = useState(false);
  const [accessProjectIds, setAccessProjectIds] = useState<number[]>([]);
  const [accessSaving, setAccessSaving] = useState(false);

  const [newEnvRestricted, setNewEnvRestricted] = useState(false);
  const [newAllowedEnvironments, setNewAllowedEnvironments] = useState<string[]>([]);
  const [newGroupsRestricted, setNewGroupsRestricted] = useState(false);
  const [newAllowedGroupIds, setNewAllowedGroupIds] = useState<number[]>([]);
  const [newProjectsRestricted, setNewProjectsRestricted] = useState(false);
  const [newAllowedProjectIds, setNewAllowedProjectIds] = useState<number[]>([]);

  const [notificationEndpoints, setNotificationEndpoints] = useState<NotificationEndpoint[]>([]);
  const [notificationError, setNotificationError] = useState<string | null>(null);
  const [notificationLoading, setNotificationLoading] = useState(false);
  const [notifEditId, setNotifEditId] = useState<number | null>(null);
  const [notifName, setNotifName] = useState("");
  const [notifType, setNotifType] = useState("webhook");
  const [notifUrl, setNotifUrl] = useState("");
  const [notifSecret, setNotifSecret] = useState("");
  const [notifEnabled, setNotifEnabled] = useState(true);
  const [notifEvents, setNotifEvents] = useState<string[]>([]);
  const [settingsTab, setSettingsTab] = useState<
    "session" | "projects" | "users" | "audit" | "notifications" | "plugins" | "admin"
  >("session");
  const [adminSettings, setAdminSettings] = useState<GlobalSettings | null>(null);
  const [adminSettingsError, setAdminSettingsError] = useState<string | null>(null);
  const [adminSettingsLoading, setAdminSettingsLoading] = useState(false);
  const [maintenanceMode, setMaintenanceMode] = useState(false);
  const [bannerMessage, setBannerMessage] = useState("");
  const [bannerLevel, setBannerLevel] = useState<"info" | "warning" | "error">("info");
  const [defaultProjectId, setDefaultProjectId] = useState<string>("");
  const [pluginDefinitions, setPluginDefinitions] = useState<PluginDefinition[]>([]);
  const [pluginInstances, setPluginInstances] = useState<PluginInstance[]>([]);
  const [pluginError, setPluginError] = useState<string | null>(null);
  const [pluginLoading, setPluginLoading] = useState(false);
  const [pluginEditId, setPluginEditId] = useState<number | null>(null);
  const [pluginName, setPluginName] = useState("");
  const [pluginType, setPluginType] = useState<"inventory" | "secrets" | "automation">("inventory");
  const [pluginDefinitionId, setPluginDefinitionId] = useState("");
  const [pluginEnabled, setPluginEnabled] = useState(true);
  const [pluginDefault, setPluginDefault] = useState(false);
  const [pluginConfig, setPluginConfig] = useState("{\n  \n}");

  const selectedAccessUser = useMemo(
    () => (accessUserId ? users.find((u) => u.id === accessUserId) ?? null : null),
    [accessUserId, users]
  );
  const availablePluginDefinitions = useMemo(
    () => pluginDefinitions.filter((item) => item.type === pluginType),
    [pluginDefinitions, pluginType]
  );
  const selectedPluginDefinition = useMemo(
    () => pluginDefinitions.find((item) => item.id === pluginDefinitionId) ?? null,
    [pluginDefinitions, pluginDefinitionId]
  );

  useEffect(() => {
    refresh().catch(() => undefined);
  }, [refresh]);

  useEffect(() => {
    if (compactTables) {
      document.body.classList.add("compact-tables");
      localStorage.setItem("it_manager_compact_tables", "1");
    } else {
      document.body.classList.remove("compact-tables");
      localStorage.removeItem("it_manager_compact_tables");
    }
  }, [compactTables]);

  const loadUsers = async () => {
    if (!token || user?.role !== "admin") return;
    setUsersLoading(true);
    setUsersError(null);
    try {
      const list = await apiFetch<UserItem[]>("/api/v1/users/", { token });
      setUsers(list);
    } catch (err) {
      const msg = formatError(err);
      setUsersError(msg);
      pushToast({ title: "Не удалось загрузить пользователей", description: msg, variant: "error" });
    } finally {
      setUsersLoading(false);
    }
  };

  const loadGroups = async () => {
    if (!token || user?.role !== "admin") return;
    try {
      const list = await apiFetch<GroupItem[]>("/api/v1/groups/", { token });
      setGroups(list);
    } catch (err) {
      const msg = formatError(err);
      pushToast({ title: "Не удалось загрузить группы", description: msg, variant: "warning" });
    }
  };

  const loadProjects = async () => {
    if (!token) return;
    setProjectsLoading(true);
    setProjectsError(null);
    try {
      const list = await apiFetch<ProjectItem[]>("/api/v1/projects/", { token });
      setProjects(list);
    } catch (err) {
      const msg = formatError(err);
      setProjectsError(msg);
      pushToast({ title: "Не удалось загрузить проекты", description: msg, variant: "warning" });
    } finally {
      setProjectsLoading(false);
    }
  };

  const loadNotifications = async () => {
    if (!token || user?.role !== "admin") return;
    setNotificationLoading(true);
    setNotificationError(null);
    try {
      const items = await apiFetch<NotificationEndpoint[]>("/api/v1/notifications/", { token });
      setNotificationEndpoints(items);
    } catch (err) {
      const msg = formatError(err);
      setNotificationError(msg);
      pushToast({ title: "Не удалось загрузить уведомления", description: msg, variant: "error" });
    } finally {
      setNotificationLoading(false);
    }
  };

  const loadAdminSettings = async () => {
    if (!token || user?.role !== "admin") return;
    setAdminSettingsLoading(true);
    setAdminSettingsError(null);
    try {
      const data = await apiFetch<GlobalSettings>("/api/v1/admin/settings/", { token });
      setAdminSettings(data);
      setMaintenanceMode(Boolean(data.maintenance_mode));
      setBannerMessage(data.banner_message ?? "");
      setBannerLevel(data.banner_level ?? "info");
      setDefaultProjectId(data.default_project_id ? String(data.default_project_id) : "");
    } catch (err) {
      const msg = formatError(err);
      setAdminSettingsError(msg);
    } finally {
      setAdminSettingsLoading(false);
    }
  };

  const loadPlugins = async () => {
    if (!token || user?.role !== "admin") return;
    setPluginLoading(true);
    setPluginError(null);
    try {
      const [definitions, instances] = await Promise.all([
        apiFetch<PluginDefinition[]>("/api/v1/plugins/definitions", { token }),
        apiFetch<PluginInstance[]>("/api/v1/plugins/", { token }),
      ]);
      setPluginDefinitions(definitions);
      setPluginInstances(instances);
    } catch (err) {
      const msg = formatError(err);
      setPluginError(msg);
      pushToast({ title: "Не удалось загрузить плагины", description: msg, variant: "error" });
    } finally {
      setPluginLoading(false);
    }
  };

  const loadAudit = async () => {
    if (!token || user?.role !== "admin") return;
    setAuditLoading(true);
    setAuditError(null);
    try {
      const params = new URLSearchParams();
      params.set("limit", String(auditLimit));
      if (auditAction.trim()) params.set("action", auditAction.trim());
      if (auditEntityType.trim()) params.set("entity_type", auditEntityType.trim());
      if (auditActor.trim()) params.set("actor", auditActor.trim());
      if (auditSourceIp.trim()) params.set("source_ip", auditSourceIp.trim());
      const items = await apiFetch<AuditEvent[]>(`/api/v1/audit/?${params.toString()}`, { token });
      setAudit(items);
    } catch (err) {
      const msg = formatError(err);
      setAuditError(msg);
      pushToast({ title: "Не удалось загрузить audit log", description: msg, variant: "error" });
    } finally {
      setAuditLoading(false);
    }
  };

  useEffect(() => {
    loadAudit().catch(() => undefined);
    loadUsers().catch(() => undefined);
    loadGroups().catch(() => undefined);
    loadProjects().catch(() => undefined);
    loadNotifications().catch(() => undefined);
    loadAdminSettings().catch(() => undefined);
    loadPlugins().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, user?.role]);

  useEffect(() => {
    if (pluginEditId) return;
    if (!availablePluginDefinitions.length) return;
    const exists = availablePluginDefinitions.some((item) => item.id === pluginDefinitionId);
    if (!exists) {
      setPluginDefinitionId(availablePluginDefinitions[0].id);
    }
  }, [availablePluginDefinitions, pluginDefinitionId, pluginEditId]);

  const resetPluginForm = () => {
    setPluginEditId(null);
    setPluginName("");
    setPluginType("inventory");
    const defaults = pluginDefinitions.filter((item) => item.type === "inventory");
    setPluginDefinitionId(defaults[0]?.id ?? "");
    setPluginEnabled(true);
    setPluginDefault(false);
    setPluginConfig("{\n  \n}");
  };

  const parsePluginConfig = () => {
    if (!pluginConfig.trim()) return {};
    return JSON.parse(pluginConfig);
  };

  const handlePluginSubmit = async () => {
    if (!token || user?.role !== "admin") return;
    let parsedConfig: Record<string, unknown>;
    try {
      parsedConfig = parsePluginConfig();
    } catch (err) {
      pushToast({ title: "Неверный JSON конфигурации", description: formatError(err), variant: "error" });
      return;
    }
    if (!pluginName.trim()) {
      pushToast({ title: "Укажите название плагина", variant: "warning" });
      return;
    }
    if (!pluginDefinitionId) {
      pushToast({ title: "Выберите definition", variant: "warning" });
      return;
    }
    try {
      if (pluginEditId) {
        await apiFetch<PluginInstance>(`/api/v1/plugins/${pluginEditId}`, {
          method: "PUT",
          token,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: pluginName,
            enabled: pluginEnabled,
            is_default: pluginDefault,
            config: parsedConfig,
          }),
        });
        pushToast({ title: "Плагин обновлен", variant: "success" });
      } else {
        await apiFetch<PluginInstance>("/api/v1/plugins/", {
          method: "POST",
          token,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: pluginName,
            type: pluginType,
            definition_id: pluginDefinitionId,
            enabled: pluginEnabled,
            is_default: pluginDefault,
            config: parsedConfig,
          }),
        });
        pushToast({ title: "Плагин создан", variant: "success" });
      }
      resetPluginForm();
      await loadPlugins();
    } catch (err) {
      const msg = formatError(err);
      setPluginError(msg);
      pushToast({ title: "Ошибка сохранения плагина", description: msg, variant: "error" });
    }
  };

  const startPluginEdit = (instance: PluginInstance) => {
    setPluginEditId(instance.id);
    setPluginName(instance.name);
    setPluginType(instance.type);
    setPluginDefinitionId(instance.definition_id);
    setPluginEnabled(instance.enabled);
    setPluginDefault(instance.is_default);
    setPluginConfig(JSON.stringify(instance.config ?? {}, null, 2));
  };

  const deletePluginInstance = async (instance: PluginInstance) => {
    if (!token || user?.role !== "admin") return;
    const ok = await confirm({
      title: "Удалить плагин?",
      description: `Удалить ${instance.name}? Это не удалит данные, только конфигурацию плагина.`,
      confirmText: "Удалить",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await apiFetch(`/api/v1/plugins/${instance.id}`, { method: "DELETE", token });
      pushToast({ title: "Плагин удален", variant: "success" });
      await loadPlugins();
    } catch (err) {
      const msg = formatError(err);
      pushToast({ title: "Не удалось удалить плагин", description: msg, variant: "error" });
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    try {
      await login(email, password);
      pushToast({ title: "Вход выполнен", description: email, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      pushToast({ title: "Ошибка входа", description: msg, variant: "error" });
    }
  };

  const createUser = async () => {
    if (!token || user?.role !== "admin") return;
    setUsersError(null);
    try {
      const created = await apiFetch<UserItem>("/api/v1/users/", {
        method: "POST",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: newUserEmail,
          password: newUserPassword,
          role: newUserRole,
          allowed_environments: newEnvRestricted ? newAllowedEnvironments : null,
          allowed_group_ids: newGroupsRestricted ? newAllowedGroupIds : null,
          allowed_project_ids: newProjectsRestricted ? newAllowedProjectIds : null,
        }),
      });
      setUsers((prev) => [...prev, created].sort((a, b) => a.id - b.id));
      setNewUserEmail("");
      setNewUserPassword("");
      setNewUserRole("user");
      setNewEnvRestricted(false);
      setNewAllowedEnvironments([]);
      setNewGroupsRestricted(false);
      setNewAllowedGroupIds([]);
      setNewProjectsRestricted(false);
      setNewAllowedProjectIds([]);
      pushToast({ title: "Пользователь создан", description: created.email, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setUsersError(msg);
      pushToast({ title: "Ошибка создания пользователя", description: msg, variant: "error" });
    }
  };

  const updateUserRole = async (u: UserItem, role: UserRole) => {
    if (!token || user?.role !== "admin") return;
    setUsersError(null);
    try {
      const updated = await apiFetch<UserItem>(`/api/v1/users/${u.id}`, {
        method: "PUT",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      });
      setUsers((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      pushToast({ title: "Роль обновлена", description: `${updated.email} → ${updated.role}`, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setUsersError(msg);
      pushToast({ title: "Ошибка обновления роли", description: msg, variant: "error" });
    }
  };

  const resetNotificationForm = () => {
    setNotifEditId(null);
    setNotifName("");
    setNotifType("webhook");
    setNotifUrl("");
    setNotifSecret("");
    setNotifEnabled(true);
    setNotifEvents([]);
  };

  const submitNotification = async () => {
    if (!token || user?.role !== "admin") return;
    setNotificationError(null);
    try {
      const payload = {
        name: notifName,
        type: notifType,
        url: notifUrl,
        secret: notifSecret || null,
        enabled: notifEnabled,
        events: notifEvents,
      };
      const url = notifEditId ? `/api/v1/notifications/${notifEditId}` : "/api/v1/notifications/";
      const method = notifEditId ? "PUT" : "POST";
      const saved = await apiFetch<NotificationEndpoint>(url, {
        method,
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setNotificationEndpoints((prev) => {
        if (notifEditId) {
          return prev.map((x) => (x.id === saved.id ? saved : x));
        }
        return [saved, ...prev];
      });
      resetNotificationForm();
      pushToast({ title: notifEditId ? "Webhook обновлён" : "Webhook создан", description: saved.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setNotificationError(msg);
      pushToast({ title: "Ошибка сохранения webhook", description: msg, variant: "error" });
    }
  };

  const editNotification = (item: NotificationEndpoint) => {
    setNotifEditId(item.id);
    setNotifName(item.name);
    setNotifType(item.type);
    setNotifUrl(item.url);
    setNotifSecret(item.secret ?? "");
    setNotifEnabled(Boolean(item.enabled));
    setNotifEvents(item.events ?? []);
  };

  const deleteNotification = async (item: NotificationEndpoint) => {
    if (!token || user?.role !== "admin") return;
    const ok = await confirm({
      title: "Удалить webhook?",
      description: `Будет удалён webhook "${item.name}".`,
      confirmText: "Удалить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!ok) return;
    try {
      await apiFetch<void>(`/api/v1/notifications/${item.id}`, { method: "DELETE", token });
      setNotificationEndpoints((prev) => prev.filter((x) => x.id !== item.id));
      pushToast({ title: "Webhook удалён", description: item.name, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setNotificationError(msg);
      pushToast({ title: "Ошибка удаления webhook", description: msg, variant: "error" });
    }
  };

  const exportAuditJson = () => {
    const payload = JSON.stringify(audit, null, 2);
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `audit-${new Date().toISOString()}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const exportAuditCsv = () => {
    const headers = ["id", "created_at", "actor", "actor_role", "action", "entity_type", "entity_id", "success", "source_ip", "meta"];
    const rows = audit.map((item) => [
      item.id,
      item.created_at,
      item.actor,
      item.actor_role ?? "",
      item.action,
      item.entity_type ?? "",
      item.entity_id ?? "",
      item.success ? "yes" : "no",
      item.source_ip ?? "",
      JSON.stringify(item.meta ?? {}),
    ]);
    const csv = [headers.join(","), ...rows.map((row) => row.map((cell) => `"${String(cell).replaceAll("\"", "\"\"")}"`).join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `audit-${new Date().toISOString()}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const saveAdminSettings = async () => {
    if (!token || user?.role !== "admin") return;
    setAdminSettingsError(null);
    try {
      const payload: Partial<GlobalSettings> = {
        maintenance_mode: maintenanceMode,
        banner_message: bannerMessage.trim() ? bannerMessage.trim() : null,
        banner_level: bannerLevel,
        default_project_id: defaultProjectId.trim() ? Number(defaultProjectId) : null,
      };
      const updated = await apiFetch<GlobalSettings>("/api/v1/admin/settings/", {
        method: "PUT",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setAdminSettings(updated);
      pushToast({ title: "Глобальные настройки сохранены", variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setAdminSettingsError(msg);
      pushToast({ title: "Ошибка сохранения", description: msg, variant: "error" });
    }
  };

  const resetUserPassword = async (u: UserItem) => {
    if (!token || user?.role !== "admin") return;
    const ok = await confirm({
      title: "Сбросить пароль?",
      description: `Будет установлен новый пароль для ${u.email}.`,
      confirmText: "Продолжить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!ok) return;
    const newPwd = window.prompt("Введите новый пароль (минимум 6 символов):", "");
    if (!newPwd) return;
    try {
      const updated = await apiFetch<UserItem>(`/api/v1/users/${u.id}`, {
        method: "PUT",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: newPwd }),
      });
      setUsers((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      pushToast({ title: "Пароль обновлён", description: updated.email, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setUsersError(msg);
      pushToast({ title: "Ошибка обновления пароля", description: msg, variant: "error" });
    }
  };

  const deleteUser = async (u: UserItem) => {
    if (!token || user?.role !== "admin") return;
    const ok = await confirm({
      title: "Удалить пользователя?",
      description: `Будет удалён пользователь ${u.email}.`,
      confirmText: "Удалить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!ok) return;
    try {
      await apiFetch<void>(`/api/v1/users/${u.id}`, { method: "DELETE", token });
      setUsers((prev) => prev.filter((x) => x.id !== u.id));
      pushToast({ title: "Пользователь удалён", description: u.email, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setUsersError(msg);
      pushToast({ title: "Ошибка удаления пользователя", description: msg, variant: "error" });
    }
  };

  const createProject = async () => {
    if (!token || user?.role !== "admin") return;
    setProjectsError(null);
    try {
      const created = await apiFetch<ProjectItem>("/api/v1/projects/", {
        method: "POST",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newProjectName, description: newProjectDescription || null }),
      });
      setProjects((prev) => [...prev, created].sort((a, b) => a.id - b.id));
      setNewProjectName("");
      setNewProjectDescription("");
      pushToast({ title: "Проект создан", description: `${created.name} (#${created.id})`, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setProjectsError(msg);
      pushToast({ title: "Ошибка создания проекта", description: msg, variant: "error" });
    }
  };

  const editProject = async (p: ProjectItem) => {
    if (!token || user?.role !== "admin") return;
    const nextName = window.prompt("Название проекта:", p.name);
    if (!nextName) return;
    const nextDescription = window.prompt("Описание (можно пусто):", p.description ?? "") ?? "";
    setProjectsError(null);
    try {
      const updated = await apiFetch<ProjectItem>(`/api/v1/projects/${p.id}`, {
        method: "PUT",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nextName, description: nextDescription || null }),
      });
      setProjects((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      pushToast({ title: "Проект обновлён", description: `${updated.name} (#${updated.id})`, variant: "success" });
    } catch (err) {
      const msg = formatError(err);
      setProjectsError(msg);
      pushToast({ title: "Ошибка обновления проекта", description: msg, variant: "error" });
    }
  };

  const deleteProject = async (p: ProjectItem) => {
    if (!token || user?.role !== "admin") return;
    const ok = await confirm({
      title: "Удалить проект?",
      description: `Будет удалён проект ${p.name} (#${p.id}) и все сущности внутри него (hosts/groups/secrets/playbooks/runs).`,
      confirmText: "Удалить",
      cancelText: "Отмена",
      danger: true,
    });
    if (!ok) return;
    setProjectsError(null);
    try {
      await apiFetch<void>(`/api/v1/projects/${p.id}`, { method: "DELETE", token });
      setProjects((prev) => prev.filter((x) => x.id !== p.id));
      const currentId = getProjectId();
      if (currentId === p.id) {
        setProjectId(1);
        pushToast({ title: "Текущий проект изменён", description: "Возврат к default", variant: "warning" });
        window.location.reload();
      } else {
        pushToast({ title: "Проект удалён", description: `${p.name} (#${p.id})`, variant: "success" });
      }
    } catch (err) {
      const msg = formatError(err);
      setProjectsError(msg);
      pushToast({ title: "Ошибка удаления проекта", description: msg, variant: "error" });
    }
  };

  const openAccessEditor = (u: UserItem) => {
    setAccessUserId(u.id);
    const envs = u.allowed_environments;
    setAccessEnvRestricted(envs !== null && envs !== undefined);
    setAccessEnvironments(envs ?? []);
    const gids = u.allowed_group_ids;
    setAccessGroupsRestricted(gids !== null && gids !== undefined);
    setAccessGroupIds(gids ?? []);
    const pids = u.allowed_project_ids;
    setAccessProjectsRestricted(pids !== null && pids !== undefined);
    setAccessProjectIds(pids ?? []);
  };

  const resetAccessEditor = () => {
    setAccessUserId(null);
    setAccessEnvRestricted(false);
    setAccessEnvironments([]);
    setAccessGroupsRestricted(false);
    setAccessGroupIds([]);
    setAccessProjectsRestricted(false);
    setAccessProjectIds([]);
  };

  const saveAccessEditor = async () => {
    if (!token || user?.role !== "admin" || !selectedAccessUser) return;
    setAccessSaving(true);
    setUsersError(null);
    try {
      const updated = await apiFetch<UserItem>(`/api/v1/users/${selectedAccessUser.id}`, {
        method: "PUT",
        token,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          allowed_environments: accessEnvRestricted ? accessEnvironments : null,
          allowed_group_ids: accessGroupsRestricted ? accessGroupIds : null,
          allowed_project_ids: accessProjectsRestricted ? accessProjectIds : null,
        }),
      });
      setUsers((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      pushToast({ title: "Ограничения обновлены", description: updated.email, variant: "success" });
      openAccessEditor(updated);
    } catch (err) {
      const msg = formatError(err);
      setUsersError(msg);
      pushToast({ title: "Ошибка сохранения ограничений", description: msg, variant: "error" });
    } finally {
      setAccessSaving(false);
    }
  };

  const summarizeScope = (u: UserItem) => {
    const env = u.allowed_environments;
    const groups = u.allowed_group_ids;
    const projects = u.allowed_project_ids;
    const envLabel = env === null || env === undefined ? "env: все" : env.length ? `env: ${env.join(",")}` : "env: нет";
    const groupsLabel =
      groups === null || groups === undefined ? "groups: все" : groups.length ? `groups: ${groups.join(",")}` : "groups: нет";
    const projectsLabel =
      projects === null || projects === undefined
        ? "projects: все"
        : projects.length
          ? `projects: ${projects.join(",")}`
          : "projects: нет";
    return `${envLabel}; ${groupsLabel}; ${projectsLabel}`;
  };

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <p className="page-kicker">Учетные записи</p>
          <h1>Настройки</h1>
        </div>
      </header>

      <div className="tabs">
        <button
          type="button"
          className={`tab-button ${settingsTab === "session" ? "active" : ""}`}
          onClick={() => setSettingsTab("session")}
        >
          Сессия
        </button>
        <button
          type="button"
          className={`tab-button ${settingsTab === "projects" ? "active" : ""}`}
          onClick={() => setSettingsTab("projects")}
        >
          Проекты
        </button>
        {user?.role === "admin" && (
          <>
            <button
              type="button"
              className={`tab-button ${settingsTab === "users" ? "active" : ""}`}
              onClick={() => setSettingsTab("users")}
            >
              Пользователи
            </button>
            <button
              type="button"
              className={`tab-button ${settingsTab === "audit" ? "active" : ""}`}
              onClick={() => setSettingsTab("audit")}
            >
              Audit log
            </button>
            <button
              type="button"
              className={`tab-button ${settingsTab === "notifications" ? "active" : ""}`}
              onClick={() => setSettingsTab("notifications")}
            >
              Notifications
            </button>
            <button
              type="button"
              className={`tab-button ${settingsTab === "plugins" ? "active" : ""}`}
              onClick={() => setSettingsTab("plugins")}
            >
              Плагины
            </button>
            <button
              type="button"
              className={`tab-button ${settingsTab === "admin" ? "active" : ""}`}
              onClick={() => setSettingsTab("admin")}
            >
              Администрирование
            </button>
          </>
        )}
      </div>

      <div className="grid">
          {settingsTab === "session" && (
          <div className="panel">
            <h2>Сессия</h2>
            {status === "authenticated" && user ? (
              <div className="stack">
                <p>
                  Вы вошли как <strong>{user.email}</strong> ({user.role})
                </p>
                <label>
                  Режим таблиц
                  <select value={compactTables ? "compact" : "spacious"} onChange={(e) => setCompactTables(e.target.value === "compact")}>
                    <option value="spacious">просторный</option>
                    <option value="compact">компактный</option>
                  </select>
                  <span className="form-helper">Компактный режим уменьшает отступы и плотность таблиц.</span>
                </label>
                <button className="ghost-button" type="button" onClick={logout}>
                  Выйти
                </button>
              </div>
          ) : (
            <>
              <p>Для работы с Hosts/Secrets требуется токен.</p>
              {error && <p className="text-error">{error}</p>}
              <form className="form-stack" onSubmit={handleSubmit}>
                <label>
                  Email
                  <input value={email} onChange={(e) => setEmail(e.target.value)} />
                </label>
                <label>
                  Пароль
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </label>
                <button className="primary-button" type="submit" disabled={status === "loading"}>
                  {status === "loading" ? "Входим..." : "Войти"}
                </button>
              </form>
              <p className="form-helper">
                Демо-учетка: <code>admin@it.local</code> / <code>admin123</code>
              </p>
            </>
          )}
        </div>
        )}

        {settingsTab === "projects" && status === "authenticated" && token && (
          <div className="panel">
            <div className="panel-title">
              <h2>Проекты</h2>
              <p className="form-helper">Проект влияет на Hosts/Groups/Secrets/Automation (изоляция данных).</p>
            </div>
            <div className="row-actions">
              <button type="button" className="ghost-button" onClick={() => loadProjects()}>
                Обновить
              </button>
            </div>
            {projectsLoading && <p>Загружаем...</p>}
            {projectsError && <p className="text-error">{projectsError}</p>}
            {projects.length > 0 && (
              <div className="form-stack" style={{ marginTop: 0 }}>
                <label>
                  Текущий проект
                  <select
                    value={String(getProjectId() ?? 1)}
                    onChange={(e) => {
                      const id = Number(e.target.value);
                      setProjectId(Number.isFinite(id) && id > 0 ? id : 1);
                    }}
                  >
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} (#{p.id})
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}

            {user?.role === "admin" && (
              <>
                <div className="panel" style={{ marginTop: "1rem" }}>
                  <div className="panel-title">
                    <h3 style={{ margin: 0 }}>Создать проект</h3>
                    <p className="form-helper">Удаление проекта удаляет все сущности внутри него.</p>
                  </div>
                  <div className="form-stack" style={{ marginTop: 0 }}>
                    <label>
                      Название
                      <input value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)} placeholder="например: prod" />
                    </label>
                    <label>
                      Описание
                      <input value={newProjectDescription} onChange={(e) => setNewProjectDescription(e.target.value)} placeholder="опционально" />
                    </label>
                    <button className="primary-button" type="button" onClick={() => createProject()} disabled={newProjectName.trim().length < 2}>
                      Создать
                    </button>
                  </div>
                </div>

                {projects.length > 0 && (
                  <div className="table-scroll" tabIndex={0} aria-label="Список проектов" style={{ marginTop: "1rem" }}>
                    <table className="hosts-table">
                      <thead>
                        <tr>
                          <th>ID</th>
                          <th>Название</th>
                          <th>Создан</th>
                          <th>Действия</th>
                        </tr>
                      </thead>
                      <tbody>
                        {projects.map((p) => (
                          <tr key={p.id}>
                            <td>{p.id}</td>
                            <td>
                              <strong>{p.name}</strong>
                              {p.description ? <div className="form-helper">{p.description}</div> : null}
                            </td>
                            <td>{new Date(p.created_at).toLocaleString()}</td>
                            <td>
                              <div className="row-actions">
                                <button
                                  type="button"
                                  className="ghost-button"
                                  onClick={() => {
                                    setProjectId(p.id);
                                    window.location.reload();
                                  }}
                                  disabled={(getProjectId() ?? 1) === p.id}
                                >
                                  Текущий
                                </button>
                                <button type="button" className="ghost-button" onClick={() => editProject(p)}>
                                  Редактировать
                                </button>
                                <button
                                  type="button"
                                  className="ghost-button"
                                  onClick={() => deleteProject(p)}
                                  disabled={p.id === 1}
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
              </>
            )}
          </div>
        )}

        {settingsTab === "users" && status === "authenticated" && user?.role === "admin" && (
          <div className="panel">
            <div className="panel-title">
              <h2>Пользователи</h2>
              <p className="form-helper">Управление учетными записями (RBAC).</p>
            </div>
            <div className="row-actions">
              <button type="button" className="ghost-button" onClick={() => loadUsers()}>
                Обновить
              </button>
            </div>
            {usersLoading && <p>Загружаем...</p>}
            {usersError && <p className="text-error">{usersError}</p>}
            {!usersLoading && users.length === 0 && <p>Пользователей пока нет</p>}
            {users.length > 0 && (
              <div className="table-scroll" tabIndex={0} aria-label="Таблица пользователей">
                <table className="hosts-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Email</th>
                      <th>Роль</th>
                      <th>Доступ</th>
                      <th>Создан</th>
                      <th>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id}>
                        <td>{u.id}</td>
                        <td>{u.email}</td>
                        <td>
                          <select
                            value={u.role}
                            onChange={(e) => updateUserRole(u, e.target.value as UserRole)}
                            aria-label={`Роль для ${u.email}`}
                          >
                            <option value="admin">админ</option>
                            <option value="operator">оператор</option>
                            <option value="viewer">viewer</option>
                            <option value="automation-only">automation-only</option>
                            <option value="user">user (legacy)</option>
                          </select>
                        </td>
                        <td>
                          <span className="form-helper" style={{ marginTop: 0 }}>
                            {summarizeScope(u)}
                          </span>
                        </td>
                        <td>{new Date(u.created_at).toLocaleString()}</td>
                        <td>
                          <div className="row-actions">
                            <button type="button" className="ghost-button" onClick={() => openAccessEditor(u)}>
                              Доступ
                            </button>
                            <button type="button" className="ghost-button" onClick={() => resetUserPassword(u)}>
                              Сбросить пароль
                            </button>
                            <button type="button" className="ghost-button" onClick={() => deleteUser(u)}>
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

            {selectedAccessUser && (
              <div className="panel" style={{ marginTop: "1rem" }}>
                <div className="panel-title">
                  <h2>Ограничения доступа</h2>
                  <p className="form-helper">Пользователь: {selectedAccessUser.email}</p>
                </div>

                <div className="form-stack" style={{ marginTop: 0 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={accessEnvRestricted}
                      onChange={(e) => setAccessEnvRestricted(e.target.checked)}
                    />
                    Ограничить по environment
                  </label>
                  {accessEnvRestricted && (
                    <label>
                      Разрешённые environments
                      <select
                        multiple
                        className="multi-select"
                        value={accessEnvironments}
                        onChange={(e) => setAccessEnvironments(Array.from(e.target.selectedOptions).map((o) => o.value))}
                      >
                        {ENV_OPTIONS.map((env) => (
                          <option key={env} value={env}>
                            {env}
                          </option>
                        ))}
                      </select>
                      <span className="form-helper">Если список пуст — доступа к хостам/группам не будет.</span>
                    </label>
                  )}

                  <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={accessGroupsRestricted}
                      onChange={(e) => setAccessGroupsRestricted(e.target.checked)}
                    />
                    Ограничить по группам хостов
                  </label>
                  {accessGroupsRestricted && (
                    <label>
                      Разрешённые группы
                      <select
                        multiple
                        className="multi-select"
                        value={accessGroupIds.map(String)}
                        onChange={(e) => setAccessGroupIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
                      >
                        {groups.map((g) => (
                          <option key={g.id} value={g.id}>
                            {g.name} (#{g.id}, {g.type})
                          </option>
                        ))}
                      </select>
                      <span className="form-helper">Если список пуст — доступа к хостам/группам не будет.</span>
                    </label>
                  )}

                  <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={accessProjectsRestricted}
                      onChange={(e) => setAccessProjectsRestricted(e.target.checked)}
                    />
                    Ограничить по проектам
                  </label>
                  {accessProjectsRestricted && (
                    <label>
                      Разрешённые проекты
                      <select
                        multiple
                        className="multi-select"
                        value={accessProjectIds.map(String)}
                        onChange={(e) => setAccessProjectIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
                      >
                        {projects.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name} (#{p.id})
                          </option>
                        ))}
                      </select>
                      <span className="form-helper">Если список пуст — доступа к проектам не будет.</span>
                    </label>
                  )}

                  <div className="form-actions">
                    <button type="button" className="primary-button" onClick={saveAccessEditor} disabled={accessSaving}>
                      {accessSaving ? "Сохраняем..." : "Сохранить"}
                    </button>
                    <button type="button" className="ghost-button" onClick={resetAccessEditor} disabled={accessSaving}>
                      Закрыть
                    </button>
                  </div>
                </div>
              </div>
            )}

            <div className="panel" style={{ marginTop: "1rem" }}>
              <div className="panel-title">
                <h2>Создать пользователя</h2>
                <p className="form-helper">Пароль хранится как bcrypt hash.</p>
              </div>
              <div className="form-stack" style={{ marginTop: 0 }}>
                <label>
                  Email
                  <input value={newUserEmail} onChange={(e) => setNewUserEmail(e.target.value)} placeholder="user@example.com" />
                </label>
                <label>
                  Пароль
                  <input type="password" value={newUserPassword} onChange={(e) => setNewUserPassword(e.target.value)} placeholder="минимум 6 символов" />
                </label>
                <label>
                  Роль
                  <select
                    value={newUserRole}
                    onChange={(e) => setNewUserRole(e.target.value as UserRole)}
                    aria-label="Роль для нового пользователя"
                  >
                    <option value="admin">админ</option>
                    <option value="operator">оператор</option>
                    <option value="viewer">viewer</option>
                    <option value="automation-only">automation-only</option>
                    <option value="user">user (legacy)</option>
                  </select>
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input type="checkbox" checked={newEnvRestricted} onChange={(e) => setNewEnvRestricted(e.target.checked)} />
                  Ограничить по environment
                </label>
                {newEnvRestricted && (
                  <label>
                    Разрешённые environments
                    <select
                      multiple
                      className="multi-select"
                      value={newAllowedEnvironments}
                      onChange={(e) => setNewAllowedEnvironments(Array.from(e.target.selectedOptions).map((o) => o.value))}
                    >
                      {ENV_OPTIONS.map((env) => (
                        <option key={env} value={env}>
                          {env}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input type="checkbox" checked={newGroupsRestricted} onChange={(e) => setNewGroupsRestricted(e.target.checked)} />
                  Ограничить по группам хостов
                </label>
                {newGroupsRestricted && (
                  <label>
                    Разрешённые группы
                    <select
                      multiple
                      className="multi-select"
                      value={newAllowedGroupIds.map(String)}
                      onChange={(e) => setNewAllowedGroupIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
                    >
                      {groups.map((g) => (
                        <option key={g.id} value={g.id}>
                          {g.name} (#{g.id}, {g.type})
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={newProjectsRestricted}
                    onChange={(e) => setNewProjectsRestricted(e.target.checked)}
                  />
                  Ограничить по проектам
                </label>
                {newProjectsRestricted && (
                  <label>
                    Разрешённые проекты
                    <select
                      multiple
                      className="multi-select"
                      value={newAllowedProjectIds.map(String)}
                      onChange={(e) => setNewAllowedProjectIds(Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}
                    >
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} (#{p.id})
                        </option>
                      ))}
                    </select>
                    <span className="form-helper">Если список пуст — доступа к проектам не будет.</span>
                  </label>
                )}
                <button className="primary-button" type="button" onClick={() => createUser()} disabled={!newUserEmail || newUserPassword.length < 6}>
                  Создать
                </button>
              </div>
            </div>
          </div>
        )}

        {settingsTab === "audit" && status === "authenticated" && user?.role === "admin" && (
          <div className="panel">
            <div className="panel-title">
              <h2>Audit log</h2>
              <p className="form-helper">События CRUD/SSH/Automation (без содержимого команд и секретов).</p>
            </div>
            <div className="row-actions">
              <button type="button" className="ghost-button" onClick={() => loadAudit()}>
                Обновить
              </button>
              <button type="button" className="ghost-button" onClick={exportAuditJson} disabled={audit.length === 0}>
                Экспорт JSON
              </button>
              <button type="button" className="ghost-button" onClick={exportAuditCsv} disabled={audit.length === 0}>
                Экспорт CSV
              </button>
            </div>
            <div className="grid" style={{ marginTop: "0.75rem" }}>
              <label>
                Action
                <input value={auditAction} onChange={(e) => setAuditAction(e.target.value)} placeholder="host.update" />
              </label>
              <label>
                Entity type
                <input value={auditEntityType} onChange={(e) => setAuditEntityType(e.target.value)} placeholder="host/secret" />
              </label>
              <label>
                Actor
                <input value={auditActor} onChange={(e) => setAuditActor(e.target.value)} placeholder="admin@it.local" />
              </label>
              <label>
                Source IP
                <input value={auditSourceIp} onChange={(e) => setAuditSourceIp(e.target.value)} placeholder="10.0.0.1" />
              </label>
              <label>
                Limit
                <input
                  type="number"
                  min={10}
                  max={500}
                  value={auditLimit}
                  onChange={(e) => setAuditLimit(Number(e.target.value))}
                />
              </label>
              <div className="row-actions" style={{ alignItems: "flex-end" }}>
                <button type="button" className="ghost-button" onClick={() => loadAudit()}>
                  Применить
                </button>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => {
                    setAuditAction("");
                    setAuditEntityType("");
                    setAuditActor("");
                    setAuditSourceIp("");
                    setAuditLimit(100);
                  }}
                >
                  Сброс
                </button>
              </div>
            </div>
            {auditLoading && <p>Загружаем...</p>}
            {auditError && <p className="text-error">{auditError}</p>}
            {!auditLoading && audit.length === 0 && <p>Событий пока нет</p>}
            {audit.length > 0 && (
              <div className="table-scroll" tabIndex={0} aria-label="Audit log">
                <table className="hosts-table">
                  <thead>
                    <tr>
                      <th>Время</th>
                      <th>Actor</th>
                      <th>Action</th>
                      <th>Entity</th>
                      <th>OK</th>
                      <th>Source IP</th>
                      <th>Meta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.map((e) => (
                      <tr key={e.id}>
                        <td>{new Date(e.created_at).toLocaleString()}</td>
                        <td>
                          {e.actor} {e.actor_role ? `(${e.actor_role})` : ""}
                        </td>
                        <td>{e.action}</td>
                        <td>
                          {e.entity_type ?? ""} {e.entity_id ? `#${e.entity_id}` : ""}
                        </td>
                        <td>{e.success ? "yes" : "no"}</td>
                        <td>{e.source_ip ?? "—"}</td>
                        <td>
                          {Object.keys(e.meta ?? {}).length > 0 ? (
                            <details>
                              <summary>meta</summary>
                              <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(e.meta, null, 2)}</pre>
                            </details>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {settingsTab === "notifications" && status === "authenticated" && user?.role === "admin" && (
          <div className="panel">
            <div className="panel-title">
              <h2>Notifications (webhook)</h2>
              <p className="form-helper">Отправка событий на внешние сервисы (Slack/Telegram через webhook шлюз).</p>
            </div>
            <div className="row-actions">
              <button type="button" className="ghost-button" onClick={() => loadNotifications()}>
                Обновить
              </button>
            </div>
            {notificationLoading && <p>Загружаем...</p>}
            {notificationError && <p className="text-error">{notificationError}</p>}
            {notificationEndpoints.length === 0 && !notificationLoading && <p>Webhook endpoints пока нет</p>}
            {notificationEndpoints.length > 0 && (
              <div className="table-scroll" tabIndex={0} aria-label="Notification endpoints">
                <table className="hosts-table">
                  <thead>
                    <tr>
                      <th>Название</th>
                      <th>Тип</th>
                      <th>URL</th>
                      <th>События</th>
                      <th>Статус</th>
                      <th>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {notificationEndpoints.map((item) => (
                      <tr key={item.id}>
                        <td>{item.name}</td>
                        <td>{item.type}</td>
                        <td className="truncate">{item.url}</td>
                        <td>{item.events?.length ? item.events.join(", ") : "all"}</td>
                        <td>{item.enabled ? "enabled" : "disabled"}</td>
                        <td>
                          <div className="row-actions">
                            <button type="button" className="ghost-button" onClick={() => editNotification(item)}>
                              Редактировать
                            </button>
                            <button type="button" className="ghost-button" onClick={() => deleteNotification(item)}>
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

            <div className="panel" style={{ marginTop: "1rem" }}>
              <div className="panel-title">
                <h2>{notifEditId ? "Редактировать webhook" : "Создать webhook"}</h2>
              </div>
              <div className="form-stack">
                <label>
                  Название
                  <input value={notifName} onChange={(e) => setNotifName(e.target.value)} required />
                </label>
                <label>
                  Тип
                  <select value={notifType} onChange={(e) => setNotifType(e.target.value)}>
                    <option value="webhook">webhook</option>
                    <option value="slack">slack</option>
                    <option value="telegram">telegram</option>
                    <option value="email">email</option>
                  </select>
                  <span className="form-helper">Slack/Telegram используют URL webhook; email — адрес получателя.</span>
                </label>
                <label>
                  URL
                  <input value={notifUrl} onChange={(e) => setNotifUrl(e.target.value)} required />
                  {notifType === "email" && <span className="form-helper">Пример: user@example.com</span>}
                </label>
                <label>
                  Secret (опционально)
                  <input value={notifSecret} onChange={(e) => setNotifSecret(e.target.value)} placeholder="X-Webhook-Secret" />
                </label>
                <label>
                  События
                  <select
                    multiple
                    value={notifEvents}
                    onChange={(e) => setNotifEvents(Array.from(e.target.selectedOptions).map((o) => o.value))}
                    style={{ minHeight: 140 }}
                  >
                    {NOTIFICATION_EVENTS.map((event) => (
                      <option key={event} value={event}>
                        {event}
                      </option>
                    ))}
                  </select>
                  <span className="form-helper">Если ничего не выбрано — будут отправляться все события.</span>
                </label>
                <label>
                  Статус
                  <select value={notifEnabled ? "enabled" : "disabled"} onChange={(e) => setNotifEnabled(e.target.value === "enabled")}>
                    <option value="enabled">enabled</option>
                    <option value="disabled">disabled</option>
                  </select>
                </label>
                <div className="row-actions">
                  <button type="button" className="primary-button" onClick={submitNotification} disabled={!notifName || !notifUrl}>
                    Сохранить
                  </button>
                  <button type="button" className="ghost-button" onClick={resetNotificationForm}>
                    Сброс
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {settingsTab === "plugins" && status === "authenticated" && user?.role === "admin" && (
          <div className="panel">
            <div className="panel-title">
              <h2>Plugins</h2>
              <p className="form-helper">Подключаемые backends для inventory/secrets/automation (MVP).</p>
            </div>
            <div className="row-actions">
              <button type="button" className="ghost-button" onClick={() => loadPlugins()}>
                Обновить
              </button>
            </div>
            {pluginLoading && <p>Загружаем...</p>}
            {pluginError && <p className="text-error">{pluginError}</p>}
            {!pluginLoading && pluginInstances.length === 0 && <p>Плагины пока не настроены</p>}
            {pluginInstances.length > 0 && (
              <div className="table-scroll" tabIndex={0} aria-label="Plugin instances">
                <table className="hosts-table">
                  <thead>
                    <tr>
                      <th>Название</th>
                      <th>Тип</th>
                      <th>Definition</th>
                      <th>Статус</th>
                      <th>Updated</th>
                      <th>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pluginInstances.map((item) => (
                      <tr key={item.id}>
                        <td>{item.name}</td>
                        <td>{item.type}</td>
                        <td>{item.definition_id}</td>
                        <td>
                          {item.enabled ? "enabled" : "disabled"}
                          {item.is_default ? " (default)" : ""}
                        </td>
                        <td>{item.updated_at ? new Date(item.updated_at).toLocaleString() : "—"}</td>
                        <td>
                          <div className="row-actions">
                            <button type="button" className="ghost-button" onClick={() => startPluginEdit(item)}>
                              Редактировать
                            </button>
                            <button type="button" className="ghost-button" onClick={() => deletePluginInstance(item)}>
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

            <div className="panel" style={{ marginTop: "1rem" }}>
              <div className="panel-title">
                <h2>{pluginEditId ? "Редактировать plugin instance" : "Создать plugin instance"}</h2>
                {selectedPluginDefinition?.description && (
                  <p className="form-helper">{selectedPluginDefinition.description}</p>
                )}
              </div>
              <div className="form-stack">
                <label>
                  Название
                  <input value={pluginName} onChange={(e) => setPluginName(e.target.value)} placeholder="prod-secrets" />
                </label>
                <label>
                  Тип
                  <select
                    value={pluginType}
                    onChange={(e) => setPluginType(e.target.value as PluginInstance["type"])}
                    disabled={pluginEditId !== null}
                  >
                    <option value="inventory">inventory</option>
                    <option value="secrets">secrets</option>
                    <option value="automation">automation</option>
                  </select>
                </label>
                <label>
                  Definition
                  <select
                    value={pluginDefinitionId}
                    onChange={(e) => setPluginDefinitionId(e.target.value)}
                    disabled={pluginEditId !== null}
                  >
                    {availablePluginDefinitions.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                  {!availablePluginDefinitions.length && <span className="form-helper">Нет доступных definitions для выбранного типа.</span>}
                </label>
                <label>
                  Config (JSON)
                  <textarea
                    rows={6}
                    value={pluginConfig}
                    onChange={(e) => setPluginConfig(e.target.value)}
                    spellCheck={false}
                  />
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={pluginEnabled} onChange={(e) => setPluginEnabled(e.target.checked)} />
                  <span>Enabled</span>
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={pluginDefault} onChange={(e) => setPluginDefault(e.target.checked)} />
                  <span>Default для выбранного типа</span>
                </label>
                <div className="row-actions">
                  <button type="button" className="primary-button" onClick={handlePluginSubmit}>
                    Сохранить
                  </button>
                  <button type="button" className="ghost-button" onClick={resetPluginForm}>
                    Сброс
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {settingsTab === "admin" && status === "authenticated" && user?.role === "admin" && (
          <div className="panel">
            <div className="panel-title">
              <h2>Глобальные настройки</h2>
              <p className="form-helper">Управление поведением всего IT Manager (admin-only).</p>
            </div>
            <div className="row-actions">
              <button type="button" className="ghost-button" onClick={() => loadAdminSettings()}>
                Обновить
              </button>
            </div>
            {adminSettingsLoading && <p>Загружаем...</p>}
            {adminSettingsError && <p className="text-error">{adminSettingsError}</p>}
            <div className="form-stack" style={{ marginTop: 0 }}>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={maintenanceMode}
                  onChange={(e) => setMaintenanceMode(e.target.checked)}
                />
                <span>Maintenance mode (информирует операторов)</span>
              </label>
              <label>
                Баннер (текст)
                <input value={bannerMessage} onChange={(e) => setBannerMessage(e.target.value)} placeholder="Плановые работы 22:00–23:00" />
              </label>
              <label>
                Уровень баннера
                <select value={bannerLevel} onChange={(e) => setBannerLevel(e.target.value as GlobalSettings["banner_level"])}>
                  <option value="info">info</option>
                  <option value="warning">warning</option>
                  <option value="error">error</option>
                </select>
              </label>
              <label>
                Default project ID
                <input
                  type="number"
                  min={1}
                  value={defaultProjectId}
                  onChange={(e) => setDefaultProjectId(e.target.value)}
                  placeholder="1"
                />
                <span className="form-helper">Используется как значение по умолчанию в UI (если задано).</span>
              </label>
              <div className="form-actions">
                <button type="button" className="primary-button" onClick={saveAdminSettings}>
                  Сохранить
                </button>
              </div>
              {adminSettings && (
                <p className="form-helper">Текущие: maintenance={String(adminSettings.maintenance_mode)}</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default SettingsPage;
