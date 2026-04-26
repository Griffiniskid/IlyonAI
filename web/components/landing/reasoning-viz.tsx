"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, Loader2 } from "lucide-react";

interface ReasoningScenario {
  id: number;
  title: string;
  steps: {
    icon: string;
    label: string;
    detail: string;
    substeps?: string[];
  }[];
}

const SCENARIOS: ReasoningScenario[] = [
  {
    id: 1,
    title: "Cross-Chain Bridge Request",
    steps: [
      {
        icon: "🔍",
        label: "Parsing Intent",
        detail: '"Bridge 1 ETH from Ethereum to Solana"',
        substeps: ["Source: Ethereum", "Destination: Solana", "Amount: 1 ETH"],
      },
      {
        icon: "⚡",
        label: "Querying deBridge DLN",
        detail: "Fetching optimal route...",
        substeps: ["Found: Ethereum → Solana via deBridge"],
      },
      {
        icon: "📊",
        label: "Calculating Economics",
        detail: "Analyzing fees and timing",
        substeps: ["Bridge fee: 0.15%", "Est. time: ~45s", "Min. received: 0.9985 ETH-equivalent"],
      },
      {
        icon: "🔐",
        label: "Building Transactions",
        detail: "Preparing complete transaction bundle",
        substeps: ["Step 1: Approval tx for ETH spend", "Step 2: Bridge deposit tx", "Ready for wallet signature"],
      },
    ],
  },
  {
    id: 2,
    title: "Yield Strategy Request",
    steps: [
      {
        icon: "💰",
        label: "Analyzing Portfolio",
        detail: "Checking wallet holdings",
        substeps: ["Wallet: 0x1234...5678", "Current: 2.5 ETH, 500 USDC"],
      },
      {
        icon: "📈",
        label: "Scanning Markets",
        detail: "Querying active opportunities",
        substeps: ["Uniswap, Aave, Curve...", "Top: Aave USDC lending @ 8.2% APY"],
      },
      {
        icon: "🛡️",
        label: "Risk Assessment",
        detail: "Evaluating protocol safety",
        substeps: ["Protocol TVL: $2.1B ✓", "Audited: CertiK ✓", "IL risk: N/A (lending)"],
      },
      {
        icon: "⚡",
        label: "Building Deposit",
        detail: "Preparing transaction",
        substeps: ["Approve USDC → Deposit to Aave", "Transaction ready"],
      },
    ],
  },
];

export function ReasoningVisualization() {
  const [currentScenario, setCurrentScenario] = useState(0);
  const [visibleSteps, setVisibleSteps] = useState(0);
  const [isComplete, setIsComplete] = useState(false);

  const scenario = SCENARIOS[currentScenario];

  const cycleScenario = useCallback(() => {
    setVisibleSteps(0);
    setIsComplete(false);
    setCurrentScenario((prev) => (prev + 1) % SCENARIOS.length);
  }, []);

  useEffect(() => {
    if (visibleSteps < scenario.steps.length) {
      const timer = setTimeout(() => setVisibleSteps((prev) => prev + 1), 800);
      return () => clearTimeout(timer);
    } else {
      setIsComplete(true);
      const timer = setTimeout(cycleScenario, 3000);
      return () => clearTimeout(timer);
    }
  }, [visibleSteps, scenario.steps.length, cycleScenario]);

  return (
    <div className="w-full max-w-4xl mx-auto min-h-[760px] md:min-h-[720px]">
      <AnimatePresence mode="wait">
        <motion.div
          key={scenario.id}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.4 }}
          className="space-y-6"
        >
          {/* Scenario title */}
          <div className="text-center mb-8">
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-purple-500/10 border border-purple-500/20"
            >
              <span className="text-sm text-purple-400 font-medium">{scenario.title}</span>
            </motion.div>
          </div>

          {/* Steps */}
          <div className="space-y-4 min-h-[590px]">
            {scenario.steps.map((step, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0.2, x: -20 }}
                animate={{
                  opacity: i < visibleSteps ? 1 : 0.2,
                  x: i < visibleSteps ? 0 : -20,
                }}
                transition={{ duration: 0.4, delay: i * 0.1 }}
                className={`relative min-h-[136px] p-5 rounded-xl border backdrop-blur-sm transition-all duration-300 ${
                  i < visibleSteps
                    ? "bg-white/[0.03] border-white/10"
                    : "bg-white/[0.01] border-white/5"
                }`}
              >
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-purple-500/30 flex items-center justify-center text-lg"
                  >
                    {i < visibleSteps ? (
                      isComplete || i < visibleSteps - 1 ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                      ) : (
                        <Loader2 className="w-5 h-5 animate-spin text-purple-400" />
                      )
                    ) : (
                      step.icon
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-semibold text-white">{step.label}</span>
                      {i === visibleSteps - 1 && !isComplete && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-500/20 text-[10px] text-purple-400 font-medium">
                          <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
                          Active
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mb-2">{step.detail}</p>

                    <div className="space-y-1.5 mt-3 min-h-[58px]">
                      {step.substeps?.map((sub, j) => (
                        <motion.div
                          key={j}
                          initial={false}
                          animate={{ opacity: i < visibleSteps ? 1 : 0, x: i < visibleSteps ? 0 : -10 }}
                          transition={{ delay: i < visibleSteps ? j * 0.1 : 0, duration: 0.25 }}
                          className="flex items-center gap-2 text-xs text-white/60"
                        >
                          <span className="w-1 h-1 rounded-full bg-emerald-400/60" />
                          {sub}
                        </motion.div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Connector line */}
                {i < scenario.steps.length - 1 && (
                  <div className="absolute left-[2.25rem] top-[3.5rem] w-px h-6 bg-gradient-to-b from-purple-500/30 to-transparent" />
                )}
              </motion.div>
            ))}
          </div>

          {/* Progress bar */}
          <div className="mt-6 h-1 bg-white/5 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-purple-500 to-emerald-500"
              initial={{ width: "0%" }}
              animate={{ width: `${(visibleSteps / scenario.steps.length) * 100}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
