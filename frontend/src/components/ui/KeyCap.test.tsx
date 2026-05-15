import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KeyCap } from "./KeyCap";

describe("KeyCap", () => {
  it("renders children inside a kbd element", () => {
    render(<KeyCap data-testid="kc">Ctrl</KeyCap>);
    const el = screen.getByTestId("kc");
    expect(el.tagName).toBe("KBD");
    expect(el.textContent).toBe("Ctrl");
  });

  it("has border-border-2 class", () => {
    render(<KeyCap data-testid="kc">K</KeyCap>);
    expect(screen.getByTestId("kc").className).toContain("border-border-2");
  });

  it("has bg-bg-raised class", () => {
    render(<KeyCap data-testid="kc">K</KeyCap>);
    expect(screen.getByTestId("kc").className).toContain("bg-bg-raised");
  });

  it("has text-ink-2 class", () => {
    render(<KeyCap data-testid="kc">K</KeyCap>);
    expect(screen.getByTestId("kc").className).toContain("text-ink-2");
  });

  it("forwards data-testid", () => {
    render(<KeyCap data-testid="my-kc">Enter</KeyCap>);
    expect(screen.getByTestId("my-kc")).toBeInTheDocument();
  });

  it("merges className", () => {
    render(
      <KeyCap data-testid="kc" className="extra">
        X
      </KeyCap>,
    );
    expect(screen.getByTestId("kc").className).toContain("extra");
  });
});
