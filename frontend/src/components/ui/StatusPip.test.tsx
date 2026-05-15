import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusPip } from "./StatusPip";

describe("StatusPip", () => {
  const statuses = ["done", "running", "queued", "error", "review"] as const;

  it.each(statuses)("renders correct dot class for status=%s", (status) => {
    const { container } = render(
      <StatusPip status={status} data-testid="pip" />,
    );
    const dot = container.querySelector("span > span");
    expect(dot?.className).toContain(`bg-status-${status}`);
  });

  it("renders label when provided", () => {
    render(<StatusPip status="done" label="Finished" data-testid="pip" />);
    expect(screen.getByText("Finished")).toBeInTheDocument();
  });

  it("does not render label span when label omitted", () => {
    render(<StatusPip status="running" data-testid="pip" />);
    // Only 1 child span (the dot), no text span
    expect(screen.queryByText("running")).not.toBeInTheDocument();
  });

  it("forwards data-testid", () => {
    render(<StatusPip status="error" data-testid="my-pip" />);
    expect(screen.getByTestId("my-pip")).toBeInTheDocument();
  });

  it("merges className", () => {
    render(<StatusPip status="queued" className="extra" data-testid="pip" />);
    expect(screen.getByTestId("pip").className).toContain("extra");
  });
});
