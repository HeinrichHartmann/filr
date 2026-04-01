#!/usr/bin/env bash
# Pre-commit hook script to run pytest
# Requires direnv to be set up with .envrc
set -e

eval "$(direnv export bash)"
pytest tests/
