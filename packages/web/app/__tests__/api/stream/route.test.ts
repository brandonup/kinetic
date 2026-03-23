import { describe, it, expect } from "vitest";

// SSE route uses Edge runtime — unit test validates exports only.
// Full streaming behavior is integration-tested against a live backend.
describe("SSE proxy route", () => {
  it("exports a GET handler", async () => {
    const mod = await import("@/app/api/stream/route");
    expect(typeof mod.GET).toBe("function");
  });

  it("exports Edge runtime config", async () => {
    const mod = await import("@/app/api/stream/route");
    expect(mod.runtime).toBe("edge");
  });

  it("exports dynamic force-dynamic config", async () => {
    const mod = await import("@/app/api/stream/route");
    expect(mod.dynamic).toBe("force-dynamic");
  });
});
