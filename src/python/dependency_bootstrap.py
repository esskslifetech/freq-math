"""Helpers for ensuring runtime dependencies are available."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Iterable


def _is_installed(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _add_local_venv_site_packages() -> None:
    """Attach bundled local venv site-packages (if present) to sys.path."""
    project_root = Path(__file__).resolve().parents[2]
    venv_lib = project_root / "venv" / "lib"
    if not venv_lib.exists():
        return

    for version_dir in sorted(venv_lib.glob("python*")):
        site_packages = version_dir / "site-packages"
        if site_packages.exists():
            site_path = str(site_packages)
            if site_path not in sys.path:
                sys.path.insert(0, site_path)


def ensure_dependencies(dependencies: Iterable[tuple[str, str]]) -> None:
    """
    Ensure required Python dependencies are installed.

    Resolution order:
    1. Already importable in active environment.
    2. Bundled ./venv site-packages (if available in repo).
    3. Pip install using active interpreter.

    Args:
        dependencies: (import_name, pip_name) pairs.
    """
    missing = [pip_name for module_name, pip_name in dependencies if not _is_installed(module_name)]
    if not missing:
        return

    _add_local_venv_site_packages()
    missing = [pip_name for module_name, pip_name in dependencies if not _is_installed(module_name)]
    if not missing:
        return

    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
    except Exception as exc:
        missing_text = ", ".join(missing)
        raise RuntimeError(
            f"Missing required dependencies ({missing_text}) and automatic installation failed. "
            f"Install them manually with: {sys.executable} -m pip install -r requirements.txt"
        ) from exc
