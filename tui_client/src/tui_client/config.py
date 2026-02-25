"""User configuration for the TUI client.

Config file: ~/.config/golf-tui.conf

Example contents:
    server = golfcards.club
    tls = true
"""

from __future__ import annotations

import os
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("GOLF_TUI_CONFIG", "~/.config/golf-tui.conf")).expanduser()

DEFAULTS = {
    "server": "golfcards.club",
    "tls": "true",
}


def load_config() -> dict[str, str]:
    """Load config from file, falling back to defaults."""
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                cfg[key.strip().lower()] = value.strip()
    return cfg


def save_config(cfg: dict[str, str]) -> None:
    """Write config to file."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k} = {v}" for k, v in sorted(cfg.items())]
    CONFIG_PATH.write_text("\n".join(lines) + "\n")
