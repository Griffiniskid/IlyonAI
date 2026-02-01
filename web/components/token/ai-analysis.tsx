"use client";

import { Brain, AlertTriangle, CheckCircle, TrendingUp, MessageSquare, Flame, Users, Twitter } from "lucide-react";
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

      {/* Narrative Analysis (Grok) */}
      {ai.grok && (
        <div className="mb-6 p-4 bg-card/50 rounded-lg border border-border/50">
          <div className="flex items-center gap-2 mb-3 text-sky-400">
            <Twitter className="h-4 w-4" />
            <h4 className="font-semibold text-sm">Narrative & Vibe (Grok)</h4>
          </div>
          
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div className="bg-background/40 p-2 rounded text-center">
              <span className="text-xs text-muted-foreground block">Score</span>
              <span className={cn(
                "font-bold",
                ai.grok.narrative_score >= 80 ? "text-emerald-400" : 
                ai.grok.narrative_score >= 50 ? "text-yellow-400" : "text-red-400"
              )}>
                {ai.grok.narrative_score}/100
              </span>
            </div>
            <div className="bg-background/40 p-2 rounded text-center">
              <span className="text-xs text-muted-foreground block">Sentiment</span>
              <span className="font-bold text-foreground">{ai.grok.sentiment}</span>
            </div>
            <div className="bg-background/40 p-2 rounded text-center">
              <span className="text-xs text-muted-foreground block">Status</span>
              <span className="font-bold text-foreground">{ai.grok.trending_status}</span>
            </div>
            <div className="bg-background/40 p-2 rounded text-center">
              <span className="text-xs text-muted-foreground block">Vibe</span>
              <span className="font-bold text-sky-400 text-xs uppercase">{ai.grok.community_vibe || "UNKNOWN"}</span>
            </div>
          </div>

          <div className="mb-3">
            <p className="text-sm text-foreground/90 leading-relaxed italic border-l-2 border-sky-500/30 pl-3">
              "{ai.grok.narrative_summary}"
            </p>
          </div>
          
          {/* Key Themes Tags */}
          {ai.grok.key_themes && ai.grok.key_themes.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {ai.grok.key_themes.map((theme, i) => (
                <Badge key={i} variant="secondary" className="text-[10px] px-1.5 py-0 bg-sky-500/10 text-sky-300 border-sky-500/20">
                  #{theme}
                </Badge>
              ))}
            </div>
          )}

          <div className="space-y-2 text-xs">
            <div className="flex gap-2 items-start">
              <Users className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
              <div>
                <span className="text-muted-foreground block mb-0.5">
                  <strong className="text-foreground">Influencer Tier:</strong> {ai.grok.influencer_tier || "NONE"}
                </span>
                <span className="text-muted-foreground/80 italic">
                  {ai.grok.influencer_activity}
                </span>
              </div>
            </div>
            {ai.grok.fud_warnings && ai.grok.fud_warnings.length > 0 && (
              <div className="flex gap-2">
                <AlertTriangle className="h-3.5 w-3.5 text-orange-400 shrink-0 mt-0.5" />
                <span className="text-orange-300/80">
                  <strong className="text-orange-400">Warnings:</strong> {ai.grok.fud_warnings.join(", ")}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Summary (Standard AI) - only show if no narrative or distinct content */}
      {!ai.grok && ai.summary && (
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
