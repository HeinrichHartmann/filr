#!/usr/bin/env bash
# Pre-commit hook script to run pytest
set -e

uv run pytest tests/
