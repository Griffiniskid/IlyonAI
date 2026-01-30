"use client";

import { useMemo } from "react";
import { cn, getScoreColor, getScoreBgColor } from "@/lib/utils";

interface ScoreCardProps {
  score: number;
  grade: string;
  verdict: string;
  size?: "sm" | "md" | "lg";
}

export function ScoreCard({ score, grade, verdict, size = "md" }: ScoreCardProps) {
  const dimensions = useMemo(() => {
    switch (size) {
      case "sm":
        return { ring: 80, stroke: 6, fontSize: "text-2xl", gradeSize: "text-sm" };
      case "lg":
        return { ring: 160, stroke: 10, fontSize: "text-5xl", gradeSize: "text-xl" };
      default:
        return { ring: 120, stroke: 8, fontSize: "text-4xl", gradeSize: "text-base" };
    }
  }, [size]);

  const circumference = 2 * Math.PI * ((dimensions.ring - dimensions.stroke) / 2);
  const offset = circumference - (score / 100) * circumference;

  const scoreColor = getScoreColor(score);
  const strokeColor = useMemo(() => {
    if (score >= 80) return "#10b981";
    if (score >= 60) return "#eab308";
    if (score >= 40) return "#f97316";
    if (score >= 20) return "#ef4444";
    return "#dc2626";
  }, [score]);

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Score Ring */}
      <div className="relative" style={{ width: dimensions.ring, height: dimensions.ring }}>
        <svg
          className="transform -rotate-90"
          width={dimensions.ring}
          height={dimensions.ring}
        >
          {/* Background circle */}
          <circle
            cx={dimensions.ring / 2}
            cy={dimensions.ring / 2}
            r={(dimensions.ring - dimensions.stroke) / 2}
            fill="none"
            stroke="hsl(var(--muted))"
            strokeWidth={dimensions.stroke}
          />
          {/* Progress circle */}
          <circle
            cx={dimensions.ring / 2}
            cy={dimensions.ring / 2}
            r={(dimensions.ring - dimensions.stroke) / 2}
            fill="none"
            stroke={strokeColor}
            strokeWidth={dimensions.stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="transition-all duration-1000 ease-out"
            style={{
              filter: `drop-shadow(0 0 8px ${strokeColor}40)`,
            }}
          />
        </svg>

        {/* Score text in center */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn("font-mono font-bold", dimensions.fontSize, scoreColor)}>
            {score}
          </span>
          <span className={cn("text-muted-foreground", dimensions.gradeSize)}>
            {grade}
          </span>
        </div>
      </div>

      {/* Verdict badge */}
      <div
        className={cn(
          "px-4 py-1.5 rounded-full font-semibold text-sm uppercase tracking-wide",
          verdict === "SAFE" && "bg-emerald-500/20 text-emerald-400",
          verdict === "CAUTION" && "bg-yellow-500/20 text-yellow-400",
          verdict === "RISKY" && "bg-orange-500/20 text-orange-400",
          verdict === "DANGEROUS" && "bg-red-500/20 text-red-400",
          verdict === "SCAM" && "bg-red-600/20 text-red-500"
        )}
      >
        {verdict}
      </div>
    </div>
  );
}
