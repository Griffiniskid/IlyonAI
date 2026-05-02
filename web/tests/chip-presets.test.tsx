import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

import { ChipPresets } from "@/components/agent/ChipPresets";

describe("ChipPresets", () => {
  it("emits a preset prompt on click", () => {
    const onSelect = vi.fn();
    render(<ChipPresets onSelect={onSelect} disabled={false} />);
    fireEvent.click(screen.getByText(/conservative/i));
    expect(onSelect).toHaveBeenCalledWith(expect.stringContaining("low-risk only"));
  });
});
