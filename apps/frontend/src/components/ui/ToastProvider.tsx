import { createContext, ReactNode, useCallback, useContext, useMemo, useRef, useState } from "react";

export type ToastVariant = "success" | "error" | "info" | "warning";

export type ToastInput = {
  title: string;
  description?: string;
  variant?: ToastVariant;
  durationMs?: number;
};

type ToastItem = Required<Pick<ToastInput, "title">> &
  Omit<ToastInput, "durationMs"> & {
    id: string;
    createdAt: number;
  };

type ToastContextValue = {
  pushToast: (toast: ToastInput) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timersRef = useRef<Record<string, number>>({});

  const remove = useCallback((id: string) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
    const t = timersRef.current[id];
    if (t) {
      window.clearTimeout(t);
      delete timersRef.current[id];
    }
  }, []);

  const pushToast = useCallback(
    (toast: ToastInput) => {
      const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const durationMs = toast.durationMs ?? (toast.variant === "error" ? 6000 : 3500);
      const item: ToastItem = {
        id,
        title: toast.title,
        description: toast.description,
        variant: toast.variant ?? "info",
        createdAt: Date.now(),
      };
      setItems((prev) => [item, ...prev].slice(0, 5));
      timersRef.current[id] = window.setTimeout(() => remove(id), durationMs);
    },
    [remove]
  );

  const value = useMemo(() => ({ pushToast }), [pushToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" role="region" aria-label="Уведомления">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.variant}`} role="status">
            <div className="toast-head">
              <div className="toast-title">{t.title}</div>
              <button type="button" className="toast-close" onClick={() => remove(t.id)} aria-label="Закрыть уведомление">
                ×
              </button>
            </div>
            {t.description && <div className="toast-desc">{t.description}</div>}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast должен использоваться внутри ToastProvider");
  }
  return ctx;
}

