"""The repository's environment file, loaded once, before any setting is read.

Every module that reads a setting from the environment imports this first (``oxcart.config``,
``backend/app/settings.py``, the ``eval`` package), so a value written in the file is seen wherever it is
read, whatever was imported before. A variable already set in the real environment wins over the file: the
host sets real environment variables and has no file.

The file is the one at the repository root (see ``.env.example`` for its shape), or the one
``OXCART_ENV_FILE`` names (the tests use a made-up one). Without ``python-dotenv`` installed nothing is
loaded.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def env_file() -> Path:
    named = os.environ.get("OXCART_ENV_FILE", "").strip()
    return Path(named) if named else REPO_ROOT / ".env"


def load() -> bool:
    """Load the file into the environment, keeping any variable already set. True when a file was read."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # optional; any other error (a bad file) surfaces
        return False
    return load_dotenv(env_file(), override=False)


LOADED = load()
