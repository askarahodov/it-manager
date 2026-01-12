import { useEffect, useMemo, useState } from "react";

import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatError } from "../lib/errors";
import { getProjectId, Project, setProjectId } from "../lib/project";
import { useToast } from "./ui/ToastProvider";

type Props = {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
};

function pickDefaultProjectId(projects: Project[]): number | null {
  const def = projects.find((p) => p.name === "default");
  return def?.id ?? (projects[0]?.id ?? null);
}

function TopBar({ sidebarOpen, onToggleSidebar }: Props) {
  const { user, status, token } = useAuth();
  const { pushToast } = useToast();

  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(() => getProjectId());

  useEffect(() => {
    if (!token || status !== "authenticated") {
      setProjects([]);
      setProjectsError(null);
      return;
    }
    apiFetch<Project[]>("/api/v1/projects/", { token })
      .then((items) => {
        setProjects(items);
        setProjectsError(null);
        // Если проект не выбран или недоступен — установим default (чтобы всегда пробрасывать X-Project-Id).
        const current = getProjectId();
        const hasCurrent = current ? items.some((p) => p.id === current) : false;
        if (!current || !hasCurrent) {
          const id = pickDefaultProjectId(items);
          if (id) {
            setProjectId(id);
            setSelectedProjectId(id);
          }
        }
      })
      .catch((err) => {
        const msg = formatError(err);
        setProjectsError(msg);
      });
  }, [status, token]);

  const selectedProject = useMemo(
    () => (selectedProjectId ? projects.find((p) => p.id === selectedProjectId) ?? null : null),
    [projects, selectedProjectId]
  );

  const canSwitch = status === "authenticated" && Boolean(token) && projects.length > 0;

  return (
    <header className="top-bar">
      <div className="top-left">
        <button
          type="button"
          className={`ghost-button menu-toggle ${sidebarOpen ? "active" : ""}`}
          onClick={onToggleSidebar}
          aria-label="Открыть меню"
        >
          Меню
        </button>
        <div>IT Manager</div>
        <div className="top-project">
          <span className="top-project-label">Проект:</span>
          <select
            className="select"
            value={selectedProjectId ?? ""}
            onChange={(e) => {
              const value = e.target.value;
              const next = value ? Number(value) : null;
              setSelectedProjectId(next);
              setProjectId(next);
              pushToast({
                title: "Проект выбран",
                description: next ? `Текущий проект: ${projects.find((p) => p.id === next)?.name ?? next}` : "default",
                variant: "success",
              });
            }}
            disabled={!canSwitch}
            aria-label="Выбор проекта"
            title={projectsError ? `Ошибка загрузки проектов: ${projectsError}` : selectedProject?.name ?? ""}
          >
            {!canSwitch && <option value="">default</option>}
            {canSwitch && projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="status-pill">Alpha</div>
      <div className="top-user">{status === "authenticated" && user ? `${user.email} (${user.role})` : "не авторизован"}</div>
    </header>
  );
}

export default TopBar;
