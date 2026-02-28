"""Test package bootstrap for local dependency availability."""

from src.python.dependency_bootstrap import ensure_dependencies

ensure_dependencies((("numpy", "numpy"),))
