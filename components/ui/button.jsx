import { cn } from "@/lib/utils";

export function Button({ className, variant = "default", size = "default", ...props }) {
  return (
    <button
      className={cn("ui-button", `ui-button-${variant}`, `ui-button-size-${size}`, className)}
      {...props}
    />
  );
}

export function IconButton({ label, icon, className, ...props }) {
  return (
    <Button className={cn("ui-icon-button", className)} size="icon" aria-label={label} title={label} {...props}>
      <span className="material-symbols-rounded" aria-hidden="true">
        {icon}
      </span>
    </Button>
  );
}
