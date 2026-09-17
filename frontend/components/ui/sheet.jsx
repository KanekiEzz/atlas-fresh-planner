import { IconButton } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Sheet({ open, onClose, title, eyebrow, children }) {
  return (
    <aside className={cn("ui-sheet", open && "is-open")} aria-hidden={!open} onClick={onClose}>
      <div className="ui-sheet-panel min-w-0 max-w-full" onClick={(event) => event.stopPropagation()}>
        <header className="ui-sheet-head min-w-0 max-w-full">
          <div className="min-w-0 max-w-full">
            {eyebrow ? <span className="eyebrow min-w-0 max-w-full break-words">{eyebrow}</span> : null}
            <h2 className="min-w-0 max-w-full break-words">{title}</h2>
          </div>
          <IconButton label="Close" icon="close" onClick={onClose} />
        </header>
        {children}
      </div>
    </aside>
  );
}
