import * as SeparatorPrimitive from "@radix-ui/react-separator";
import { cn } from "@/lib/utils";

interface SeparatorProps {
  orientation?: "horizontal" | "vertical";
  className?: string;
  "data-testid"?: string;
}

export function Separator({
  orientation = "horizontal",
  className,
  "data-testid": testId,
}: SeparatorProps) {
  return (
    <SeparatorPrimitive.Root
      data-testid={testId}
      orientation={orientation}
      decorative
      className={cn(
        "shrink-0 bg-border-1",
        orientation === "horizontal" ? "h-[1px] w-full" : "h-full w-[1px]",
        className,
      )}
    />
  );
}
