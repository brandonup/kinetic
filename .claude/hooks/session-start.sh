#!/bin/bash
set -euo pipefail

# Only run in remote (Claude Code on the web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo "=== Kinetic session-start hook ==="

# Backend: install Python dependencies if present
if [ -f "${CLAUDE_PROJECT_DIR}/backend/requirements.txt" ]; then
  echo "Installing Python dependencies..."
  pip install -r "${CLAUDE_PROJECT_DIR}/backend/requirements.txt"
elif [ -f "${CLAUDE_PROJECT_DIR}/backend/pyproject.toml" ]; then
  echo "Installing Python dependencies (pyproject.toml)..."
  pip install -e "${CLAUDE_PROJECT_DIR}/backend"
fi

# Frontend: install Node.js dependencies if present
if [ -f "${CLAUDE_PROJECT_DIR}/frontend/package.json" ]; then
  echo "Installing frontend Node.js dependencies..."
  cd "${CLAUDE_PROJECT_DIR}/frontend"
  npm install
elif [ -f "${CLAUDE_PROJECT_DIR}/package.json" ]; then
  echo "Installing Node.js dependencies..."
  cd "${CLAUDE_PROJECT_DIR}"
  npm install
fi

echo "=== Session-start hook complete ==="
