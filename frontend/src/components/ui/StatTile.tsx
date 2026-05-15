import { cn } from "@/lib/utils";

interface StatTileProps {
  value: string | number;
  label: string;
  className?: string;
  "data-testid"?: string;
}

export function StatTile({
  value,
  label,
  className,
  "data-testid": testId,
}: StatTileProps) {
  return (
    <div
      data-testid={testId}
      className={cn("flex flex-col gap-0.5", className)}
    >
      <span className="text-2xl font-semibold text-ink-1">{value}</span>
      <span className="text-xs text-ink-3">{label}</span>
    </div>
  );
}
