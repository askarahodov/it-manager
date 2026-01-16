type ActionMenuItem = {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  title?: string;
};

type ActionMenuProps = {
  items: ActionMenuItem[];
  label?: string;
  ariaLabel?: string;
};

function closeMenu(target: HTMLElement | null) {
  const details = target?.closest("details") as HTMLDetailsElement | null;
  if (details) {
    details.open = false;
  }
}

export default function ActionMenu({ items, label = "...", ariaLabel = "Действия" }: ActionMenuProps) {
  return (
    <details className="action-menu" onClick={(event) => event.stopPropagation()}>
      <summary
        className="ghost-button action-menu-trigger"
        aria-label={ariaLabel}
        onClick={(event) => event.stopPropagation()}
      >
        {label}
      </summary>
      <div className="action-menu-popover" role="menu">
        {items.map((item, index) => (
          <button
            key={`${item.label}-${index}`}
            type="button"
            className={`action-menu-item ${item.danger ? "danger" : ""}`}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              if (item.disabled) return;
              item.onClick();
              closeMenu(event.currentTarget);
            }}
            disabled={item.disabled}
            title={item.title}
            role="menuitem"
          >
            {item.label}
          </button>
        ))}
      </div>
    </details>
  );
}
