#!/usr/bin/env python3
"""
Remove related_frameworks references that point to frameworks not in the curated set.
"""
import json
import re
from pathlib import Path

ENRICHED = Path(__file__).parent / "frameworks_enriched.json"

def name_to_slug(name: str) -> str:
    """Convert framework name to slug format used in related_frameworks."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug

def main():
    data = json.loads(ENRICHED.read_text())
    frameworks = data["frameworks"]

    # Build set of valid slugs from the 184 curated frameworks
    valid_slugs = {name_to_slug(f["name"]) for f in frameworks}
    print(f"Valid framework slugs: {len(valid_slugs)}")

    total_removed = 0
    total_kept = 0

    for f in frameworks:
        original = f.get("related_frameworks", [])
        if not original:
            continue

        cleaned = [slug for slug in original if slug in valid_slugs]
        removed = [slug for slug in original if slug not in valid_slugs]

        if removed:
            print(f"\n  [{f['name']}]")
            for slug in removed:
                print(f"    - REMOVED: {slug}")
            total_removed += len(removed)

        total_kept += len(cleaned)
        f["related_frameworks"] = cleaned

    print(f"\n{'='*60}")
    print(f"Total removed: {total_removed}")
    print(f"Total kept:    {total_kept}")

    ENRICHED.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Saved: {ENRICHED}")

if __name__ == "__main__":
    main()
