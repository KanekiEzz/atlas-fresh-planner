import { IconButton } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Sheet({ open, onClose, title, eyebrow, children }) {
  return (
    <aside className={cn("ui-sheet", open && "is-open")} aria-hidden={!open} onClick={onClose}>
      <div className="ui-sheet-panel" onClick={(event) => event.stopPropagation()}>
        <header className="ui-sheet-head">
          <div>
            {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
            <h2>{title}</h2>
          </div>
          <IconButton label="Close" icon="close" onClick={onClose} />
        </header>
        {children}
      </div>
    </aside>
  );
}
