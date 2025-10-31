import { forwardRef, type HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const BaseNode = forwardRef<
    HTMLDivElement,
    HTMLAttributes<HTMLDivElement> & { selected?: boolean }
>(({ className, selected, ...props }, ref) => (
    <div
        ref={ref}
        className={cn(
            "relative rounded-md border bg-card p-5 text-card-foreground",
            className,
            selected ? "border-4" : "",
            "hover:ring-1",
        )}
        style={{ zIndex: selected ? 100 : 'auto' }}
        tabIndex={0}
        {...props}
    />
));

BaseNode.displayName = "BaseNode";