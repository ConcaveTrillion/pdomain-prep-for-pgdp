// App.test.tsx — Vitest tests for App shell routing.
// Phase 2.4: AppShell + SuiteSiblingsProvider mocks added (#266).
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "./test/server";
import type * as React from "react";

// Phase 2.4: Mock @concavetrillion/pd-ui/shell so AppShell renders a
// transparent pass-through in jsdom — no Zustand store setup, no real
// grid layout. The mock preserves the slot-forwarding contract (header,
// main, children) so downstream tests can assert on TopNav + Routes.
vi.mock("@concavetrillion/pd-ui/shell", () => ({
  AppShell: ({
    header,
    main,
    children,
  }: {
    appId?: string;
    appDisplayName?: string;
    appIconUrl?: string;
    header?: React.ReactNode;
    main?: React.ReactNode;
    children?: React.ReactNode;
    launcherSlot?: string;
    deployMode?: string;
    uiPrefsConfig?: unknown;
  }) => (
    <div data-testid="pd-ui-app-shell">
      <div data-testid="pd-ui-app-shell-header">{header}</div>
      <div data-testid="pd-ui-app-shell-main">{main}</div>
      {children}
    </div>
  ),
  SuiteSiblingsProvider: ({
    children,
  }: {
    value?: unknown;
    children?: React.ReactNode;
  }) => <>{children}</>,
  // Other exports that App.tsx imports as types — provide no-op values so
  // TypeScript import side-effects compile cleanly.
}));

// Mock @concavetrillion/pd-ui/canvas to prevent the konva/lib/index-node.js
// -> require("canvas") chain. PageWorkbenchPage transitively imports this
// module; hoisting the mock here prevents the native addon from loading.
vi.mock("@concavetrillion/pd-ui/canvas", () => ({
  PageImageCanvas: ({
    children,
  }: {
    src?: string;
    page?: { width: number; height: number };
    words?: unknown[];
    children?: {
      selection?: () => React.ReactNode;
      tool?: () => React.ReactNode;
      underlay?: () => React.ReactNode;
      overlay?: () => React.ReactNode;
      hud?: () => React.ReactNode;
    };
  }) => (
    <div data-testid="pd-ui-canvas">
      {children?.selection?.()}
      {children?.tool?.()}
    </div>
  ),
}));

// Mock react-konva and related canvas modules to prevent Node.js canvas
// native addon from being required in jsdom environments.
vi.mock("react-konva", () => ({
  Stage: ({
    children,
    width,
    height,
    "data-testid": tid,
  }: {
    children?: React.ReactNode;
    width?: number;
    height?: number;
    "data-testid"?: string;
  }) => (
    <div
      data-testid={tid ?? "konva-stage"}
      data-width={width}
      data-height={height}
    >
      {children}
    </div>
  ),
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: () => <div data-testid="konva-rect" />,
  Image: () => <div data-testid="konva-image" />,
}));

vi.mock("use-image", () => ({
  __esModule: true,
  default: () => [null, "loaded"],
}));

import App from "./App";

// App.tsx uses useMatch/useNavigate/useLocation which require a Router context.
// In production, main.tsx wraps App in <BrowserRouter>. Tests use MemoryRouter.
// App also relies on the QueryClient from main.tsx; we provide a fresh one per test.
function renderApp(initialPath = "/") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// Helper: setup MSW handlers for the root / project-list route.
function withNoProjects() {
  server.use(
    http.get("/api/data/projects", () => HttpResponse.json([])),
    http.get("/api/server-info", () =>
      HttpResponse.json({
        host: "localhost",
        port: 8765,
        url: "http://localhost:8765",
      }),
    ),
  );
}

describe("App: routing shell", () => {
  it("renders the top-nav brand on the root route", async () => {
    withNoProjects();
    renderApp();
    await waitFor(() => {
      // TopNav renders brand text "pgdp-prep" regardless of route.
      expect(screen.getByText("pgdp-prep")).toBeInTheDocument();
    });
  });

  it("renders project-list view on / when no projects", async () => {
    withNoProjects();
    renderApp();
    await waitFor(() => {
      expect(screen.getByText("pgdp-prep")).toBeInTheDocument();
    });
    // pd-ui AppShell main slot is present with route content.
    expect(screen.getByTestId("pd-ui-app-shell-main")).toBeInTheDocument();
  });

  it("Phase 2.4: pd-ui AppShell wrapper is present (data-testid=app-shell)", async () => {
    withNoProjects();
    renderApp();
    await waitFor(() => {
      expect(screen.getByText("pgdp-prep")).toBeInTheDocument();
    });
    // Outer wrapper preserves data-testid=app-shell for any Playwright selectors.
    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
    // pd-ui AppShell mock renders inside it.
    expect(screen.getByTestId("pd-ui-app-shell")).toBeInTheDocument();
  });

  it("Phase 2.4: TopNav renders inside AppShell header slot", async () => {
    withNoProjects();
    renderApp();
    await waitFor(() => {
      expect(screen.getByText("pgdp-prep")).toBeInTheDocument();
    });
    const headerSlot = screen.getByTestId("pd-ui-app-shell-header");
    // TopNav brand text is a descendant of the AppShell header slot.
    expect(headerSlot.querySelector("[data-testid='top-nav']")).not.toBeNull();
  });

  it("Phase 2.4: search pill renders in AppShell header slot", async () => {
    withNoProjects();
    renderApp();
    await waitFor(() => {
      expect(screen.getByText("pgdp-prep")).toBeInTheDocument();
    });
    const headerSlot = screen.getByTestId("pd-ui-app-shell-header");
    // The search pill button should be inside the header slot.
    const searchBtn = headerSlot.querySelector("[aria-label='Search (⌘K)']");
    expect(searchBtn).not.toBeNull();
  });

  it("Phase 2.4: Routes render inside AppShell main slot", async () => {
    withNoProjects();
    renderApp();
    await waitFor(() => {
      expect(screen.getByText("pgdp-prep")).toBeInTheDocument();
    });
    // All route-level content is inside the main slot.
    expect(screen.getByTestId("pd-ui-app-shell-main")).toBeInTheDocument();
  });

  it("Phase 2.4: GAP-1 — ServerInfoFooter is app-local inside main slot", async () => {
    withNoProjects();
    renderApp();
    await waitFor(() => {
      expect(screen.getByText("pgdp-prep")).toBeInTheDocument();
    });
    const mainSlot = screen.getByTestId("pd-ui-app-shell-main");
    // ServerInfoFooter fetches /api/server-info and renders a <footer> element.
    // After data loads it renders inside main (GAP-1: app-local footer zone).
    await waitFor(() => {
      const footerEl = mainSlot.querySelector("footer");
      expect(footerEl).not.toBeNull();
    });
  });
});
