import { createContext, ReactNode, useCallback, useContext, useMemo, useState } from "react";

export type ConfirmOptions = {
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
};

type ConfirmState = ConfirmOptions & {
  open: boolean;
  resolve?: (value: boolean) => void;
};

type ConfirmContextValue = {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
};

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ConfirmState>({
    open: false,
    title: "",
    description: "",
    confirmText: "Подтвердить",
    cancelText: "Отмена",
    danger: false,
  });

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setState({
        open: true,
        title: options.title,
        description: options.description,
        confirmText: options.confirmText ?? "Подтвердить",
        cancelText: options.cancelText ?? "Отмена",
        danger: Boolean(options.danger),
        resolve,
      });
    });
  }, []);

  const close = useCallback((value: boolean) => {
    setState((prev) => {
      prev.resolve?.(value);
      return { ...prev, open: false, resolve: undefined };
    });
  }, []);

  const value = useMemo(() => ({ confirm }), [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {state.open && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label={state.title}>
          <div className="modal">
            <div className="modal-header">
              <div className="modal-title">{state.title}</div>
            </div>
            {state.description && <div className="modal-desc">{state.description}</div>}
            <div className="modal-actions">
              <button type="button" className="ghost-button" onClick={() => close(false)}>
                {state.cancelText}
              </button>
              <button
                type="button"
                className={`primary-button ${state.danger ? "danger" : ""}`}
                onClick={() => close(true)}
              >
                {state.confirmText}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    throw new Error("useConfirm должен использоваться внутри ConfirmProvider");
  }
  return ctx;
}
