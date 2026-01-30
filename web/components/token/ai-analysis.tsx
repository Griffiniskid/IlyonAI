"use client";

import { Brain, AlertTriangle, CheckCircle, TrendingUp } from "lucide-react";
import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { AIAnalysisResponse } from "@/types";
import { cn } from "@/lib/utils";

interface AIAnalysisProps {
  ai: AIAnalysisResponse;
}

export function AIAnalysis({ ai }: AIAnalysisProps) {
  if (!ai.available) {
    return (
      <GlassCard className="opacity-60">
        <div className="flex items-center gap-2 mb-4">
          <Brain className="h-5 w-5 text-muted-foreground" />
          <h3 className="font-semibold">AI Analysis</h3>
        </div>
        <p className="text-muted-foreground text-sm">AI analysis not available</p>
      </GlassCard>
    );
  }

  return (
    <GlassCard>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-emerald-500" />
          <h3 className="font-semibold">AI Analysis</h3>
        </div>
        <Badge variant="outline" className="font-mono">
          {ai.confidence}% confidence
        </Badge>
      </div>

      {/* Summary */}
      {ai.summary && (
        <div className="mb-4 p-3 bg-card/50 rounded-lg">
          <p className="text-sm text-foreground/90">{ai.summary}</p>
        </div>
      )}

      {/* Rug probability */}
      <div className="mb-4 p-3 bg-card/50 rounded-lg">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-muted-foreground">Rug Pull Probability</span>
          <span
            className={cn(
              "font-mono font-semibold",
              ai.rug_probability <= 25 && "text-emerald-400",
              ai.rug_probability > 25 && ai.rug_probability <= 50 && "text-yellow-400",
              ai.rug_probability > 50 && ai.rug_probability <= 75 && "text-orange-400",
              ai.rug_probability > 75 && "text-red-400"
            )}
          >
            {ai.rug_probability}%
          </span>
        </div>
        <div className="h-2 bg-muted rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full transition-all duration-500",
              ai.rug_probability <= 25 && "bg-emerald-500",
              ai.rug_probability > 25 && ai.rug_probability <= 50 && "bg-yellow-500",
              ai.rug_probability > 50 && ai.rug_probability <= 75 && "bg-orange-500",
              ai.rug_probability > 75 && "bg-red-500"
            )}
            style={{ width: `${ai.rug_probability}%` }}
          />
        </div>
      </div>

      {/* Flags */}
      <div className="grid grid-cols-2 gap-4">
        {/* Red flags */}
        {ai.red_flags.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-red-400 text-sm font-medium mb-2">
              <AlertTriangle className="h-4 w-4" />
              Red Flags ({ai.red_flags.length})
            </div>
            <ul className="space-y-1">
              {ai.red_flags.slice(0, 5).map((flag, i) => (
                <li key={i} className="text-xs text-red-300/80 flex items-start gap-1">
                  <span className="text-red-400">•</span>
                  {flag}
                </li>
              ))}
              {ai.red_flags.length > 5 && (
                <li className="text-xs text-muted-foreground">
                  +{ai.red_flags.length - 5} more
                </li>
              )}
            </ul>
          </div>
        )}

        {/* Green flags */}
        {ai.green_flags.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-emerald-400 text-sm font-medium mb-2">
              <CheckCircle className="h-4 w-4" />
              Green Flags ({ai.green_flags.length})
            </div>
            <ul className="space-y-1">
              {ai.green_flags.slice(0, 5).map((flag, i) => (
                <li key={i} className="text-xs text-emerald-300/80 flex items-start gap-1">
                  <span className="text-emerald-400">•</span>
                  {flag}
                </li>
              ))}
              {ai.green_flags.length > 5 && (
                <li className="text-xs text-muted-foreground">
                  +{ai.green_flags.length - 5} more
                </li>
              )}
            </ul>
          </div>
        )}
      </div>

      {/* Recommendation */}
      {ai.recommendation && (
        <div className="mt-4 pt-4 border-t border-border/50">
          <div className="flex items-center gap-1.5 text-sm font-medium mb-2">
            <TrendingUp className="h-4 w-4 text-emerald-500" />
            Recommendation
          </div>
          <p className="text-sm text-muted-foreground">{ai.recommendation}</p>
        </div>
      )}
    </GlassCard>
  );
}
