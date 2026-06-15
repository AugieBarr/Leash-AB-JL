#!/bin/bash
# SessionStart hook for Claude Code on the web.
#
# Installs the project's dev environment (runtime + test deps from pyproject.toml)
# so `pytest` is green and the agent can run the governance suite without manual
# setup. Synchronous on purpose: the container caches after first run, and we'd
# rather guarantee deps exist than race the agent loop.
set -euo pipefail

# Claude Code on the web only — local dev manages its own environment.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$PROJECT_DIR"

# uv is the project's package manager (see README quickstart). Ensure it exists,
# preferring pip (always present) and falling back to the official installer.
if ! command -v uv >/dev/null 2>&1; then
  python -m pip install --user uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# Sync the full dev environment into .venv (idempotent; --extra dev adds pytest +
# pytest-asyncio, which the async governance tests require).
uv sync --extra dev

# Make the synced venv the default for the session so `pytest` and `python`
# resolve the installed deps directly — no explicit `uv run` needed.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export PATH=\"$HOME/.local/bin:$PROJECT_DIR/.venv/bin:\$PATH\""
    echo "export VIRTUAL_ENV=\"$PROJECT_DIR/.venv\""
  } >> "$CLAUDE_ENV_FILE"
fi

echo "[session-start] leash dev env ready ($(uv run python -c 'import cryptography, pydantic, httpx, pytest; print("governance deps ok")'))"
