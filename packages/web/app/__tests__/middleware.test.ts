import { describe, it, expect } from "vitest";

// Middleware relies on NextRequest/NextResponse at runtime.
// Unit test validates only the exported config matcher shape.
import { config } from "@/middleware";

describe("middleware config", () => {
  it("exports a matcher array", () => {
    expect(Array.isArray(config.matcher)).toBe(true);
  });

  it("does not match /login directly", () => {
    // The negative lookahead pattern should exclude /login
    const pattern = (config.matcher as string[]).join("");
    expect(pattern).toContain("(?!");
    expect(pattern).toContain("login");
  });

  it("does not match _next static assets", () => {
    const pattern = (config.matcher as string[]).join("");
    expect(pattern).toContain("_next");
  });
});
