import { render, screen } from "@testing-library/react";
import { CheckCheck } from "lucide-react";
import { describe, expect, it } from "vitest";

import { EmptyState, KpiCard, PulseCard } from "@/components/dashboard/kpi-card";

describe("KpiCard", () => {
  it("renders the label and value with an accessible label", () => {
    render(<KpiCard icon={CheckCheck} label="Verified" value={42} hint="of 100 claims" />);
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByLabelText("42")).toBeInTheDocument();
    expect(screen.getByText("of 100 claims")).toBeInTheDocument();
  });

  it("marks a pulsing card with data-pulsing", () => {
    const { container } = render(
      <PulseCard pulsing>
        <span>content</span>
      </PulseCard>,
    );
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper).toHaveAttribute("data-pulsing");
    expect(wrapper).toHaveClass("realtime-pulse");
  });

  it("does not pulse when idle", () => {
    const { container } = render(
      <PulseCard pulsing={false}>
        <span>content</span>
      </PulseCard>,
    );
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper).not.toHaveAttribute("data-pulsing");
    expect(wrapper).not.toHaveClass("realtime-pulse");
  });
});

describe("EmptyState", () => {
  it("renders title and hint", () => {
    render(
      <EmptyState icon={CheckCheck} title="No pending claims" hint="Claims appear here." />,
    );
    expect(screen.getByText("No pending claims")).toBeInTheDocument();
    expect(screen.getByText("Claims appear here.")).toBeInTheDocument();
  });
});
