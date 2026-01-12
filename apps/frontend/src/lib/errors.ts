import { ApiError } from "./api";

export function formatError(err: unknown): string {
  if (!err) return "Неизвестная ошибка";
  if (typeof err === "string") return err;

  if (err instanceof ApiError) {
    // backend может возвращать JSON со строкой detail; apiFetch сейчас отдаёт текст,
    // поэтому здесь максимально безопасно приводим к виду "HTTP 400: ..."
    const msg = err.details?.message || err.message || "Ошибка API";
    const rid = err.details?.requestId ? ` (request-id: ${err.details.requestId})` : "";
    return `HTTP ${err.details.status}: ${msg}${rid}`;
  }

  if (err instanceof Error) {
    // fetch network error обычно приходит как TypeError("Failed to fetch")
    if (err.name === "TypeError" && /Failed to fetch/i.test(err.message)) {
      return "Ошибка сети: backend недоступен или блокируется CORS";
    }
    return err.message || "Ошибка";
  }

  try {
    return JSON.stringify(err);
  } catch {
    return "Неизвестная ошибка";
  }
}
