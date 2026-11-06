import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConnectionPill } from "@/components/dashboard/connection-pill";

describe("ConnectionPill", () => {
  it("announces a live realtime connection", () => {
    render(<ConnectionPill connected />);
    expect(screen.getByLabelText("Realtime connection live")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("announces an offline connection", () => {
    render(<ConnectionPill connected={false} />);
    expect(screen.getByLabelText("Realtime connection offline")).toBeInTheDocument();
    expect(screen.getByText("Offline")).toBeInTheDocument();
  });
});
