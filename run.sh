#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# First run: uv creates .venv and installs dependencies automatically.
exec uv run audio2lrc "$@"