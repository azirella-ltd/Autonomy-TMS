import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@azirella-ltd/autonomy-frontend";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
        secondary: "border-transparent bg-green-100 text-green-700 hover:bg-green-100",
        destructive: "border text-red-700 bg-red-100 border-red-200",
        destructive2: "border text-red-700 bg-red-100 border-red-200 rounded-[6px] px-2 py-1",
        destructive3: "border text-white bg-red-700 border-red-700 rounded-[6px] px-2 py-1",
        outline: "text-foreground bg-gray-200",
        outline2: "text-foreground border-0",
        primary: "border text-green-700 bg-green-100 border-green-200",
        primary2: "border text-green-700 bg-green-100 border-green-200 rounded-[6px] px-2 py-1",
        primary3: "border text-white bg-green-700 border-green-700 rounded-[6px] px-2 py-1",
        warning: "border text-amber-700 bg-amber-100 border-amber-200",
        warning2: "border text-amber-700 bg-amber-100 border-amber-200 rounded-[6px] px-2 py-1",
        warning3: "border text-white bg-amber-600 border-amber-600 rounded-[6px] px-2 py-1",
        // Decision pills - visually balanced
        autonomous: "border text-green-700 bg-green-100 border-green-200 rounded-[6px] px-2 py-1",
        suggested: "border text-indigo-700 bg-indigo-100 border-indigo-200 rounded-[6px] px-2 py-1",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
