#!/bin/bash
set -euo pipefail

# Only run in remote Claude Code environment
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# This is a documentation-only repository with no code dependencies.
# No installation steps are required.
echo "Session start hook: no dependencies to install (docs-only repo)."
