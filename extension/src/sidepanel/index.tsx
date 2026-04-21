import React from "react";
import { createRoot } from "react-dom/client";
import { SidePanelApp } from "./SidePanelApp";

const root = createRoot(document.getElementById("root")!);
root.render(<SidePanelApp />);
