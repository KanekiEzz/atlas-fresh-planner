import { cn } from "@/lib/utils";

export function Badge({ className, variant = "default", ...props }) {
  return <span className={cn("ui-badge min-w-0 max-w-full break-words", `ui-badge-${variant}`, className)} {...props} />;
}
