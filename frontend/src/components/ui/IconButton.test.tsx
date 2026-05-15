import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IconButton } from "./IconButton";

describe("IconButton", () => {
  it("renders children", () => {
    render(<IconButton data-testid="ib">X</IconButton>);
    expect(screen.getByTestId("ib")).toBeInTheDocument();
  });

  it("applies icon size (h-9 w-9) class", () => {
    render(<IconButton data-testid="ib">X</IconButton>);
    const btn = screen.getByTestId("ib");
    expect(btn.className).toContain("h-9");
    expect(btn.className).toContain("w-9");
  });

  it("forwards data-testid", () => {
    render(<IconButton data-testid="icon-btn">+</IconButton>);
    expect(screen.getByTestId("icon-btn")).toBeInTheDocument();
  });

  it("forwards variant prop", () => {
    render(
      <IconButton variant="danger" data-testid="ib">
        D
      </IconButton>,
    );
    const btn = screen.getByTestId("ib");
    expect(btn.className).toContain("bg-red-500");
  });
});
