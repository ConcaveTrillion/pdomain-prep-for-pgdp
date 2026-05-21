// uiPrefs.test.ts — Phase 2.5 store tests.
//
// The store was migrated from zustand `create` + `persist` middleware to a
// plain `createStore` with manual localStorage (key: "pgdp.uiPrefs").
// The persist-middleware envelope ({state:{theme}}) is gone — theme is now
// stored as a bare string.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { useUiPrefs, THEME_STORAGE_KEY } from "./uiPrefs";

describe("useUiPrefs", () => {
  beforeEach(() => {
    localStorage.clear();
    // Reset store state directly (setState merges, so we cover both fields).
    useUiPrefs.setState({ theme: "light", searchOpen: false });
    // Remove DOM attribute set by previous test's applyTheme.
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
    it("persists theme to localStorage after setTheme (bare string, not envelope)", () => {
      useUiPrefs.getState().setTheme("dark");
      const stored = localStorage.getItem(THEME_STORAGE_KEY);
      expect(stored).toBe("dark");
    });

    it("persists 'light' theme", () => {
      useUiPrefs.getState().setTheme("light");
      expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    });

    it("persists 'system' theme", () => {
      useUiPrefs.getState().setTheme("system");
      expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("system");
    });

    it("does not persist searchOpen to localStorage", () => {
      useUiPrefs.getState().setSearchOpen(true);
      // Only theme writes to localStorage; searchOpen has no persistence.
      const stored = localStorage.getItem(THEME_STORAGE_KEY);
      // Nothing should have been written (theme wasn't touched).
      expect(stored).toBeNull();
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
