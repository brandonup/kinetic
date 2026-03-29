#!/bin/bash
set -e
cd /Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api

git add app/api/routes/mcp.py app/main.py tests/test_mcp.py

git commit -m "feat: MCP context endpoint — auth, rate limit, scope routing, ACL, context assembly L1-L5 (KIN-321)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
