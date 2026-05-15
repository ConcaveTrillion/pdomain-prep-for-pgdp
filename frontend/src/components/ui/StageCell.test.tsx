import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StageCell } from "./StageCell";

describe("StageCell", () => {
  const statuses = [
    "clean",
    "dirty",
    "not-run",
    "running",
    "failed",
    "na",
  ] as const;

  it("renders stage name", () => {
    render(<StageCell stage="OCR" status="clean" data-testid="sc" />);
    expect(screen.getByText("OCR")).toBeInTheDocument();
  });

  it.each(statuses)("renders correct dot class for status=%s", (status) => {
    const { container } = render(
      <StageCell stage="Step" status={status} data-testid="sc" />,
    );
    const dot = container.querySelector("div > span:first-child");
    expect(dot?.className).toContain(`bg-stage-${status}`);
  });

  it("has border-border-1 class on container", () => {
    render(<StageCell stage="Ingest" status="na" data-testid="sc" />);
    expect(screen.getByTestId("sc").className).toContain("border-border-1");
  });

  it("has bg-bg-surface class on container", () => {
    render(<StageCell stage="Pack" status="clean" data-testid="sc" />);
    expect(screen.getByTestId("sc").className).toContain("bg-bg-surface");
  });

  it("forwards data-testid", () => {
    render(<StageCell stage="Test" status="running" data-testid="my-cell" />);
    expect(screen.getByTestId("my-cell")).toBeInTheDocument();
  });

  it("merges className", () => {
    render(
      <StageCell
        stage="S"
        status="failed"
        className="extra"
        data-testid="sc"
      />,
    );
    expect(screen.getByTestId("sc").className).toContain("extra");
  });
});
