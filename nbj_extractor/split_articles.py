"""
Split JSONL article files into individual JSON files for KB upload.

Reads both nate_b_jones_content_sample.jsonl and nate_b_jones_content_remaining.jsonl,
creates one JSON file per article in articles/ with metadata preserved for future
recency scoring.

Usage:
    cd /Users/brandonupchuch/son_of_anton/projects/kinetic/nbj_extractor
    python split_articles.py
"""

import json
import os
import re
import sys

INPUT_FILES = [
    "nate_b_jones_content_sample.jsonl",
    "nate_b_jones_content_remaining.jsonl",
]
OUTPUT_DIR = "articles"


def sanitize_filename(title: str, max_len: int = 80) -> str:
    """Convert article title to a safe filename."""
    # Lowercase, replace non-alphanumeric with hyphens
    name = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    # Collapse multiple hyphens
    name = re.sub(r"-{2,}", "-", name)
    # Truncate
    if len(name) > max_len:
        name = name[:max_len].rstrip("-")
    return name


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)

    total = 0
    skipped = 0
    seen_slugs: set[str] = set()

    for input_file in INPUT_FILES:
        input_path = os.path.join(script_dir, input_file)
        if not os.path.exists(input_path):
            print(f"WARNING: {input_file} not found, skipping", file=sys.stderr)
            continue

        print(f"Processing {input_file}...", file=sys.stderr)

        with open(input_path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    article = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"  Line {line_num}: JSON parse error: {e}", file=sys.stderr)
                    skipped += 1
                    continue

                title = article.get("title", "").strip()
                content = article.get("content", "").strip()

                if not title or not content:
                    print(f"  Line {line_num}: Missing title or content, skipping", file=sys.stderr)
                    skipped += 1
                    continue

                # Build output structure
                output = {
                    "title": title,
                    "subtitle": article.get("subtitle", ""),
                    "url": article.get("url", ""),
                    "date": article.get("date", ""),
                    "slug": article.get("slug", ""),
                    "type": article.get("type", ""),
                    "word_count": article.get("word_count", 0),
                    "content": content,
                }

                # Generate unique filename
                slug = article.get("slug") or sanitize_filename(title)
                if slug in seen_slugs:
                    slug = f"{slug}-{article.get('id', line_num)}"
                seen_slugs.add(slug)

                output_path = os.path.join(output_dir, f"{slug}.json")
                with open(output_path, "w") as out:
                    json.dump(output, out, indent=2, ensure_ascii=False)

                total += 1

    print(f"\nDone. {total} articles written to {OUTPUT_DIR}/", file=sys.stderr)
    if skipped:
        print(f"Skipped {skipped} entries (missing data or parse errors)", file=sys.stderr)


if __name__ == "__main__":
    main()
