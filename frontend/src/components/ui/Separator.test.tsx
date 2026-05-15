import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Separator } from "./Separator";

describe("Separator", () => {
  it("renders horizontal by default", () => {
    render(<Separator data-testid="sep" />);
    const el = screen.getByTestId("sep");
    expect(el.className).toContain("h-[1px]");
    expect(el.className).toContain("w-full");
  });

  it("renders vertical when orientation='vertical'", () => {
    render(<Separator data-testid="sep" orientation="vertical" />);
    const el = screen.getByTestId("sep");
    expect(el.className).toContain("h-full");
    expect(el.className).toContain("w-[1px]");
  });

  it("has bg-border-1 class", () => {
    render(<Separator data-testid="sep" />);
    expect(screen.getByTestId("sep").className).toContain("bg-border-1");
  });

  it("forwards data-testid", () => {
    render(<Separator data-testid="my-sep" />);
    expect(screen.getByTestId("my-sep")).toBeInTheDocument();
  });

  it("merges className", () => {
    render(<Separator data-testid="sep" className="extra" />);
    expect(screen.getByTestId("sep").className).toContain("extra");
  });
});
