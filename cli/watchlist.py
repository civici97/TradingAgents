"""Watchlist persistence for TradingAgents CLI.

Stores a list of frequently-analysed tickers in
``~/.tradingagents/watchlist.json`` so users can pick them quickly
on subsequent runs instead of retyping the code every time.
"""

from __future__ import annotations

import json
import datetime
from pathlib import Path
from typing import List, Optional

_TRADINGAGENTS_HOME = Path.home() / ".tradingagents"
_WATCHLIST_FILE = _TRADINGAGENTS_HOME / "watchlist.json"


# ── data helpers ────────────────────────────────────────────────────────────

def _ensure_file() -> Path:
    """Create parent dirs & file if absent; return the path."""
    _WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _WATCHLIST_FILE.exists():
        _WATCHLIST_FILE.write_text("[]", encoding="utf-8")
    return _WATCHLIST_FILE


def _load() -> List[dict]:
    path = _ensure_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: List[dict]) -> None:
    path = _ensure_file()
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


# ── public API ──────────────────────────────────────────────────────────────

def get_watchlist() -> List[dict]:
    """Return the current watchlist.

    Each entry is a dict: ``{"ticker": "300750.SZ", "name": "宁德时代", "added_at": "2026-05-21"}``.
    """
    return _load()


def add_to_watchlist(ticker: str, name: str = "") -> bool:
    """Add *ticker* to the watchlist.  Returns True if newly added."""
    entries = _load()
    ticker = ticker.strip().upper()
    for e in entries:
        if e.get("ticker", "").upper() == ticker:
            # already present – update name if provided
            if name and not e.get("name"):
                e["name"] = name
                _save(entries)
            return False
    entries.append({
        "ticker": ticker,
        "name": name,
        "added_at": datetime.date.today().isoformat(),
    })
    _save(entries)
    return True


def remove_from_watchlist(ticker: str) -> bool:
    """Remove *ticker* from the watchlist.  Returns True if found & removed."""
    entries = _load()
    ticker = ticker.strip().upper()
    before = len(entries)
    entries = [e for e in entries if e.get("ticker", "").upper() != ticker]
    if len(entries) < before:
        _save(entries)
        return True
    return False


def watchlist_display_label(entry: dict) -> str:
    """Format a watchlist entry for display: ``300750.SZ  宁德时代``."""
    name = entry.get("name", "")
    label = entry["ticker"]
    if name:
        label += f"  {name}"
    return label


def find_in_watchlist(ticker: str) -> Optional[dict]:
    """Return the watchlist entry for *ticker*, or None."""
    ticker = ticker.strip().upper()
    for e in _load():
        if e.get("ticker", "").upper() == ticker:
            return e
    return None
