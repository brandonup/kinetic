#!/bin/bash
set -euo pipefail

# Only run in remote Claude Code sessions
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo "Kinetic session-start hook running..."

# Backend (FastAPI / Python) — install when present
if [ -f "$CLAUDE_PROJECT_DIR/backend/requirements.txt" ]; then
  echo "Installing Python dependencies..."
  pip install -r "$CLAUDE_PROJECT_DIR/backend/requirements.txt" --quiet
fi

if [ -f "$CLAUDE_PROJECT_DIR/backend/pyproject.toml" ]; then
  echo "Installing Python project (pyproject.toml)..."
  pip install -e "$CLAUDE_PROJECT_DIR/backend" --quiet
fi

# Frontend (Next.js 14) — install when present
if [ -f "$CLAUDE_PROJECT_DIR/frontend/package.json" ]; then
  echo "Installing frontend dependencies..."
  cd "$CLAUDE_PROJECT_DIR/frontend"
  npm install
fi

echo "Session-start hook complete."
