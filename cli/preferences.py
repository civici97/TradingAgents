"""User-preference persistence for TradingAgents CLI.

Remembers the last interactive selections (LLM provider, models,
language, analysts, depth, etc.) so they become defaults on the
next invocation — no more re-typing identical values each run.

File location: ``~/.tradingagents/preferences.json``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

_TRADINGAGENTS_HOME = Path.home() / ".tradingagents"
_PREFS_FILE = _TRADINGAGENTS_HOME / "preferences.json"


def _ensure_file() -> Path:
    _PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _PREFS_FILE.exists():
        _PREFS_FILE.write_text("{}", encoding="utf-8")
    return _PREFS_FILE


def load_preferences() -> Dict[str, Any]:
    """Load saved preferences.  Returns empty dict on first run."""
    path = _ensure_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_preferences(prefs: Dict[str, Any]) -> None:
    """Persist *prefs* to disk (full overwrite)."""
    path = _ensure_file()
    path.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")


def save_selections(selections: dict) -> None:
    """Extract the subset of interactive selections worth remembering and save them.

    Called at the start of ``run_analysis`` so the preferences are
    available on the *next* invocation.
    """
    # Only save analyst *values*, not the Enum objects
    analyst_values = []
    for a in selections.get("analysts", []):
        analyst_values.append(a.value if hasattr(a, "value") else str(a))

    prefs = {
        "last_provider": selections.get("llm_provider", ""),
        "last_backend_url": selections.get("backend_url"),
        "last_quick_llm": selections.get("shallow_thinker", ""),
        "last_deep_llm": selections.get("deep_thinker", ""),
        "last_language": selections.get("output_language", "English"),
        "last_analysts": analyst_values,
        "last_depth": selections.get("research_depth", 1),
        "last_google_thinking_level": selections.get("google_thinking_level"),
        "last_openai_reasoning_effort": selections.get("openai_reasoning_effort"),
        "last_anthropic_effort": selections.get("anthropic_effort"),
    }
    save_preferences(prefs)


def get_pref(key: str, default: Any = None) -> Any:
    """Convenience getter for a single preference value."""
    return load_preferences().get(key, default)
