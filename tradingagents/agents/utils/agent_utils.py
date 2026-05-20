from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Applied to every agent whose output reaches the saved report —
    analysts, researchers, debaters, research manager, trader, and
    portfolio manager — so a non-English run produces a fully localized
    report rather than a mix of languages.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def _detect_market(ticker: str) -> str:
    """Detect market type from ticker suffix."""
    t = ticker.strip().upper()
    if t.endswith((".SS", ".SH", ".SZ")):
        return "cn_a_share"
    if t.endswith(".HK"):
        return "hk"
    if t.endswith("-USD") or t.endswith("-USDT"):
        return "crypto"
    return "us_intl"


# Market-specific trading rules injected into every agent's context
_MARKET_RULES = {
    "cn_a_share": (
        "This is a **Chinese A-share stock**. Critical trading rules that MUST inform all analysis and recommendations:\n"
        "- **T+1 settlement**: Shares bought today CANNOT be sold until the next trading day. "
        "This means intraday stop-losses are IMPOSSIBLE — if the stock drops 8% after you buy, you must wait until tomorrow to sell.\n"
        "- **±10% daily price limit** (涨跌停): Main board stocks can move at most ±10% per day. "
        "STAR Market (科创板, 688xxx) and ChiNext (创业板, 300xxx) have ±20% limits.\n"
        "- **No short selling** for most retail investors. Margin short selling (融券) has very high barriers.\n"
        "- **Trading hours**: 09:30-11:30 and 13:00-15:00 CST (2 sessions, 4 hours total). "
        "Pre-market bidding: 09:15-09:25 (price discovery), 09:25-09:30 (no cancellation).\n"
        "- **Currency**: CNY (Chinese Yuan).\n"
        "- **Implications for strategy**: Stop-loss orders must account for T+1 delay. "
        "Position sizing should be more conservative because you cannot exit same-day. "
        "Prefer buying near the end of the trading session to minimize overnight gap risk."
    ),
    "hk": (
        "This is a **Hong Kong stock**. Key trading rules:\n"
        "- **T+0 trading**: Can buy and sell on the same day.\n"
        "- **No daily price limits**: Stocks can move unlimited percentage in a single day.\n"
        "- **Short selling allowed** for designated stocks.\n"
        "- **Trading hours**: 09:30-12:00 and 13:00-16:00 HKT.\n"
        "- **Lot size**: Minimum trading unit varies by stock (not always 100 shares).\n"
        "- **Currency**: HKD."
    ),
    "crypto": (
        "This is a **crypto asset**. Treat it as a crypto asset rather than a company. "
        "Do not assume company fundamentals are available. "
        "Trading is 24/7 with no price limits. High volatility is expected."
    ),
    "us_intl": (
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.T`)."
    ),
}


def build_instrument_context(ticker: str, asset_type: str = "stock") -> str:
    """Describe the exact instrument and inject market-specific trading rules.

    Auto-detects the market from the ticker suffix and provides the
    appropriate trading rules (T+1, price limits, trading hours, etc.)
    so all downstream agents make market-aware recommendations.
    """
    # Override detection if explicitly crypto
    if asset_type == "crypto":
        market = "crypto"
    else:
        market = _detect_market(ticker)

    instrument_label = "asset" if market == "crypto" else "instrument"
    market_rules = _MARKET_RULES.get(market, _MARKET_RULES["us_intl"])

    return (
        f"The {instrument_label} to analyze is `{ticker}`. "
        f"Use this exact ticker in every tool call, report, and recommendation.\n\n"
        f"## Market Rules\n{market_rules}"
    )

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
