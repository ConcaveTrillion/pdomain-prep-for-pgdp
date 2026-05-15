import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

type Theme = "light" | "dark" | "system";

interface UiPrefsState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  searchOpen: boolean;
  setSearchOpen: (v: boolean) => void;
}

function resolveTheme(theme: Theme): "light" | "dark" {
  if (theme === "system") {
    if (typeof window === "undefined" || !window.matchMedia) return "light";
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }
  return theme;
}

export const useUiPrefs = create<UiPrefsState>()(
  persist(
    (set) => ({
      theme: "light",
      setTheme: (theme) => set({ theme }),
      searchOpen: false,
      setSearchOpen: (searchOpen) => set({ searchOpen }),
    }),
    {
      name: "pgdp.uiPrefs",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ theme: state.theme }),
    },
  ),
);

// Apply theme to <html> on store changes.
useUiPrefs.subscribe((state) => {
  document.documentElement.setAttribute(
    "data-theme",
    resolveTheme(state.theme),
  );
});

// Apply immediately on module load (so first render matches localStorage).
document.documentElement.setAttribute(
  "data-theme",
  resolveTheme(useUiPrefs.getState().theme),
);
