"""Shared path utilities for the extract-plano skill."""

from pathlib import Path

_MARKERS = ("config.json", "HEARTBEAT.md")


def find_pipa_root() -> Path:
    """Walk up from this file until finding PIPA root (contains config.json + HEARTBEAT.md)."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if all((candidate / m).exists() for m in _MARKERS):
            return candidate
    raise RuntimeError(
        f"Cannot locate PIPA root from {here}. "
        "Expected config.json and HEARTBEAT.md in an ancestor directory."
    )
