const STORAGE_KEY = "it_manager_project_id";

export type Project = {
  id: number;
  name: string;
  description?: string | null;
  created_at: string;
};

export function getProjectId(): number | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  const id = Number(raw);
  return Number.isFinite(id) && id > 0 ? id : null;
}

export function setProjectId(id: number | null): void {
  if (!id) {
    localStorage.removeItem(STORAGE_KEY);
  } else {
    localStorage.setItem(STORAGE_KEY, String(id));
  }
  window.dispatchEvent(new CustomEvent("itmgr:project-change", { detail: { projectId: id } }));
}

export function getProjectHeaders(): Record<string, string> {
  const id = getProjectId();
  return id ? { "X-Project-Id": String(id) } : {};
}

