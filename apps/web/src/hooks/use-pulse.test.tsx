import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePulse } from "@/hooks/use-pulse";
import { useRealtimeStore } from "@/stores/realtime-store";

function PulseProbe({ types }: { types: string[] }) {
  const pulsing = usePulse(...types);
  return <p data-testid="probe">{pulsing ? "pulsing" : "idle"}</p>;
}

describe("usePulse", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Reset the shared zustand store between tests.
    useRealtimeStore.setState({ connected: false, lastEvent: null });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("pulses for ~2 seconds after a matching event, then settles", () => {
    render(<PulseProbe types={["VERIFICATION_COMPLETE"]} />);
    expect(screen.getByTestId("probe")).toHaveTextContent("idle");

    act(() => {
      useRealtimeStore.getState().record("VERIFICATION_COMPLETE", {});
    });
    expect(screen.getByTestId("probe")).toHaveTextContent("pulsing");

    act(() => {
      vi.advanceTimersByTime(2100);
    });
    expect(screen.getByTestId("probe")).toHaveTextContent("idle");
  });

  it("ignores non-matching events", () => {
    render(<PulseProbe types={["VERIFICATION_COMPLETE"]} />);
    act(() => {
      useRealtimeStore.getState().record("TRAINEE_ENROLLED", {});
    });
    expect(screen.getByTestId("probe")).toHaveTextContent("idle");
  });

  it("matches any event in the list", () => {
    render(<PulseProbe types={["A", "B"]} />);
    act(() => {
      useRealtimeStore.getState().record("B", {});
    });
    expect(screen.getByTestId("probe")).toHaveTextContent("pulsing");
  });
});
