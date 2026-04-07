"use client";

import { GlassCard } from "@/components/ui/card";
import {
  Construction,
  Shield,
  Bell,
  FileSearch,
  Flame,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

const icons: Record<string, LucideIcon> = {
  construction: Construction,
  shield: Shield,
  bell: Bell,
  "file-search": FileSearch,
  flame: Flame,
  users: Users,
};

interface ComingSoonProps {
  title: string;
  description?: string;
  icon?: string;
}

export function ComingSoon({ title, description, icon = "construction" }: ComingSoonProps) {
  const Icon = icons[icon] ?? Construction;

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      <GlassCard className="text-center py-20">
        <Icon className="h-16 w-16 text-emerald-400/50 mx-auto mb-6" />
        <h1 className="text-3xl font-bold mb-3">{title}</h1>
        <p className="text-muted-foreground max-w-md mx-auto mb-4">
          {description || "This feature is under active development and will be available soon."}
        </p>
        <span className="inline-block text-xs font-semibold uppercase tracking-wider text-emerald-400 bg-emerald-400/10 px-4 py-2 rounded-full">
          Coming Soon
        </span>
      </GlassCard>
    </div>
  );
}
