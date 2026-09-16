import { cn } from "@/lib/utils";

export function Select({ className, ...props }) {
  return <select className={cn("ui-select", className)} {...props} />;
}
