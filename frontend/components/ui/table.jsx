import { cn } from "@/lib/utils";

export function TableWrap({ className, ...props }) {
  return <div className={cn("ui-table-wrap min-w-0 max-w-full", className)} {...props} />;
}

export function Table({ className, ...props }) {
  return <table className={cn("ui-table min-w-0 max-w-full", className)} {...props} />;
}
