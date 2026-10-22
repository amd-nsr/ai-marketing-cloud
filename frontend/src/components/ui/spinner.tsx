import { cn } from "@/lib/utils";

export function Spinner({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <span
      role="status"
      className={cn("inline-flex items-center gap-2 text-sm text-muted", className)}
    >
      <span
        aria-hidden
        className="size-4 animate-spin rounded-full border-2 border-border border-t-primary"
      />
      <span className="sr-only">{label}</span>
    </span>
  );
}

export function PageLoading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center gap-2 text-sm text-muted">
      <Spinner label={label} />
      {label}
    </div>
  );
}
