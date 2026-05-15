import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Progress } from "./Progress";

describe("Progress", () => {
  it("renders with data-testid", () => {
    render(<Progress data-testid="prog" value={50} />);
    expect(screen.getByTestId("prog")).toBeInTheDocument();
  });

  it("has bg-bg-sunk class on root", () => {
    render(<Progress data-testid="prog" value={25} />);
    expect(screen.getByTestId("prog").className).toContain("bg-bg-sunk");
  });

  it("indicator translateX is correct for 0%", () => {
    const { container } = render(<Progress data-testid="prog" value={0} />);
    const indicator = container.querySelector("[style]");
    expect(indicator).not.toBeNull();
    expect((indicator as HTMLElement).style.transform).toBe(
      "translateX(-100%)",
    );
  });

  it("indicator translateX is correct for 100%", () => {
    const { container } = render(<Progress data-testid="prog" value={100} />);
    const indicator = container.querySelector("[style]");
    expect((indicator as HTMLElement).style.transform).toBe("translateX(-0%)");
  });

  it("indicator translateX is correct for 50%", () => {
    const { container } = render(<Progress data-testid="prog" value={50} />);
    const indicator = container.querySelector("[style]");
    expect((indicator as HTMLElement).style.transform).toBe("translateX(-50%)");
  });

  it("indicator has bg-accent class", () => {
    const { container } = render(<Progress data-testid="prog" value={75} />);
    const indicator = container.querySelector("[style]");
    expect((indicator as HTMLElement).className).toContain("bg-accent");
  });

  it("defaults value to 0", () => {
    const { container } = render(<Progress data-testid="prog" />);
    const indicator = container.querySelector("[style]");
    expect((indicator as HTMLElement).style.transform).toBe(
      "translateX(-100%)",
    );
  });
});
