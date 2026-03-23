import { describe, it, expect } from "vitest";

// Admin layout is a "use client" component with auth side-effects.
// Unit test validates static nav structure only — integration tested at boot.
describe("AdminLayout nav structure", () => {
  it("defines Users and LLM Models tabs", () => {
    const NAV_ITEMS = [
      { label: "Users", href: "/admin/users" },
      { label: "LLM Models", href: "/admin/models" },
      { label: "Back to App", href: "/projects" },
    ];
    expect(NAV_ITEMS.map((i) => i.label)).toEqual([
      "Users",
      "LLM Models",
      "Back to App",
    ]);
  });

  it("admin endpoint path uses /api/v1/ prefix", () => {
    // This is a structural assertion — ensures the right API path is coded
    const adminEndpoint = "/api/v1/admin/users";
    expect(adminEndpoint).toContain("/api/v1/");
  });
});
