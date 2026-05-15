import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Card, CardContent, CardHeader, CardTitle } from "./Card";

describe("Card", () => {
  it("renders with border-border-1 class", () => {
    render(<Card data-testid="card">content</Card>);
    const card = screen.getByTestId("card");
    expect(card.className).toContain("border-border-1");
  });

  it("renders with bg-bg-surface class", () => {
    render(<Card data-testid="card">content</Card>);
    expect(screen.getByTestId("card").className).toContain("bg-bg-surface");
  });

  it("forwards data-testid", () => {
    render(<Card data-testid="my-card">hi</Card>);
    expect(screen.getByTestId("my-card")).toBeInTheDocument();
  });

  it("merges additional className", () => {
    render(
      <Card data-testid="card" className="extra">
        x
      </Card>,
    );
    expect(screen.getByTestId("card").className).toContain("extra");
  });

  it("renders children", () => {
    render(<Card>Hello Card</Card>);
    expect(screen.getByText("Hello Card")).toBeInTheDocument();
  });

  it("CardHeader renders with correct class", () => {
    render(<CardHeader data-testid="hdr">head</CardHeader>);
    expect(screen.getByTestId("hdr").className).toContain("p-6");
  });

  it("CardTitle renders as h3", () => {
    render(<CardTitle>Title text</CardTitle>);
    const el = screen.getByText("Title text");
    expect(el.tagName).toBe("H3");
    expect(el.className).toContain("text-ink-1");
  });

  it("CardContent renders with p-6 pt-0", () => {
    render(<CardContent data-testid="cc">body</CardContent>);
    expect(screen.getByTestId("cc").className).toContain("p-6");
    expect(screen.getByTestId("cc").className).toContain("pt-0");
  });
});
