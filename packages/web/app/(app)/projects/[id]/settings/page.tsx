"use client";

/**
 * Project Settings Page — KIN-383
 *
 * Placeholder: the existing project edit form will be moved here.
 * For now, redirects to the project chat page.
 */

import { useParams } from "next/navigation";

export default function ProjectSettingsPage() {
  const params = useParams();
  const projectId = params.id as string;

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold text-foreground mb-4">
        Project Settings
      </h1>
      <p className="text-sm text-muted-foreground">
        Project settings page — to be populated with the existing project edit form.
      </p>
    </div>
  );
}
