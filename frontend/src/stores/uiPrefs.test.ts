import { describe, it, expect, beforeEach, vi } from "vitest";
import { useUiPrefs } from "./uiPrefs";

describe("useUiPrefs", () => {
  beforeEach(() => {
    localStorage.clear();
    useUiPrefs.setState({ theme: "light", searchOpen: false });
    // Reset attribute after setState (subscribe fires and sets "light")
    document.documentElement.removeAttribute("data-theme");
  });

  it("default theme is light", () => {
    expect(useUiPrefs.getState().theme).toBe("light");
  });

  it("setTheme updates the theme", () => {
    useUiPrefs.getState().setTheme("dark");
    expect(useUiPrefs.getState().theme).toBe("dark");
  });

  it("setTheme accepts system", () => {
    useUiPrefs.getState().setTheme("system");
    expect(useUiPrefs.getState().theme).toBe("system");
  });

  it("default searchOpen is false", () => {
    expect(useUiPrefs.getState().searchOpen).toBe(false);
  });

  it("setSearchOpen toggles the value", () => {
    useUiPrefs.getState().setSearchOpen(true);
    expect(useUiPrefs.getState().searchOpen).toBe(true);
    useUiPrefs.getState().setSearchOpen(false);
    expect(useUiPrefs.getState().searchOpen).toBe(false);
  });

  describe("persistence (localStorage)", () => {
    it("persists theme to localStorage after setTheme", async () => {
      useUiPrefs.getState().setTheme("dark");
      // persist middleware writes on next microtask
      await new Promise((r) => setTimeout(r, 0));
      const stored = localStorage.getItem("pgdp.uiPrefs");
      expect(stored).not.toBeNull();
      const parsed = JSON.parse(stored!);
      expect(parsed.state.theme).toBe("dark");
    });

    it("does not persist searchOpen", async () => {
      useUiPrefs.getState().setSearchOpen(true);
      await new Promise((r) => setTimeout(r, 0));
      const stored = localStorage.getItem("pgdp.uiPrefs");
      if (stored) {
        const parsed = JSON.parse(stored);
        expect(parsed.state.searchOpen).toBeUndefined();
      }
    });
  });

  describe("document.documentElement [data-theme] attribute", () => {
    it("sets data-theme to dark after setTheme('dark')", () => {
      useUiPrefs.getState().setTheme("dark");
      expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    });

    it("sets data-theme to light after setTheme('light')", () => {
      useUiPrefs.getState().setTheme("dark");
      useUiPrefs.getState().setTheme("light");
      expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    });

    it("resolves system theme via matchMedia (dark OS)", () => {
      vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
        matches: query === "(prefers-color-scheme: dark)",
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }));
      useUiPrefs.getState().setTheme("system");
      expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
      vi.restoreAllMocks();
    });

    it("resolves system theme via matchMedia (light OS)", () => {
      vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }));
      useUiPrefs.getState().setTheme("system");
      expect(document.documentElement.getAttribute("data-theme")).toBe("light");
      vi.restoreAllMocks();
    });
  });
});
