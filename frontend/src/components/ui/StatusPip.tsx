import { cn } from "@/lib/utils";

type Status = "done" | "running" | "queued" | "error" | "review";

const dotClass: Record<Status, string> = {
  done: "bg-status-done",
  running: "bg-status-running",
  queued: "bg-status-queued",
  error: "bg-status-error",
  review: "bg-status-review",
};

interface StatusPipProps {
  status: Status;
  label?: string;
  className?: string;
  "data-testid"?: string;
}

export function StatusPip({
  status,
  label,
  className,
  "data-testid": testId,
}: StatusPipProps) {
  return (
    <span
      data-testid={testId}
      className={cn("inline-flex items-center gap-1.5 text-sm", className)}
    >
      <span className={cn("h-2 w-2 rounded-full shrink-0", dotClass[status])} />
      {label && <span className="text-ink-2">{label}</span>}
    </span>
  );
}
