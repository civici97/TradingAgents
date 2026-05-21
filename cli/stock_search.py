"""Stock-name fuzzy search for Chinese A-share tickers.

Uses *akshare* to download the full A-share stock list, caches it
locally (7-day TTL), and provides three matching modes:

1. **Exact numeric code** — ``300750`` → ``300750.SZ``
2. **Chinese name substring** — ``宁德时代`` → ``300750.SZ``
3. **Pinyin-initial prefix** — ``ndsdk`` → ``宁德时代 → 300750.SZ``

For non-A-share tickers (US, HK, etc.) the caller should bypass this
module and accept the raw user input as-is.
"""

from __future__ import annotations

import json
import time
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple

_TRADINGAGENTS_HOME = Path.home() / ".tradingagents"
_CACHE_DIR = _TRADINGAGENTS_HOME / "cache"
_STOCK_NAMES_FILE = _CACHE_DIR / "stock_names.json"
_CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days



# ── pinyin helpers ──────────────────────────────────────────────────────────

# GB2312/GBK pinyin-initial lookup — the authoritative approach.
# Chinese characters encoded in GBK have their pinyin-initial determined
# by the high byte.  This table maps GBK high-byte ranges to initials.
# Coverage: virtually 100 % of characters found in A-share stock names.

_GBK_PINYIN_TABLE: list[tuple[int, str]] = [
    (0xB0A1, "a"), (0xB0C5, "b"), (0xB2C1, "c"), (0xB4EE, "d"),
    (0xB6EA, "e"), (0xB7A2, "f"), (0xB8C1, "g"), (0xBAB8, "h"),
    (0xBBF7, "j"), (0xBFA6, "k"), (0xC0AC, "l"), (0xC2E8, "m"),
    (0xC4C3, "n"), (0xC5B6, "o"), (0xC5BE, "p"), (0xC6DA, "q"),
    (0xC8BB, "r"), (0xC8F6, "s"), (0xCBFA, "t"), (0xCDDA, "w"),
    (0xCEF4, "x"), (0xD1B9, "y"), (0xD4D1, "z"),
]


def _get_pinyin_initial(char: str) -> str:
    """Return the lowercase pinyin initial letter of a single CJK character.

    Uses GBK encoding to look up the initial from the standard GB2312 table.
    Falls back to the character itself if not CJK or encoding fails.
    """
    if not ("\u4e00" <= char <= "\u9fff"):
        return char.lower()

    try:
        gbk_bytes = char.encode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return char.lower()

    if len(gbk_bytes) != 2:
        return char.lower()

    code = (gbk_bytes[0] << 8) | gbk_bytes[1]

    # Binary search through the pinyin table
    initial = "a"
    for boundary, letter in _GBK_PINYIN_TABLE:
        if code >= boundary:
            initial = letter
        else:
            break
    return initial


def _pinyin_initials(text: str) -> str:
    """Return the concatenated pinyin initials of *text*."""
    return "".join(_get_pinyin_initial(ch) for ch in text if ch.strip())



# ── cache management ────────────────────────────────────────────────────────

def _is_cache_fresh() -> bool:
    if not _STOCK_NAMES_FILE.exists():
        return False
    age = time.time() - _STOCK_NAMES_FILE.stat().st_mtime
    return age < _CACHE_TTL_SECONDS


def _download_stock_list() -> List[dict]:
    """Download the full A-share stock list from akshare.

    Returns a list of dicts: ``[{"code": "300750", "name": "宁德时代", "ticker": "300750.SZ"}, ...]``
    """
    try:
        import akshare as ak
    except ImportError:
        return []

    entries: list[dict] = []
    try:
        # akshare's stock_info_a_code_name() returns a DataFrame with
        # columns: code, name
        df = ak.stock_info_a_code_name()
        for _, row in df.iterrows():
            code = str(row["code"]).strip()
            name = str(row["name"]).strip()
            # Determine exchange suffix
            if code.startswith(("6", "9")):
                suffix = ".SS"  # Shanghai
            elif code.startswith(("0", "2", "3")):
                suffix = ".SZ"  # Shenzhen
            elif code.startswith(("4", "8")):
                suffix = ".BJ"  # Beijing
            else:
                suffix = ".SS"
            ticker = f"{code}{suffix}"
            py_initials = _pinyin_initials(name)
            entries.append({
                "code": code,
                "name": name,
                "ticker": ticker,
                "pinyin": py_initials,
            })
    except Exception:
        pass

    return entries


def _load_cache() -> List[dict]:
    """Load stock list from cache file."""
    try:
        data = json.loads(_STOCK_NAMES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_cache(entries: List[dict]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _STOCK_NAMES_FILE.write_text(
        json.dumps(entries, ensure_ascii=False),
        encoding="utf-8",
    )


def refresh_stock_list(force: bool = False) -> List[dict]:
    """Ensure the local stock-name cache is populated and return it.

    Downloads from akshare on first use or when the cache is stale (>7 days).
    """
    if not force and _is_cache_fresh():
        return _load_cache()

    entries = _download_stock_list()
    if entries:
        _save_cache(entries)
        return entries

    # Fall back to stale cache if download failed
    return _load_cache()


# ── search API ──────────────────────────────────────────────────────────────

def search_stocks(query: str, limit: int = 15) -> List[dict]:
    """Search A-share stocks by code, Chinese name, or pinyin initials.

    Returns up to *limit* matching entries sorted by relevance.
    Each entry: ``{"code": "300750", "name": "宁德时代", "ticker": "300750.SZ", "pinyin": "ndsdk"}``.
    """
    query = query.strip()
    if not query:
        return []

    entries = refresh_stock_list()
    if not entries:
        return []

    query_lower = query.lower()
    is_digit = query.isdigit()

    exact: list[dict] = []
    prefix: list[dict] = []
    contains: list[dict] = []

    for e in entries:
        code = e.get("code", "")
        name = e.get("name", "")
        py = e.get("pinyin", "")

        # 1. Exact code match
        if is_digit and code == query:
            exact.append(e)
            continue

        # 2. Code prefix match
        if is_digit and code.startswith(query):
            prefix.append(e)
            continue

        # 3. Chinese name exact match
        if query in name:
            if name == query:
                exact.append(e)
            elif name.startswith(query):
                prefix.append(e)
            else:
                contains.append(e)
            continue

        # 4. Pinyin initial match
        if not is_digit and py.startswith(query_lower):
            prefix.append(e)
            continue

        # 5. Pinyin contains
        if not is_digit and query_lower in py:
            contains.append(e)

    results = exact + prefix + contains
    return results[:limit]


def search_display_label(entry: dict) -> str:
    """Format a search result for display: ``300750.SZ  宁德时代``."""
    return f"{entry['ticker']}  {entry['name']}"


def is_a_share_input(query: str) -> bool:
    """Heuristic: does the input look like it's trying to find a Chinese A-share stock?

    True if the query contains CJK characters, is a 6-digit number, or
    looks like pinyin initials (all lowercase ASCII, 2-8 chars).
    """
    query = query.strip()
    if not query:
        return False

    # Contains CJK characters
    if any("\u4e00" <= ch <= "\u9fff" for ch in query):
        return True

    # 6-digit stock code
    if query.isdigit() and len(query) == 6:
        return True

    # Pure lowercase ascii, 2-8 chars — likely pinyin initials
    if query.isascii() and query.isalpha() and query.islower() and 2 <= len(query) <= 8:
        return True

    return False
