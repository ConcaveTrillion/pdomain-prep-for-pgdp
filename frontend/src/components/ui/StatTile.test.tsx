import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatTile } from "./StatTile";

describe("StatTile", () => {
  it("renders value", () => {
    render(<StatTile value={42} label="pages" data-testid="st" />);
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders label", () => {
    render(<StatTile value={7} label="errors" data-testid="st" />);
    expect(screen.getByText("errors")).toBeInTheDocument();
  });

  it("renders string value", () => {
    render(<StatTile value="100%" label="complete" data-testid="st" />);
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("value has text-ink-1 class", () => {
    render(<StatTile value={1} label="x" data-testid="st" />);
    const value = screen.getByText("1");
    expect(value.className).toContain("text-ink-1");
  });

  it("label has text-ink-3 class", () => {
    render(<StatTile value={1} label="myLabel" data-testid="st" />);
    const lbl = screen.getByText("myLabel");
    expect(lbl.className).toContain("text-ink-3");
  });

  it("forwards data-testid", () => {
    render(<StatTile value={0} label="none" data-testid="my-tile" />);
    expect(screen.getByTestId("my-tile")).toBeInTheDocument();
  });

  it("merges className", () => {
    render(
      <StatTile value={5} label="foo" className="extra" data-testid="st" />,
    );
    expect(screen.getByTestId("st").className).toContain("extra");
  });
});
