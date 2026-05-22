import { describe, expect, it } from "vitest";

import pkg from "../package.json";

/**
 * Regression guard for ocr-container-meta #293.
 *
 * `@concavetrillion/pd-ui@0.1.0-alpha` shipped broken metadata: no
 * transitive deps (konva, react-konva, @radix-ui/*, clsx, react-virtuoso)
 * resolved on install. `0.1.0-alpha.1` re-published with valid metadata.
 *
 * The pin must stay at >= 0.1.0-alpha.1 so a fresh `pnpm install` pulls a
 * version whose peer/transitive deps actually resolve. This is also the
 * floor for the Phase 2.7 migration (meta #266).
 */
describe("@concavetrillion/pd-ui pin (meta #293)", () => {
  const pin = (pkg.dependencies as Record<string, string>)[
    "@concavetrillion/pd-ui"
  ];

  it("is declared as a dependency", () => {
    expect(pin).toBeDefined();
  });

  it("is not pinned to the broken 0.1.0-alpha metadata", () => {
    expect(pin).not.toBe("^0.1.0-alpha");
    expect(pin).not.toBe("0.1.0-alpha");
  });

  it("pins at least 0.1.0-alpha.1", () => {
    expect(pin).toMatch(/0\.1\.0-alpha\.\d+/);
  });
});
