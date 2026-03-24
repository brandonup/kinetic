/**
 * DocumentStatusBadge component tests — KIN-346
 *
 * Spec: PRD §7 (Knowledge Base & RAG)
 * Component: packages/web/components/DocumentStatusBadge.tsx
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import type { DocumentStatus } from "@/lib/types/models";

describe("DocumentStatusBadge", () => {
  const STATUSES: DocumentStatus[] = [
    "pending",
    "extracting",
    "chunking",
    "embedding",
    "completed",
    "failed",
  ];

  it.each(STATUSES)("renders %s status with correct label", (status) => {
    render(<DocumentStatusBadge status={status} />);
    const expected = status.charAt(0).toUpperCase() + status.slice(1);
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("renders failed badge with error info", () => {
    render(
      <DocumentStatusBadge
        status="failed"
        errorStage="chunking"
        errorMessage="Out of memory"
      />,
    );
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders completed badge without processing indicator", () => {
    const { container } = render(<DocumentStatusBadge status="completed" />);
    // No animated pulse dot for completed status
    const pulseDot = container.querySelector(".animate-pulse");
    expect(pulseDot).toBeNull();
  });

  it("renders processing statuses with animated indicator", () => {
    const { container } = render(<DocumentStatusBadge status="extracting" />);
    const pulseDot = container.querySelector(".animate-pulse");
    expect(pulseDot).not.toBeNull();
  });
});
