import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Input } from "./Input";

describe("Input", () => {
  it("renders an input element", () => {
    render(<Input data-testid="inp" />);
    expect(screen.getByTestId("inp")).toBeInTheDocument();
  });

  it("has border-border-2 class", () => {
    render(<Input data-testid="inp" />);
    expect(screen.getByTestId("inp").className).toContain("border-border-2");
  });

  it("has bg-bg-surface class", () => {
    render(<Input data-testid="inp" />);
    expect(screen.getByTestId("inp").className).toContain("bg-bg-surface");
  });

  it("has text-ink-1 class", () => {
    render(<Input data-testid="inp" />);
    expect(screen.getByTestId("inp").className).toContain("text-ink-1");
  });

  it("accepts value prop", () => {
    render(<Input data-testid="inp" value="hello" onChange={() => {}} />);
    expect(screen.getByDisplayValue("hello")).toBeInTheDocument();
  });

  it("accepts type prop", () => {
    render(<Input data-testid="inp" type="password" />);
    expect(screen.getByTestId("inp")).toHaveAttribute("type", "password");
  });

  it("forwards data-testid", () => {
    render(<Input data-testid="my-input" />);
    expect(screen.getByTestId("my-input")).toBeInTheDocument();
  });

  it("merges additional className", () => {
    render(<Input data-testid="inp" className="extra-class" />);
    expect(screen.getByTestId("inp").className).toContain("extra-class");
  });
});
