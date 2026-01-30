"use client";

import { Check, X, AlertTriangle, Lock, Unlock, Shield } from "lucide-react";
import { GlassCard } from "@/components/ui/card";
import type { SecurityResponse } from "@/types";
import { cn } from "@/lib/utils";

interface SecurityChecksProps {
  security: SecurityResponse;
}

export function SecurityChecks({ security }: SecurityChecksProps) {
  const checks = [
    {
      label: "Mint Authority",
      value: !security.mint_authority_enabled,
      goodLabel: "Disabled",
      badLabel: "Enabled",
      description: "Can new tokens be minted?",
    },
    {
      label: "Freeze Authority",
      value: !security.freeze_authority_enabled,
      goodLabel: "Disabled",
      badLabel: "Enabled",
      description: "Can tokens be frozen?",
    },
    {
      label: "Liquidity Lock",
      value: security.liquidity_locked,
      goodLabel: `Locked ${security.lp_lock_percent > 0 ? `(${security.lp_lock_percent.toFixed(0)}%)` : ""}`,
      badLabel: "Unlocked",
      description: "Is liquidity locked?",
    },
    {
      label: "Honeypot Status",
      value: !security.honeypot_is_honeypot,
      goodLabel: security.honeypot_status === "safe" ? "Safe" : "Tradeable",
      badLabel: security.honeypot_is_honeypot ? "Honeypot!" : security.honeypot_status,
      description: security.honeypot_explanation || "Can tokens be sold?",
    },
  ];

  return (
    <GlassCard>
      <div className="flex items-center gap-2 mb-4">
        <Shield className="h-5 w-5 text-emerald-500" />
        <h3 className="font-semibold">Security Checks</h3>
      </div>

      <div className="space-y-3">
        {checks.map((check) => (
          <div
            key={check.label}
            className="flex items-center justify-between py-2 border-b border-border/50 last:border-0"
          >
            <div>
              <div className="font-medium text-sm">{check.label}</div>
              <div className="text-xs text-muted-foreground">{check.description}</div>
            </div>
            <div
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold",
                check.value
                  ? "bg-emerald-500/20 text-emerald-400"
                  : "bg-red-500/20 text-red-400"
              )}
            >
              {check.value ? (
                <Check className="h-3.5 w-3.5" />
              ) : (
                <X className="h-3.5 w-3.5" />
              )}
              {check.value ? check.goodLabel : check.badLabel}
            </div>
          </div>
        ))}
      </div>

      {/* Honeypot warnings */}
      {security.honeypot_warnings && security.honeypot_warnings.length > 0 && (
        <div className="mt-4 p-3 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
          <div className="flex items-center gap-2 text-yellow-400 text-sm font-medium mb-2">
            <AlertTriangle className="h-4 w-4" />
            Warnings
          </div>
          <ul className="text-xs text-yellow-200/80 space-y-1">
            {security.honeypot_warnings.map((warning, i) => (
              <li key={i}>• {warning}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Sell tax info */}
      {security.honeypot_sell_tax_percent !== null && security.honeypot_sell_tax_percent > 0 && (
        <div className="mt-3 p-3 bg-orange-500/10 rounded-lg border border-orange-500/20">
          <div className="text-sm">
            <span className="text-orange-400 font-medium">Sell Tax: </span>
            <span className="text-orange-200">
              {security.honeypot_sell_tax_percent.toFixed(1)}%
            </span>
          </div>
        </div>
      )}
    </GlassCard>
  );
}
