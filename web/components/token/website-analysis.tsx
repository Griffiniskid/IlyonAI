"use client";

import { Globe, Check, X, Smartphone, Lock, AlertTriangle, FileText, ExternalLink } from "lucide-react";
import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Define interface locally based on backend schema
interface WebsiteAnalysisResponse {
  quality: number;
  is_legitimate: boolean;
  has_privacy_policy: boolean;
  has_terms: boolean;
  has_copyright: boolean;
  has_contact: boolean;
  has_tokenomics: boolean;
  has_roadmap: boolean;
  has_team: boolean;
  has_whitepaper: boolean;
  has_audit: boolean;
  audit_provider: string | null;
  red_flags: string[];
  ai_quality: string;
  ai_concerns: string[];
}

interface WebsiteAnalysisProps {
  website: WebsiteAnalysisResponse;
  url?: string | null;
}

export function WebsiteAnalysis({ website, url }: WebsiteAnalysisProps) {
  if (!url) return null;

  const trustSignals = [
    { label: "SSL / HTTPS", value: url.startsWith("https"), icon: Lock },
    { label: "Contact Info", value: website.has_contact, icon: FileText },
    { label: "Privacy Policy", value: website.has_privacy_policy, icon: FileText },
    { label: "Terms of Service", value: website.has_terms, icon: FileText },
    { label: "Copyright", value: website.has_copyright, icon: FileText },
  ];

  const contentSignals = [
    { label: "Whitepaper", value: website.has_whitepaper },
    { label: "Roadmap", value: website.has_roadmap },
    { label: "Tokenomics", value: website.has_tokenomics },
    { label: "Team Info", value: website.has_team },
    { label: "Audit", value: website.has_audit },
  ];

  return (
    <GlassCard className="h-full">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Globe className="h-5 w-5 text-blue-500" />
          <h3 className="font-semibold">Website Analysis</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn(
            "text-2xl font-bold font-mono",
            website.quality >= 80 ? "text-emerald-400" :
            website.quality >= 50 ? "text-yellow-400" : "text-red-400"
          )}>
            {website.quality}/100
          </span>
        </div>
      </div>

      <div className="space-y-6">
        {/* Trust Signals Grid */}
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Trust Signals</h4>
          <div className="grid grid-cols-2 gap-2">
            {trustSignals.map((signal) => (
              <div 
                key={signal.label} 
                className={cn(
                  "flex items-center gap-2 px-3 py-2 rounded-lg text-sm border",
                  signal.value 
                    ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-200" 
                    : "bg-red-500/5 border-red-500/10 text-red-300/70"
                )}
              >
                {signal.value ? <Check className="h-4 w-4 shrink-0" /> : <X className="h-4 w-4 shrink-0" />}
                {signal.label}
              </div>
            ))}
          </div>
        </div>

        {/* Content Checklist */}
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Content</h4>
          <div className="flex flex-wrap gap-2">
            {contentSignals.map((signal) => (
              <Badge 
                key={signal.label}
                variant={signal.value ? "secondary" : "outline"}
                className={cn(
                  !signal.value && "opacity-50 dashed border-muted-foreground/40"
                )}
              >
                {signal.label}
              </Badge>
            ))}
          </div>
        </div>

        {/* AI & Red Flags */}
        {(website.red_flags.length > 0 || website.ai_concerns.length > 0) && (
          <div className="p-3 bg-red-500/10 rounded-lg border border-red-500/20">
            <div className="flex items-center gap-2 text-red-400 text-sm font-medium mb-2">
              <AlertTriangle className="h-4 w-4" />
              Red Flags & Concerns
            </div>
            <ul className="text-xs text-red-200/80 space-y-1 list-disc list-inside">
              {website.red_flags.map((flag, i) => (
                <li key={`flag-${i}`}>{flag}</li>
              ))}
              {website.ai_concerns.map((concern, i) => (
                <li key={`concern-${i}`}>{concern}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Footer Link */}
        <a 
          href={url} 
          target="_blank" 
          rel="noopener noreferrer"
          className="flex items-center justify-center w-full py-2 text-xs text-muted-foreground hover:text-foreground transition-colors border-t border-border mt-4"
        >
          Visit Website <ExternalLink className="h-3 w-3 ml-1" />
        </a>
      </div>
    </GlassCard>
  );
}
