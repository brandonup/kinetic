"""
Deployment smoke test — automated checks (KIN-437).

Verifies production services are reachable and responding correctly.
Auth-dependent checks (profile, agent CRUD, conversation, KB) require
manual browser testing — see checklist printed at the end.

Usage:
    cd packages/api
    .venv/bin/python3 scripts/smoke_test.py
"""

import sys
import urllib.request
import urllib.error
import json
import ssl

VERCEL_URL = "https://kinetic-ashy-beta.vercel.app"
RAILWAY_URL = "https://kinetic-production-b568.up.railway.app"
MCP_URL = "https://iiapaogaoadtvjnryuls.supabase.co/functions/v1/kinetic-mcp"

# Skip SSL verification for basic connectivity checks
ctx = ssl.create_default_context()


def check(name: str, url: str, expected_status: int = 200, timeout: int = 15) -> bool:
    """Check if a URL is reachable and returns the expected status."""
    try:
        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        status = resp.getcode()
        if status == expected_status:
            print(f"  ✅ {name}: {status} OK", file=sys.stderr)
            return True
        else:
            print(f"  ❌ {name}: expected {expected_status}, got {status}", file=sys.stderr)
            return False
    except urllib.error.HTTPError as e:
        # Some endpoints return non-200 but are still reachable
        if e.code == expected_status:
            print(f"  ✅ {name}: {e.code} (expected)", file=sys.stderr)
            return True
        print(f"  ❌ {name}: HTTP {e.code}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  ❌ {name}: {e}", file=sys.stderr)
        return False


def check_json(name: str, url: str, timeout: int = 15) -> dict | None:
    """Fetch JSON from a URL."""
    try:
        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        data = json.loads(resp.read().decode())
        print(f"  ✅ {name}: OK — {json.dumps(data)[:100]}", file=sys.stderr)
        return data
    except Exception as e:
        print(f"  ❌ {name}: {e}", file=sys.stderr)
        return None


def main():
    print("\n=== KINETIC DEPLOYMENT SMOKE TEST ===\n", file=sys.stderr)
    passed = 0
    failed = 0

    # --- Vercel (Frontend) ---
    print("Frontend (Vercel):", file=sys.stderr)
    if check("App loads", VERCEL_URL):
        passed += 1
    else:
        failed += 1

    if check("Login page", f"{VERCEL_URL}/login"):
        passed += 1
    else:
        failed += 1

    # --- Railway (API) ---
    print("\nBackend (Railway):", file=sys.stderr)
    health = check_json("Health endpoint", f"{RAILWAY_URL}/health")
    if health:
        passed += 1
        env = health.get("environment", "unknown")
        if env == "production":
            print(f"  ✅ Environment: {env}", file=sys.stderr)
            passed += 1
        else:
            print(f"  ⚠️  Environment: {env} (expected 'production')", file=sys.stderr)
            failed += 1
    else:
        failed += 1

    if check("API docs", f"{RAILWAY_URL}/docs"):
        passed += 1
    else:
        failed += 1

    # --- MCP Edge Function ---
    print("\nMCP Server (Supabase Edge Function):", file=sys.stderr)
    # MCP endpoint returns 405 on GET (expects POST with JSON-RPC) — that's correct behavior
    if check("MCP endpoint reachable", MCP_URL, expected_status=405):
        passed += 1
    else:
        failed += 1

    # --- Summary ---
    total = passed + failed
    print(f"\n=== RESULTS: {passed}/{total} passed ===\n", file=sys.stderr)

    if failed > 0:
        print(f"❌ {failed} check(s) failed — investigate before proceeding.\n", file=sys.stderr)
    else:
        print("All automated checks passed.\n", file=sys.stderr)

    # --- Manual Checklist ---
    print("=== MANUAL BROWSER CHECKLIST ===", file=sys.stderr)
    print(f"Open: {VERCEL_URL}\n", file=sys.stderr)
    print("""\
  [ ] 1. AUTH: Sign in with Google OAuth → redirected back → authenticated
  [ ] 2. PROFILE: User profile page loads, can update settings
  [ ] 3. API KEY: Add OpenAI API key in settings → saves successfully
  [ ] 4. AGENT: Create agent with name + instructions → appears in list
  [ ] 5. CONVERSATION: Start chat with agent → send message → streamed response
  [ ] 6. KB: Upload document to agent KB → ingestion completes → shows in list
  [ ] 7. ACTIVE MEMORY: After conversation, check active memory entries created
  [ ] 8. CORS: Open browser DevTools (F12) → Console tab → no CORS errors
  [ ] 9. MCP: Already verified via Claude Code MCP connector (✅)
""", file=sys.stderr)


if __name__ == "__main__":
    main()
