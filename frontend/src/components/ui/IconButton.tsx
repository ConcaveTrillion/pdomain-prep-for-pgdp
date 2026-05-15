import { Button, type ButtonProps } from "./Button";
import { cn } from "@/lib/utils";

export interface IconButtonProps extends Omit<ButtonProps, "size"> {
  "data-testid"?: string;
}

export function IconButton({ className, ...props }: IconButtonProps) {
  return <Button size="icon" className={cn(className)} {...props} />;
}
