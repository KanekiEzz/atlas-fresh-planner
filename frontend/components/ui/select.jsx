import { cn } from "@/lib/utils";

export function Select({ className, ...props }) {
  return <select className={cn("ui-select min-w-0 max-w-full", className)} {...props} />;
}
