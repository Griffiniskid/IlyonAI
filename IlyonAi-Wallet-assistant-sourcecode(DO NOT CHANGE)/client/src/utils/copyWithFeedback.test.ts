import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { copyWithFeedback } from "./copyWithFeedback";

describe("copyWithFeedback", () => {
  const originalClipboard = navigator.clipboard;

  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  afterEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: originalClipboard,
    });
    vi.useRealTimers();
  });

  it("copies text and updates only the clicked button", async () => {
    vi.useFakeTimers();

    const button = document.createElement("button");
    button.textContent = "📋";
    button.style.color = "rgba(255,255,255,0.5)";

    await copyWithFeedback("pool-address-123", button, 1000);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("pool-address-123");
    expect(button.textContent).toBe("✓");
    expect(button.style.color).toBe("rgb(74, 222, 128)");

    vi.advanceTimersByTime(1000);

    expect(button.textContent).toBe("📋");
    expect(button.style.color).toBe("rgba(255, 255, 255, 0.5)");
  });
});
