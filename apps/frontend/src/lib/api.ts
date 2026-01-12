import { getProjectHeaders } from "./project";

type ApiErrorDetails = {
  status: number;
  message: string;
  requestId?: string;
};

export class ApiError extends Error {
  details: ApiErrorDetails;

  constructor(details: ApiErrorDetails) {
    super(details.message);
    this.details = details;
  }
}

type ApiFetchOptions = Omit<RequestInit, "headers"> & {
  headers?: Record<string, string>;
  token?: string | null;
};

function newRequestId(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c && "randomUUID" in c && typeof c.randomUUID === "function") {
    return c.randomUUID();
  }
  return `web-${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
}

async function readErrorMessage(response: Response): Promise<string> {
  const text = (await response.text()) || "Ошибка API";
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) return text;
  try {
    const obj = JSON.parse(text) as { detail?: unknown; message?: unknown };
    if (typeof obj?.detail === "string") return obj.detail;
    if (typeof obj?.message === "string") return obj.message;
    return text;
  } catch {
    return text;
  }
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers ?? {}),
  };

  // Projects/Tenants: по умолчанию пробрасываем выбранный проект (если установлен).
  // Переопределить можно напрямую через options.headers["X-Project-Id"].
  if (!headers["X-Project-Id"] && !headers["x-project-id"]) {
    Object.assign(headers, getProjectHeaders());
  }

  if (!headers["X-Request-Id"] && !headers["x-request-id"]) {
    headers["X-Request-Id"] = newRequestId();
  }

  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  const response = await fetch(path, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    const requestId = response.headers.get("x-request-id") || undefined;
    throw new ApiError({ status: response.status, message, requestId });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
