import { ReactNode } from "react";

type Props = {
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  secondaryLabel?: string;
  onSecondaryAction?: () => void;
  children?: ReactNode;
};

function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
  secondaryLabel,
  onSecondaryAction,
  children,
}: Props) {
  return (
    <div className="empty-state">
      <div>
        <h3>{title}</h3>
        {description && <p>{description}</p>}
      </div>
      {children}
      {(actionLabel || secondaryLabel) && (
        <div className="row-actions">
          {actionLabel && onAction && (
            <button type="button" className="primary-button" onClick={onAction}>
              {actionLabel}
            </button>
          )}
          {secondaryLabel && onSecondaryAction && (
            <button type="button" className="ghost-button" onClick={onSecondaryAction}>
              {secondaryLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default EmptyState;
