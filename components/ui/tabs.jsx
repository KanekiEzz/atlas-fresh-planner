import { cn } from "@/lib/utils";

export function TabsList({ className, ...props }) {
  return <div className={cn("ui-tabs-list", className)} {...props} />;
}

export function TabsTrigger({ active, className, ...props }) {
  return <button className={cn("ui-tabs-trigger", active && "is-active", className)} {...props} />;
}
