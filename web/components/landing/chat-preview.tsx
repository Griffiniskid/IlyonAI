"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, Loader2 } from "lucide-react";

interface Scenario {
  id: number;
  userMessage: string;
  reasoningSteps: { type: "think" | "tool" | "result" | "conclude"; label: string; detail: string }[];
  aiResponse: string;
  structuredOutput?: {
    type: "swap" | "balance" | "bridge";
    title: string;
    details: Record<string, string>;
  };
}

const SCENARIOS: Scenario[] = [
  {
    id: 1,
    userMessage: "Swap 0.5 SOL to USDC at best rate",
    reasoningSteps: [
      { type: "think", label: "Identifying swap parameters", detail: "Extracting token pair & amount" },
      { type: "tool", label: "build_swap_tx", detail: "Querying Jupiter v6 route" },
      { type: "result", label: "Route found", detail: "Optimal Solana transaction bundle" },
      { type: "conclude", label: "Simulation complete", detail: "Transaction ready to sign" },
    ],
    aiResponse: "Found the best route via Jupiter. Here are the details:",
    structuredOutput: {
      type: "swap",
      title: "Swap Preview",
      details: {
        From: "0.5 SOL",
        To: "~28.45 USDC",
        Route: "Jupiter v6 Aggregator",
        "Price Impact": "≤ 0.3%",
        Fee: "0.1% platform",
      },
    },
  },
  {
    id: 2,
    userMessage: "What's my portfolio worth today?",
    reasoningSteps: [
      { type: "tool", label: "get_balance", detail: "Connecting to chain RPCs" },
      { type: "result", label: "On-chain query complete", detail: "Latest balances resolved" },
      { type: "tool", label: "get_token_price", detail: "Fetching USD prices" },
      { type: "conclude", label: "Portfolio ready", detail: "Total net worth calculated" },
    ],
    aiResponse: "Here's your current portfolio across all chains:",
    structuredOutput: {
      type: "balance",
      title: "Portfolio Summary",
      details: {
        "Total Value": "$12,847.32",
        "24h Change": "+3.2%",
        Chains: "Solana, Ethereum, Base",
        "Top Holding": "2.5 ETH ($6,120)",
      },
    },
  },
  {
    id: 3,
    userMessage: "Bridge 1 ETH from Ethereum to Solana",
    reasoningSteps: [
      { type: "think", label: "Parsing bridge request", detail: "Source: Ethereum → Destination: Solana" },
      { type: "tool", label: "build_bridge_tx", detail: "Querying deBridge DLN route" },
      { type: "result", label: "Bridge route prepared", detail: "Approval + bridge payload ready" },
      { type: "conclude", label: "Preparing confirmation", detail: "Ready for wallet signing" },
    ],
    aiResponse: "Bridge route ready via deBridge DLN:",
    structuredOutput: {
      type: "bridge",
      title: "Bridge Preview",
      details: {
        From: "1 ETH (Ethereum)",
        To: "~0.998 ETH (Solana)",
        Route: "deBridge DLN",
        "Bridge Fee": "0.15%",
        "Est. Time": "~45 seconds",
      },
    },
  },
];

export function ChatPreview() {
  const [currentScenario, setCurrentScenario] = useState(0);
  const [showReasoning, setShowReasoning] = useState(false);
  const [visibleSteps, setVisibleSteps] = useState(0);
  const [showOutput, setShowOutput] = useState(false);

  const scenario = SCENARIOS[currentScenario];

  const cycleScenario = useCallback(() => {
    setShowOutput(false);
    setVisibleSteps(0);
    setShowReasoning(false);
    setCurrentScenario((prev) => (prev + 1) % SCENARIOS.length);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => setShowReasoning(true), 600);
    return () => clearTimeout(timer);
  }, [currentScenario]);

  useEffect(() => {
    if (!showReasoning) return;
    if (visibleSteps < scenario.reasoningSteps.length) {
      const timer = setTimeout(() => setVisibleSteps((prev) => prev + 1), 400);
      return () => clearTimeout(timer);
    } else {
      const timer = setTimeout(() => setShowOutput(true), 500);
      return () => clearTimeout(timer);
    }
  }, [showReasoning, visibleSteps, scenario.reasoningSteps.length]);

  useEffect(() => {
    const interval = setInterval(cycleScenario, 8000);
    return () => clearInterval(interval);
  }, [cycleScenario]);

  return (
    <div className="relative">
      <div className="glass-card animate-fade-in-up" style={{ animationDelay: "400ms" }}>
        {/* Demo badge */}
        <div className="absolute -top-2 -right-2 px-2 py-1 bg-emerald-500/20 border border-emerald-500/30 rounded-full text-xs text-emerald-400 font-medium">
          Demo
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={scenario.id}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="space-y-4"
          >
            {/* User message */}
            <div className="flex justify-end">
              <div className="msg-bubble user max-w-[80%]">
                {scenario.userMessage}
              </div>
            </div>

            {/* Reasoning steps */}
            <AnimatePresence>
              {showReasoning && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  className="reasoning-wrap"
                >
                  <div className="reasoning-toggle justify-center">
                    <span className="text-center">🧠 AI Thinking...</span>
                  </div>
                  <div className="reasoning-steps-list">
                    {scenario.reasoningSteps.map((step, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: i < visibleSteps ? 1 : 0.3, x: 0 }}
                        transition={{ delay: i * 0.1 }}
                        className="reasoning-step"
                      >
                        <span>
                          {i < visibleSteps ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          ) : (
                            <Loader2 className="w-4 h-4 animate-spin text-purple-400" />
                          )}
                        </span>
                        <div>
                          <div className={`reasoning-step-label ${step.type}`}>
                            {step.label}
                          </div>
                          <div className="reasoning-step-detail">{step.detail}</div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* AI Response */}
            <AnimatePresence>
              {showOutput && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-end gap-2"
                >
                  <div className="msg-avatar assistant">🤖</div>
                  <div className="max-w-[80%]">
                    <div className="msg-bubble assistant">
                      {scenario.aiResponse}
                    </div>
                    {scenario.structuredOutput && (
                      <div className="mt-2 p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
                        <div className="text-sm font-semibold text-emerald-400 mb-2">
                          {scenario.structuredOutput.title}
                        </div>
                        <div className="space-y-1">
                          {Object.entries(scenario.structuredOutput.details).map(([key, val]) => (
                            <div key={key} className="flex justify-between text-xs">
                              <span className="text-muted-foreground">{key}</span>
                              <span className="text-white font-medium">{val}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Decorative elements */}
      <div className="absolute -top-4 -right-4 w-24 h-24 bg-emerald-500/20 rounded-full blur-2xl" />
      <div className="absolute -bottom-4 -left-4 w-32 h-32 bg-emerald-500/10 rounded-full blur-3xl" />
    </div>
  );
}
