import { useEffect, useRef, useState, type ReactNode } from 'react';

export type MenuEntry =
  | { kind?: 'item'; label: string; note?: string; checked?: boolean; disabled?: boolean; onClick: () => void }
  | { kind: 'heading'; label: string }
  | { kind: 'separator' }
  | { kind: 'custom'; node: ReactNode };

export function Menu({ label, ariaLabel, entries, onOpen }: {
  label: ReactNode;
  ariaLabel: string;
  entries: MenuEntry[];
  onOpen?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    const esc = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);

  return (
    <div className="menu" ref={ref}>
      <button
        className="icon-btn"
        aria-label={ariaLabel}
        title={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => {
          if (!open) onOpen?.();
          setOpen(!open);
        }}
      >
        {label}
      </button>
      {open && (
        <div className="menu-list" role="menu">
          {entries.map((entry, i) => {
            if (entry.kind === 'separator') return <div key={i} className="menu-sep" />;
            if (entry.kind === 'heading') return <div key={i} className="menu-label">{entry.label}</div>;
            if (entry.kind === 'custom') return <div key={i} className="menu-custom">{entry.node}</div>;
            return (
              <button
                key={i}
                role="menuitem"
                className="menu-item"
                disabled={entry.disabled}
                onClick={() => {
                  setOpen(false);
                  entry.onClick();
                }}
              >
                <span><span className="menu-check">{entry.checked ? '✓' : ''}</span>{entry.label}</span>
                {entry.note && <small>{entry.note}</small>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
