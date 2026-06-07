import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { parseSwapPreview, SimulationPreview } from "@/components/agent-app/MainApp";

vi.mock("framer-motion", () => {
  const R = require("react") as typeof import("react");
  const skip = new Set(["animate", "initial", "exit", "variants", "transition", "whileHover", "whileTap", "layout"]);
  const motion = new Proxy({}, { get: (_t, tag: string) => R.forwardRef<HTMLElement, Record<string, unknown>>((props, ref) => {
    const dom = Object.fromEntries(Object.entries(props).filter(([k]) => !skip.has(k)));
    return R.createElement(tag, { ...dom, ref });
  }) });
  return { AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>, motion };
});

// A real, deserializable Solana stake tx (build_stake_tx output).
const REAL_TX = "AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAQAHFTnVMjVSDFnu/k/rQ2FyXNUz6Gwef6n3r80+3fz6w1zYDUqWX4BuEEA/VL9TgZ+eeBTEEiYf/TUQ4ar8IIR3uzkZRUF9VuHZ6wcfKj2FHUA6aUaHxAg0OtgVXsx9N8hBUy1HOE/fpzc0YyaMu7byEsrzeeap7YCgrv22YNduyXBjScgIgVkpa3jArJQWmYUMSlKy8Yqc4Nd5htLkigsWs3Rk3E4Sv8QEiMWNMMq12yJv8PQ15IaqWYNPOQ32njvjkXsetPbPvT4XKTjvlNCcr0LlAkwPxS0xGgibToHWM+Drl4e+rxpkjwQBPX1htBlFy35opL8UclhwRjYt1cavZ/+eUSPuPoI0D4hbmOtnls9hjeu2VYMJ4+V5BEAdVCEiJqIdmklnVTL3GrXKI61rcFwE4jsO/6OYROzRbst6fL4C02P/flNunOfK8RqucbvlTfpEwkb/RSWcYARRnDNScjXfsLhf7Ff9NofcPgIyAbMytm5ggTyKwmR+JqgXUXARVe+AtVp7YN9gOSgfz/XhEdXdo+NyI1UaxM4bI7ZZUviK/cJgVle7nN1zfk42fXVgwXU5RvVGMdH6Je91sSFkgCMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMGRm/lIRcy/+ytunLDm+e8jOW7xfcSayxDmzpAAAAABHnVW/IxwG7udMVuzmgVB/2xst6j9I5RArHNola8E48G3fbh12Whk9nL4UbO63msHLSF7V9bN5E6jPWFfv8AqU9LbA5BCP0qaiR46uCsxZ2yG7Tt9RHBYs9gLR4MCQH7jJclj04kifG7PRApFI4NgwtaE5na/xCEBI572Nvp+Fm0P/on9df2SnTAmx8pWHneSwmrNt/J3VFLMhqns4zl6Pol220C5VH2HRVY47Ipk1xW8lqQZw4zzNPh1t4TidCgBw8ABQLAXBUADwAJAwQXAQAAAAAAEwYABQAmDhEBAQ4CAAUMAgAAAEBCDwAAAAAAEQEFAREQPBESAAUJBAomLQ0QFBAlIwYiJAkLJiwhJRIRESglCAMBECcSKRoLAhYZGBEXFQwHECoREiACHAQeHx0bKy3BIJszQdacgQcDAAAAJmQAARpkAQIRAWQCA0BCDwAAAAAAVeALAAAAAAAyABQRAwUAAAEJA++NDvfBY9wM8+T289gdVvqWdTV+9AEKKkjR0SSNiSvGBo+WlJCRkwU/AY45mI5odMuyskXo3rFRKyDcT6cBlAl6zvVyu1feVMo2uZQVBpiUl5ydlgQVmYub0dB75Rt960M1yqmEaKL7yDrqsb3qW/ZzGM4JHJ36b/YEBggNAwA=";

describe("sign flow persists the signature", () => {
  it("clicking Sign calls onSigned(signature) and shows ✅ sent (so the parent can persist it)", async () => {
    const onSigned = vi.fn();
    // mock Phantom: signAndSendTransaction resolves with a signature
    (window as any).phantom = { solana: { isPhantom: true, signAndSendTransaction: vi.fn().mockResolvedValue({ signature: "SIGNED_BY_PHANTOM_abc123" }) } };
    // recordTx posts to /api/v1/transactions — stub fetch
    (global as any).fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });

    const preview = parseSwapPreview(JSON.stringify({
      status: "ok", action: "stake", is_stake: true, staking_protocol: "Jito", receipt_token_symbol: "jitoSOL",
      swapTransaction: REAL_TX, ui_out_amount: 0.00078, ui_in_amount: 0.001, in_symbol: "SOL", out_symbol: "jitoSOL",
      from_token_symbol: "SOL", to_token_symbol: "Jito JitoSOL", route_summary: "Stake via Jito", liquid: true, apy: 5.18,
    }))!;

    render(<SimulationPreview preview={preview} solanaAddress="4tknrGRLnUQTJXwfRJ2SNe7whTpdnxSTL9qSVgeLtReF" walletType="phantom" onSigned={onSigned} />);

    fireEvent.click(screen.getByRole("button", { name: /Stake in Phantom/i }));

    await waitFor(() => expect(onSigned).toHaveBeenCalledWith("SIGNED_BY_PHANTOM_abc123"));
    await waitFor(() => expect(screen.getByText(/Transaction sent/i)).toBeInTheDocument());
    // button gone after signing
    expect(screen.queryByRole("button", { name: /Stake in Phantom/i })).not.toBeInTheDocument();
  });
});
