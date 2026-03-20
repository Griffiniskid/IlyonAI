/// <reference types="vitest" />
import { render, screen, fireEvent } from "@testing-library/react";
import { it, expect } from "vitest";
import { CommandPalette } from "../../components/layout/command-palette";

it("opens command palette with Ctrl+K", async () => {
  render(<CommandPalette />);
  fireEvent.keyDown(window, { key: "k", ctrlKey: true });
  expect(screen.getByPlaceholderText(/search tokens, wallets, pages/i)).toBeInTheDocument();
});
