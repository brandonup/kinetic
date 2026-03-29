#!/usr/bin/env python3
"""
Substack Scraper for RAG Ingestion
====================================
Scrapes all posts from a Substack newsletter (including paid content)
and saves them as JSONL — one JSON object per post.

SETUP:
1. Get your session cookie from Chrome:
   - Open Chrome → go to natesnewsletter.substack.com
   - Open DevTools (F12) → Application tab → Cookies
   - Find the cookie named: substack.sid
   - Copy its value

2. Paste it into SESSION_COOKIE below (or pass via --cookie flag)

3. Run: python substack_scraper.py

OUTPUT:
  substack_posts.jsonl — one JSON object per line, each with:
    {
      "id": "post-id",
      "title": "Post title",
      "subtitle": "Post subtitle",
      "date": "2026-03-19T...",
      "url": "https://...",
      "slug": "post-slug",
      "type": "newsletter",
      "word_count": 1234,
      "content": "Full plain text content..."
    }
"""

import requests
import json
import time
import argparse
import sys
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

try:
    from bs4 import BeautifulSoup
    import html2text
except ImportError:
    print("Missing dependencies. Run: pip install requests beautifulsoup4 html2text")
    sys.exit(1)


# ── CONFIG ─────────────────────────────────────────────────────────────────────
SUBSTACK_URL = "https://natesnewsletter.substack.com"
SESSION_COOKIE = "s%3ALCzGbFiQ3rjIR8uRUAibDbm_yqCl0wlG.bs5MtMlhLnVwuW5kUKbcFN89KX8fvY2mWEEuWGU6m%2BA"
OUTPUT_FILE = "substack_posts.jsonl"
REQUEST_DELAY = 0.75  # seconds between requests (be respectful)
# ───────────────────────────────────────────────────────────────────────────────


def make_session(cookie: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    if cookie:
        decoded_cookie = unquote(cookie)
        session.headers.update({"Cookie": f"substack.sid={decoded_cookie}"})
    return session


def html_to_text(html_content: str) -> str:
    """Convert HTML to clean plain text suitable for RAG."""
    if not html_content:
        return ""

    h = html2text.HTML2Text()
    h.ignore_links = False      # keep links as [text](url) — useful for citations
    h.ignore_images = True
    h.ignore_emphasis = False
    h.body_width = 0            # don't wrap lines
    h.protect_links = True

    text = h.handle(html_content)
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    # Remove trailing Substack CDN image links e.g. [](https://substackcdn.com/...)
    text = re.sub(r'\[]\(https://substackcdn\.com[^)]*\)\s*$', '', text).strip()
    return text


def fetch_post_list(session: requests.Session) -> list[dict]:
    """Fetch all post metadata via the Substack API."""
    posts = []
    offset = 0
    limit = 25
    total_fetched = 0

    print(f"Fetching post list from {SUBSTACK_URL}...")

    while True:
        url = f"{SUBSTACK_URL}/api/v1/posts"
        params = {"limit": limit, "offset": offset}

        try:
            resp = session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            batch = resp.json()
        except requests.HTTPError as e:
            print(f"  HTTP error fetching post list: {e}")
            break
        except Exception as e:
            print(f"  Error fetching post list: {e}")
            break

        if not batch:
            break

        posts.extend(batch)
        total_fetched += len(batch)
        print(f"  Fetched {total_fetched} posts so far...")

        if len(batch) < limit:
            break  # last page

        offset += limit
        time.sleep(REQUEST_DELAY)

    print(f"Found {len(posts)} total posts.\n")
    return posts


def fetch_post_content(session: requests.Session, slug: str) -> dict:
    """Fetch full content by loading the actual post page (not the API).

    The API always truncates paid content at the paywall. The rendered
    web page includes the full body when the session cookie is valid.
    """
    # First try the rendered page to get full paid content
    page_url = f"{SUBSTACK_URL}/p/{slug}"
    try:
        page_resp = session.get(page_url, headers={"Accept": "text/html"}, timeout=15)
        page_resp.raise_for_status()
        soup = BeautifulSoup(page_resp.text, "html.parser")

        # Substack renders post body inside these selectors
        body_el = (
            soup.select_one("div.available-content")
            or soup.select_one("div.body.markup")
            or soup.select_one("div.post-content")
            or soup.select_one("article .body")
        )

        if body_el:
            # Remove the paywall CTA if present
            for cta in body_el.select(".paywall, .subscription-widget-wrap, .paywall-jump"):
                cta.decompose()

            body_html = str(body_el)
            # Also grab the API response for metadata
            api_url = f"{SUBSTACK_URL}/api/v1/posts/{slug}"
            try:
                api_resp = session.get(api_url, timeout=15)
                api_data = api_resp.json() if api_resp.ok else {}
            except Exception:
                api_data = {}

            api_data["body_html"] = body_html
            return api_data

    except Exception as e:
        print(f"    Warning: Page fetch failed for {slug}: {e}")

    # Fallback to API-only (will be truncated for paid posts)
    api_url = f"{SUBSTACK_URL}/api/v1/posts/{slug}"
    try:
        resp = session.get(api_url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        print(f"    Warning: HTTP {resp.status_code} for {slug}")
        return {}
    except Exception as e:
        print(f"    Warning: Error fetching {slug}: {e}")
        return {}


def extract_sections(body_html: str) -> list[dict]:
    """Parse body HTML into sections by heading (h2/h3)."""
    if not body_html:
        return []

    soup = BeautifulSoup(body_html, "html.parser")
    sections = []
    current_heading = None
    current_blocks = []

    seen_texts = set()
    for el in soup.find_all(["h2", "h3", "p", "ul", "ol", "blockquote", "pre"]):
        if el.name in ("h2", "h3"):
            # Save previous section if there was one
            if current_heading is not None:
                sections.append({
                    "heading": current_heading,
                    "content": "\n\n".join(current_blocks).strip(),
                })
            current_heading = el.get_text(strip=True)
            current_blocks = []
            seen_texts = set()
        else:
            # Skip elements nested inside a parent we already captured
            if el.name == "p" and el.parent and el.parent.name in ("li", "ul", "ol", "blockquote"):
                continue
            text = el.get_text(separator=" ", strip=True)
            if text and text not in seen_texts:
                current_blocks.append(text)
                seen_texts.add(text)

    # Save last section
    if current_heading is not None:
        sections.append({
            "heading": current_heading,
            "content": "\n\n".join(current_blocks).strip(),
        })

    # Drop sections with empty headings
    sections = [s for s in sections if s["heading"].strip()]

    return sections


def fetch_comments(session: requests.Session, post_id: str) -> list[dict]:
    """Fetch comments for a post from the Substack API."""
    url = f"{SUBSTACK_URL}/api/v1/post/{post_id}/comments"
    try:
        resp = session.get(url, params={"all_comments": "true", "sort": "top"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    Warning: Could not fetch comments for post {post_id}: {e}")
        return []

    raw_comments = data.get("comments", [])
    result = []
    for c in raw_comments:
        # Build replies list
        replies = []
        for r in c.get("children", []):
            replies.append({
                "id": str(r.get("id", "")),
                "author": (r.get("name") or r.get("author_name") or ""),
                "date": r.get("date") or "",
                "body": r.get("body") or "",
                "replies": [],
            })
        result.append({
            "id": str(c.get("id", "")),
            "author": (c.get("name") or c.get("author_name") or ""),
            "date": c.get("date") or "",
            "body": c.get("body") or "",
            "replies": replies,
        })

    return result


def process_post(post_meta: dict, post_detail: dict, comments: list[dict]) -> dict:
    """Build a clean, RAG-ready dict from raw API data."""

    # Get HTML content — try body_html first, fall back to truncated_body_text
    body_html = post_detail.get("body_html", "") or post_meta.get("body_html", "")
    body_text = post_detail.get("truncated_body_text", "") or post_meta.get("truncated_body_text", "")

    if body_html:
        full_text = html_to_text(body_html)
        sections = extract_sections(body_html)

        # content = intro only (before first heading); sections carry the rest
        if sections:
            first_heading = sections[0]["heading"]
            # Find where the first heading appears in the plain text
            idx = full_text.find(first_heading)
            if idx > 0:
                content = full_text[:idx].strip()
                # Remove trailing markdown artifacts (##, **, etc.)
                content = re.sub(r'[\s#*]+$', '', content).strip()
            else:
                content = full_text
        else:
            content = full_text
    else:
        content = body_text or ""
        sections = []

    # word_count covers the entire post (intro + all sections)
    total_text = content + " " + " ".join(s["content"] for s in sections)
    word_count = len(total_text.split()) if total_text.strip() else 0

    return {
        "id": str(post_meta.get("id", "")),
        "title": post_meta.get("title", "").strip(),
        "subtitle": (post_meta.get("subtitle") or "").strip(),
        "date": post_meta.get("post_date", ""),
        "url": post_meta.get("canonical_url", ""),
        "slug": post_meta.get("slug", ""),
        "type": post_meta.get("type", "newsletter"),
        "word_count": word_count,
        "content": content,
        "sections": sections,
        "comments": comments,
    }


def scrape(cookie: str, output_path: Path, limit: int = 0):
    session = make_session(cookie)

    if not cookie:
        print("⚠  No session cookie provided — paid posts will be truncated.")
        print("   See the top of this script for instructions.\n")

    # 1. Get all post metadata
    post_list = fetch_post_list(session)

    if not post_list:
        print("No posts found. Check your cookie or the Substack URL.")
        return

    # 2. Fetch full content for each post
    if limit:
        post_list = post_list[:limit]

    results = []
    for i, post_meta in enumerate(post_list, 1):
        slug = post_meta.get("slug", "")
        title = post_meta.get("title", slug)
        is_paid = post_meta.get("audience", "") == "only_paid"

        label = "[PAID]" if is_paid else "[FREE]"
        print(f"  [{i:03d}/{len(post_list)}] {label} {title[:70]}")

        post_detail = fetch_post_content(session, slug)
        has_body = bool(post_detail.get("body_html"))
        print(f"         body_html present: {has_body} | audience: {post_detail.get('audience', 'unknown')}")
        post_id = str(post_meta.get("id", ""))
        comments = fetch_comments(session, post_id)
        processed = process_post(post_meta, post_detail, comments)
        results.append(processed)

        time.sleep(REQUEST_DELAY)

    # 3. Write JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for record in results:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Summary
    total_words = sum(r["word_count"] for r in results)
    paid_count = sum(1 for r in results if r.get("word_count", 0) > 200)
    empty_count = sum(1 for r in results if r["word_count"] == 0)

    print(f"\n{'─'*50}")
    print(f"Done! Saved {len(results)} posts → {output_path}")
    print(f"Total words: {total_words:,}")
    if empty_count:
        print(f"Posts with no content (likely need cookie): {empty_count}")
    print(f"{'─'*50}")


def main():
    parser = argparse.ArgumentParser(description="Scrape Nate's Substack for RAG ingestion")
    parser.add_argument("--cookie", type=str, default=SESSION_COOKIE,
                        help="Your substack.sid session cookie value")
    parser.add_argument("--output", type=str, default=OUTPUT_FILE,
                        help="Output JSONL file path")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only process this many posts (0 = all)")
    args = parser.parse_args()

    scrape(
        cookie=args.cookie,
        output_path=Path(args.output),
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
