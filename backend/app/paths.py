import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    from app import config  # noqa: F401  (loads .env before PARTSWAP_DATA_DIR is read)

    configured = Path(os.environ.get("PARTSWAP_DATA_DIR") or "data")
    if not configured.is_absolute():
        configured = repo_root() / configured
    return configured
