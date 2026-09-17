import { cn } from "@/lib/utils";

export function Input({ className, ...props }) {
  return <input className={cn("ui-input min-w-0 max-w-full", className)} {...props} />;
}
