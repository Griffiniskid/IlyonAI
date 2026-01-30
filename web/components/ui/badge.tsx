import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-transparent bg-destructive text-destructive-foreground",
        outline: "text-foreground",
        safe: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
        caution: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
        risky: "bg-orange-500/20 text-orange-400 border-orange-500/30",
        danger: "bg-red-500/20 text-red-400 border-red-500/30",
        scam: "bg-red-600/20 text-red-500 border-red-600/30",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

// Verdict badge helper
function VerdictBadge({ verdict }: { verdict: string }) {
  const variant = (() => {
    switch (verdict?.toUpperCase()) {
      case "SAFE": return "safe";
      case "CAUTION": return "caution";
      case "RISKY": return "risky";
      case "DANGEROUS": return "danger";
      case "SCAM": return "scam";
      default: return "secondary";
    }
  })() as "safe" | "caution" | "risky" | "danger" | "scam" | "secondary";

  return <Badge variant={variant}>{verdict}</Badge>;
}

export { Badge, badgeVariants, VerdictBadge };
