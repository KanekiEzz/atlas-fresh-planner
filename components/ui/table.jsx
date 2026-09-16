import { cn } from "@/lib/utils";

export function TableWrap({ className, ...props }) {
  return <div className={cn("ui-table-wrap", className)} {...props} />;
}

export function Table({ className, ...props }) {
  return <table className={cn("ui-table", className)} {...props} />;
}
