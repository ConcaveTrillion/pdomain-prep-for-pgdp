// App.tsx — SPA root: router, QueryClient provider, and route table.
//
// Phase 2.4: replaced local AppShell wrapper with pd-ui AppShell (#266).
//
// Slot mapping vs former local layout (components/shell/AppShell.tsx):
//   header   ← TopNav (was header slot of custom AppShell)
//   main     ← Routes block + banners + SearchModal + HotkeyHelpModal
//   footer   — pd-ui AppShell has no footer zone (GAP-1); ServerInfoFooter
//              is kept app-local inside the main slot using flex-col layout.
//
// GAP-1: pd-ui AppShell has no footer zone. ServerInfoFooter (formerly in
//         the 32px footer grid row of components/shell/AppShell.tsx) is
//         kept app-local: rendered as a flex-col sibling of the routes div
//         inside the `main` slot. Resolve if pd-ui adds a footer zone.
//
// GAP-2: GET /api/ui-prefs backend endpoint not yet implemented — uiPrefsConfig
//         load() returns localStorage-seeded defaults; persist callbacks write to
//         localStorage as a stopgap. Full server-side persistence deferred to
//         when pd-ocr-ops mounts /api/ui-prefs in the FastAPI app.
//         Phase 2.5: shim reconciled — reads/writes bare string (not JSON envelope).
//
// GAP-3: POST /api/ui-prefs backend endpoint not yet implemented — same as GAP-2.
//
// GAP-4: GET /api/suite/installed + POST /api/suite/launch backend endpoints not
//         yet implemented. SuiteSiblingsProvider fetchInstalled returns [] (no-op);
//         postLaunch returns requires-host-config. Real wiring blocked on pd-ocr-ops
//         mounting /api/suite/* routes in the FastAPI app.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  Route,
  Routes,
  Link,
  useLocation,
  useMatch,
  useNavigate,
} from "react-router-dom";
import { useHotkeys } from "react-hotkeys-hook";
import {
  AppShell,
  SuiteSiblingsProvider,
  type UIPrefsConfig,
  type InstalledApp,
  type LaunchResult,
} from "@concavetrillion/pd-ui/shell";
import { api, getAuthToken } from "./api/client";
import type { components } from "./api/types.gen";
import { AwaitingReviewBanner } from "./components/AwaitingReviewBanner";
import { ServerInfoFooter } from "./components/ServerInfoFooter";
import { TooltipProvider } from "./components/ui/Tooltip";
import { HotkeyHelpModal } from "./components/shell/HotkeyHelpModal";
import { SearchModal } from "./components/shell/SearchModal";
import { TopNav } from "./components/shell/TopNav";
import { UserMenu } from "./components/shell/UserMenu";
import { useUiPrefs, THEME_STORAGE_KEY } from "./stores/uiPrefs";

type ReviewStatusResponse = components["schemas"]["ReviewStatusResponse"];
import { JobsPage } from "./pages/JobsPage";
import { LoginPage } from "./pages/LoginPage";
import { ProjectListPage } from "./pages/ProjectListPage";
import { ProjectConfigurePage } from "./pages/ProjectConfigurePage";
import { PageWorkbenchPage } from "./pages/PageWorkbenchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ProjectReviewQueuePage } from "./pages/ProjectReviewQueuePage";
import { TextReviewPage } from "./pages/TextReviewPage";
import { CropsGridPage } from "./pages/CropsGridPage";

// ── Phase 2.5: UIPrefsConfig shim (GAP-2, GAP-3 reconciled) ────────────────
//
// The backend does not yet expose GET/POST /api/ui-prefs endpoints.
// Phase 2.5 reconciliation: the local uiPrefs.ts store now writes theme as
// a bare string to THEME_STORAGE_KEY ("pgdp.uiPrefs"). The load() and
// persistCommon() shims read/write the same bare-string format so both
// stores stay in sync via localStorage.
//
// GAP-2: GET /api/ui-prefs not yet implemented — load() seeds from localStorage.
// GAP-3: POST /api/ui-prefs not yet implemented — persistCommon writes to localStorage.
// Full server-side persistence is deferred until pd-ocr-ops mounts /api/ui-prefs.
//
// GAP-5 (from uiPrefs.ts): pd-ui's UIPrefs.theme is 'dark' | 'light' (no
// 'system'). The local store supports 'system'; when theme is 'system' the
// pd-ui AppShell receives the resolved effective value ('dark' or 'light').
const UI_PREFS_CONFIG: UIPrefsConfig = {
  load: async () => {
    // Seed theme from localStorage bare string (Phase 2.5 format).
    // Fall back to effective resolved value if theme is 'system'.
    let theme: "dark" | "light" = "light";
    try {
      const raw = localStorage.getItem(THEME_STORAGE_KEY);
      if (raw === "dark") theme = "dark";
      else if (raw === "light") theme = "light";
      else if (raw === "system") {
        // Resolve 'system' to effective value for pd-ui's factory (no 'system' in UIPrefs).
        try {
          theme = window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light";
        } catch {
          theme = "light";
        }
      }
    } catch {
      // localStorage unavailable or unexpected error
    }
    return { theme, density: "normal", fontScale: 1.0 };
  },
  persistCommon: async (prefs) => {
    // GAP-2: no backend — write theme back to localStorage as bare string.
    // Only writes 'dark' or 'light'; 'system' is the local store's concern.
    try {
      const current = localStorage.getItem(THEME_STORAGE_KEY);
      // Don't overwrite 'system' with its resolved value — let the local store own that.
      if (current !== "system") {
        localStorage.setItem(THEME_STORAGE_KEY, prefs.theme);
      }
    } catch {
      // ignore
    }
  },
  persistApp: async (_appPrefs) => {
    // GAP-3: no backend — no-op until pd-ocr-ops mounts /api/ui-prefs.
  },
};

// ── Phase 2.4: SuiteSiblings fetch/launch shims (GAP-4) ─────────────────────
//
// The backend does not yet expose /api/suite/installed or /api/suite/launch.
// fetchInstalled returns an empty list (no siblings shown in launcher).
// postLaunch returns requires-host-config.
async function fetchInstalled(): Promise<InstalledApp[]> {
  // GAP-4: when pd-ocr-ops mounts /api/suite/* in FastAPI, replace with:
  //   const res = await fetch("/api/suite/installed");
  //   if (!res.ok) return [];
  //   return (await res.json()) as InstalledApp[];
  return [];
}

async function postLaunch(id: string): Promise<LaunchResult> {
  // GAP-4: when pd-ocr-ops mounts /api/suite/* in FastAPI, replace with:
  //   const res = await fetch(`/api/suite/launch`, {
  //     method: "POST", body: JSON.stringify({ id }),
  //     headers: { "Content-Type": "application/json" },
  //   });
  //   return (await res.json()) as LaunchResult;
  return { kind: "requires-host-config", siblingId: id };
}

export default function App() {
  const { setSearchOpen } = useUiPrefs();
  const projectMatch = useMatch("/projects/:projectId/*");
  const [hotkeyHelpOpen, setHotkeyHelpOpen] = useState(false);

  useHotkeys("?", () => setHotkeyHelpOpen(true), { preventDefault: true });

  return (
    <TooltipProvider>
      {/*
       * Phase 2.4: SuiteSiblingsProvider supplies the launcher context
       * that pd-ui AppShell's LauncherSlot reads via useSuiteSiblingsContext().
       * fetchInstalled / postLaunch are shims (GAP-4) until pd-ocr-ops
       * mounts /api/suite/* in the FastAPI app.
       */}
      <SuiteSiblingsProvider value={{ fetchInstalled, postLaunch }}>
        {/*
         * Outer wrapper preserves data-testid="app-shell" for any integration
         * tests or Playwright selectors that anchor on the shell root.
         */}
        <div data-testid="app-shell" className="h-screen w-full">
          <AppShell
            appId="pd-prep-for-pgdp"
            appDisplayName="pgdp-prep"
            appIconUrl="/static/icon.svg"
            launcherSlot="header"
            deployMode="local"
            uiPrefsConfig={UI_PREFS_CONFIG}
            header={
              <TopNav
                centerSlot={
                  <button
                    onClick={() => setSearchOpen(true)}
                    className="flex w-full items-center gap-2 rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-400 hover:border-slate-600 hover:text-slate-300 transition-colors"
                    aria-label="Search (⌘K)"
                  >
                    <span className="flex-1 text-left">Search projects…</span>
                    <kbd className="ml-auto text-xs text-slate-500 font-mono">
                      ⌘K
                    </kbd>
                  </button>
                }
                rightSlot={
                  <>
                    <OpenTasksBell />
                    <UserMenu />
                  </>
                }
              />
            }
            main={
              /*
               * GAP-1: pd-ui AppShell has no footer zone. ServerInfoFooter
               * is kept app-local as a flex-col sibling of the routes div,
               * pinned to the bottom of the main zone via flex layout.
               */
              <div className="flex flex-col h-full overflow-hidden">
                <SearchModal />
                <HotkeyHelpModal
                  open={hotkeyHelpOpen}
                  onClose={() => setHotkeyHelpOpen(false)}
                />
                <AuthGuard />
                {/* Global banner slot — rendered above all page content */}
                <div className="banner-slot mx-auto max-w-7xl px-4 pt-4 space-y-2">
                  {projectMatch && <AwaitingReviewBanner />}
                </div>
                <div className="flex-1 overflow-auto mx-auto max-w-7xl p-4 w-full">
                  <Routes>
                    <Route path="/login" element={<LoginPage />} />
                    <Route path="/" element={<ProjectListPage />} />
                    <Route path="/jobs" element={<JobsPage />} />
                    <Route
                      path="/projects/:projectId"
                      element={<ProjectConfigurePage />}
                    />
                    <Route
                      path="/projects/:projectId/pages/:idx0"
                      element={<PageWorkbenchPage />}
                    />
                    <Route
                      path="/projects/:projectId/pages/:idx0/review"
                      element={<TextReviewPage />}
                    />
                    <Route
                      path="/projects/:projectId/crops"
                      element={<CropsGridPage />}
                    />
                    <Route
                      path="/projects/:projectId/review"
                      element={<ProjectReviewQueuePage />}
                    />
                    <Route path="/settings" element={<SettingsPage />} />
                  </Routes>
                </div>
                {/* GAP-1: ServerInfoFooter pinned at bottom of main zone */}
                <ServerInfoFooter />
              </div>
            }
          />
        </div>
      </SuiteSiblingsProvider>
    </TooltipProvider>
  );
}

/**
 * Bell icon in the navbar showing unreviewed-page count for the active project.
 * Only renders when the user is on a project route and there are pages
 * awaiting review with a parked build_package job.
 */
function OpenTasksBell() {
  const match = useMatch("/projects/:projectId/*");
  const projectId = match?.params?.projectId ?? null;

  const status = useQuery({
    queryKey: ["review-status", projectId],
    queryFn: () =>
      api.get<ReviewStatusResponse>(
        `/api/data/projects/${projectId}/review-status`,
      ),
    refetchInterval: 1000,
    enabled: projectId !== null,
  });

  const count = status.data?.awaiting_review_job_id
    ? status.data.unreviewed_count
    : 0;

  if (!projectId || count === 0) return null;

  return (
    <Link
      to={`/projects/${projectId}/review`}
      className="relative flex items-center text-slate-600 hover:text-slate-900"
      title={`${count} page${count === 1 ? "" : "s"} awaiting review`}
      aria-label={`Open tasks: ${count} page${count === 1 ? "" : "s"} awaiting review`}
    >
      <span className="text-base">🔔</span>
      <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-0.5 text-[10px] font-bold text-white">
        {count}
      </span>
    </Link>
  );
}

/** In JWT mode: redirect to /login if no token, OR on any 401. */
function AuthGuard() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();

  // Eager redirect: direct nav to a protected route with no token.
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- __ENV__ is an untyped runtime injection from env.js
    const env = (window as any).__ENV__ ?? {};
    if (env.AUTH_MODE !== "jwt") return;
    if (location.pathname === "/login") return;
    if (!getAuthToken()) void navigate("/login", { replace: true });
  }, [navigate, location.pathname]);

  // Reactive redirect: any cached query that 401s.
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- __ENV__ is an untyped runtime injection from env.js
    const env = (window as any).__ENV__ ?? {};
    if (env.AUTH_MODE !== "jwt") return;
    if (location.pathname === "/login") return;

    const cache = queryClient.getQueryCache();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- QueryCacheNotifyEvent type not exported from @tanstack/react-query
    const unsub = cache.subscribe((event: any) => {
      const status = event?.query?.state?.error?.status;
      if (status === 401) void navigate("/login", { replace: true });
    });
    return () => unsub();
  }, [queryClient, navigate, location.pathname]);
  return null;
}
