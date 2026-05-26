#!/usr/bin/env python3
"""
Refresh the Substack session cookie on the Nate B. Jones scrape source.

Local-only MVP. The production poller scrapes natesnewsletter.substack.com
daily; full paywalled-post content needs a valid `substack.sid` session
cookie, and Substack session cookies expire periodically.

This script reads a fresh cookie from your local Chrome — where you are
already logged into Substack — and PATCHes it onto the production scrape
source through the Kinetic API. The API re-encrypts the credential
(AES-256-GCM) server-side; the encryption master key never leaves prod.

Run this:
  - once during initial setup, to give the source a cookie, and
  - again whenever paywalled posts stop coming through, or the source
    auto-deactivates after repeated 403s (an expired cookie). The PATCH
    also re-activates the source, so this doubles as the recovery step.

Usage (from the nbj_extractor directory):

    cd /Users/brandonupchuch/son_of_anton/projects/kinetic/nbj_extractor
    .venv/bin/pip install browser_cookie3        # one-time, into this venv

    # Create / update the gitignored .env file next to this script with:
    #   SCRAPE_SOURCE_ID=<scrape source id>
    #   KINETIC_USER_JWT=<fresh prod access token from the Kinetic web app>

    python refresh_substack_cookie.py --dry-run   # read cookie, show it, no PATCH
    python refresh_substack_cookie.py             # read cookie + PATCH to prod

If browser_cookie3 cannot decrypt the Chrome cookie store on your machine,
fall back to a Playwright persistent-context approach (see the feature plan).

Requirements: `browser_cookie3`, `requests`.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import requests

# --- Constants --------------------------------------------------------------

ENV_FILE_NAME = ".env"

KINETIC_BASE_URL_DEFAULT = "https://kinetic-production-b568.up.railway.app"  # prod
COOKIE_NAME = "substack.sid"
COOKIE_DOMAIN = "substack.com"
HTTP_TIMEOUT_S = 30

logger = logging.getLogger("refresh_substack_cookie")


# --- Environment ------------------------------------------------------------

def load_env_file(path: Path) -> None:
    """Merge KEY=VALUE lines from a .env file into os.environ.

    Existing environment variables take precedence (setdefault), so an
    explicit `export` always wins over the file.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# --- Cookie -----------------------------------------------------------------

def read_substack_cookie(cookie_file: Optional[str]) -> str:
    """Read the `substack.sid` cookie value from the local Chrome profile.

    Raises RuntimeError with actionable guidance on failure.
    """
    try:
        import browser_cookie3
    except ImportError as exc:
        raise RuntimeError(
            "browser_cookie3 is not installed. Run: .venv/bin/pip install browser_cookie3"
        ) from exc

    try:
        jar = browser_cookie3.chrome(
            domain_name=COOKIE_DOMAIN,
            cookie_file=cookie_file or None,
        )
    except Exception as exc:  # browser_cookie3 raises bare exceptions
        raise RuntimeError(
            f"Could not read Chrome's cookie store: {exc}. "
            "Make sure Chrome is installed and you have logged into Substack in it."
        ) from exc

    matches = [c for c in jar if c.name == COOKIE_NAME]
    if not matches:
        raise RuntimeError(
            f"No '{COOKIE_NAME}' cookie found for {COOKIE_DOMAIN} in Chrome. "
            "Log into Substack in Chrome, then re-run."
        )
    if len(matches) > 1:
        logger.warning(
            "Found %d '%s' cookies — using the first (domain=%s).",
            len(matches), COOKIE_NAME, matches[0].domain,
        )
    value = matches[0].value or ""
    if not value:
        raise RuntimeError(f"'{COOKIE_NAME}' cookie is present but empty.")
    return value


# --- Kinetic API ------------------------------------------------------------

def patch_credential(
    base_url: str, jwt: str, source_id: str, cookie_value: str
) -> requests.Response:
    """PATCH the scrape source: update the credential and re-activate it."""
    endpoint = f"{base_url.rstrip('/')}/api/v1/scrape-sources/{source_id}"
    return requests.patch(
        endpoint,
        headers={
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
        },
        json={"credential": cookie_value, "is_active": True},
        timeout=HTTP_TIMEOUT_S,
    )


# --- CLI --------------------------------------------------------------------

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh the Substack session cookie on the Nate scrape source.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read the cookie and show a masked preview, but do not PATCH.",
    )
    parser.add_argument(
        "--base-url",
        default=KINETIC_BASE_URL_DEFAULT,
        help=f"Kinetic API base URL (default: prod, {KINETIC_BASE_URL_DEFAULT}).",
    )
    parser.add_argument(
        "--cookie-file",
        default=None,
        help="Path to a specific Chrome 'Cookies' SQLite file (default: auto-detect).",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging.")
    return parser.parse_args(argv)


def _mask(value: str) -> str:
    """Mask a secret for logging — show length + a short prefix only."""
    if len(value) <= 8:
        return f"<{len(value)} chars>"
    return f"{value[:6]}…<{len(value)} chars total>"


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    script_dir = Path(__file__).resolve().parent
    load_env_file(script_dir / ENV_FILE_NAME)

    scrape_source_id = os.environ.get("SCRAPE_SOURCE_ID", "").strip()
    jwt = os.environ.get("KINETIC_USER_JWT", "").strip()
    # Tolerate a pasted "Bearer <token>" value.
    if jwt[:7].lower() == "bearer ":
        jwt = jwt[7:].strip()

    if not scrape_source_id:
        logger.error("Missing SCRAPE_SOURCE_ID (set it in .env or the environment).")
        return 2
    if not args.dry_run and not jwt:
        logger.error(
            "Missing KINETIC_USER_JWT. Copy a fresh access token from the "
            "Kinetic web app session and set it in .env."
        )
        return 2

    # --- Read cookie -------------------------------------------------------
    try:
        cookie_value = read_substack_cookie(args.cookie_file)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1
    logger.info("Read %s cookie: %s", COOKIE_NAME, _mask(cookie_value))

    if args.dry_run:
        print()
        print("=== Cookie refresh dry run ===")
        print(f"Scrape source:  {scrape_source_id}")
        print(f"{COOKIE_NAME}:   {_mask(cookie_value)}")
        print("\nNo PATCH performed. Re-run without --dry-run to push to prod.")
        return 0

    # --- PATCH -------------------------------------------------------------
    logger.info("Patching scrape source %s ...", scrape_source_id)
    resp = patch_credential(args.base_url, jwt, scrape_source_id, cookie_value)

    if resp.status_code == 200:
        data = resp.json()
        print()
        print("=== Cookie refreshed ===")
        print(f"Scrape source:  {scrape_source_id}")
        print(f"is_active:      {data.get('is_active')}")
        print(f"updated_at:     {data.get('updated_at')}")
        print(f"last_error:     {data.get('last_error')}")
        print("\nThe production poller will use the new cookie on its next run.")
        return 0

    if resp.status_code == 401:
        logger.error(
            "HTTP 401 — KINETIC_USER_JWT is expired or invalid. "
            "Grab a fresh access token from the Kinetic web app and update .env."
        )
    elif resp.status_code == 404:
        logger.error(
            "HTTP 404 — scrape source not found, or not owned by this user. "
            "Check SCRAPE_SOURCE_ID."
        )
    else:
        logger.error("HTTP %d: %s", resp.status_code, resp.text[:300])
    return 1


if __name__ == "__main__":
    sys.exit(main())
