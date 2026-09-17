import { cn } from "@/lib/utils";

export function Card({ className, size = "default", ...props }) {
  return <section className={cn("ui-card min-w-0 max-w-full", className)} data-size={size} {...props} />;
}

export function CardHeader({ className, ...props }) {
  return <div className={cn("ui-card-header min-w-0 max-w-full", className)} {...props} />;
}

export function CardTitle({ className, ...props }) {
  return <h2 className={cn("ui-card-title min-w-0 max-w-full break-words", className)} {...props} />;
}

export function CardContent({ className, ...props }) {
  return <div className={cn("ui-card-content min-w-0 max-w-full", className)} {...props} />;
}
