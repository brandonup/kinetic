# Code Review — KIN-371: Rework framework edit/add form fields

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Verdict:** APPROVED
**Critical:** 0 | **Important:** 0

---

## Files Reviewed

- `packages/web/components/FrameworkLibraryTab.tsx` (FrameworkForm component, lines 38–214)

---

## Verified Changes

Per ticket description and Dinesh's comment: form reworked to Name → Category → Description → When to apply → Principles → Steps. Confidence field removed from form, table, and request types.

### Field order (confirmed)

```
Name *
Category
Description
When to apply *
Principles (* in add mode)
Steps
```

Matches the ticket requirement. Confidence is absent from `FrameworkForm`.

### Principles field in edit mode

Previously `Principles` was not shown in the edit form. Now it is shown in both add and edit mode (line 144: `<label>Principles {!initial && "*"}</label>` — asterisk only in add mode since it's optional in edit). Correct — users can now edit principles via the form.

### Steps field added

New field. Multi-value array input matching the When to apply pattern. `steps.filter(Boolean)` in the POST body; undefined (omitted) when empty in add mode (line 79: `steps: steps.filter(Boolean).length > 0 ? steps.filter(Boolean) : undefined`). Correct — steps is optional per the framework schema.

### Description field added

New textarea field. `description || undefined` in both add and edit bodies — empty string becomes undefined, not sent as null. Consistent with the existing `category` handling.

### Confidence removal

Confirmed: no `confidence` field in `FrameworkForm`, no `confidence` in `CreateFrameworkRequest` or `UpdateFrameworkRequest` types (from Dinesh's comment: "Confidence removed from form + table + request types"). The backend framework schema includes `confidence` (enum: high/medium) but it's origin-set (extraction pipeline), not user-editable. Removing it from the UI is correct per spec.

### No-op PATCH guard (line 366–371)

```typescript
if (editTarget && Object.keys(body).length === 0) {
  setShowForm(false);
  setEditTarget(null);
  return;
}
```

Prevents a spurious empty PATCH when a user opens the edit form and saves without changing anything. This is correct and tested (existing test: "does not fire PATCH when no fields changed").

### `whenToApplyChanged` hint (lines 53–55, 139–141)

Shows informational text "Trigger embeddings will be updated in the background." when `when_to_apply` has changed in edit mode. Correct UX indicator — embeddings are regenerated asynchronously on the backend when triggers change.

---

## Test Impact

KIN-377 (Bachman) flags a pre-existing test failure: `successful create appends new framework row to table`. This test is in the same file as KIN-371's form changes. The `FrameworkLibraryTab.test.tsx` file was identified as having a pre-existing failure (noted in KIN-370 R3). The root cause is investigated under KIN-377 — it is not introduced by KIN-371. The relevant test assertions work against the modal button, name input, and trigger input — none of which changed structurally. The new Principles and Steps fields initialize with `[""]` (empty), do not affect the modal render, and do not affect the save button disabled state (which only checks `!name.trim()`).

---

## Summary

Form restructuring is clean. All six fields present in the correct order, Confidence correctly removed, Principles available in edit mode, Steps added, empty-field filtering correct. LGTM.

— Gilfoyle
