import { cn } from "@/lib/utils";

type StageStatus = "clean" | "dirty" | "not-run" | "running" | "failed" | "na";

const dotClass: Record<StageStatus, string> = {
  clean: "bg-stage-clean",
  dirty: "bg-stage-dirty",
  "not-run": "bg-stage-not-run",
  running: "bg-stage-running",
  failed: "bg-stage-failed",
  na: "bg-stage-na",
};

interface StageCellProps {
  stage: string;
  status: StageStatus;
  className?: string;
  "data-testid"?: string;
}

export function StageCell({
  stage,
  status,
  className,
  "data-testid": testId,
}: StageCellProps) {
  return (
    <div
      data-testid={testId}
      className={cn(
        "flex flex-col items-center gap-1 rounded-md border border-border-1 bg-bg-surface p-2 text-center",
        className,
      )}
    >
      <span className={cn("h-2.5 w-2.5 rounded-full", dotClass[status])} />
      <span className="text-xs text-ink-3 leading-tight">{stage}</span>
    </div>
  );
}
