#!/bin/bash
# Pre-commit hook script to run pytest
# Load direnv environment
set -e

# Source direnv if available
if command -v direnv >/dev/null 2>&1; then
    eval "$(direnv export bash 2>/dev/null)" || true
fi

pytest tests/
