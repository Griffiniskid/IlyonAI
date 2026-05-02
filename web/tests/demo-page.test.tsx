import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import React from "react";

import DemoPage from "@/app/demo/page";

describe("DemoPage", () => {
  it("renders the DemoChatFrame banner", () => {
    const { container } = render(<DemoPage />);
    expect(container.textContent).toContain("Sentinel scoring layered in");
  });
});
