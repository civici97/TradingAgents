from typing import Annotated
import logging

logger = logging.getLogger(__name__)

# Import from vendor-specific modules
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .tushare_provider import (
    get_stock_data as get_tushare_stock,
    get_indicators as get_tushare_indicators,
    get_fundamentals as get_tushare_fundamentals,
    get_balance_sheet as get_tushare_balance_sheet,
    get_cashflow as get_tushare_cashflow,
    get_income_statement as get_tushare_income_statement,
    get_news as get_tushare_news,
    get_global_news as get_tushare_global_news,
    get_insider_transactions as get_tushare_insider_transactions,
    TushareRateLimitError,
)
from .alpha_vantage_common import AlphaVantageRateLimitError

try:
    from yfinance.exceptions import YFRateLimitError
except ImportError:
    YFRateLimitError = None

# ---------------------------------------------------------------------------
# Optional vendor imports — guarded so missing packages don't break the system.
# Vendors whose package is not installed are simply excluded from the routing
# table; the fallback chain skips them transparently.
# ---------------------------------------------------------------------------

# AKShare (completely free, no auth)
_akshare_available = False
try:
    from .akshare_provider import (
        get_stock_data as get_akshare_stock,
        get_indicators as get_akshare_indicators,
        get_fundamentals as get_akshare_fundamentals,
        get_balance_sheet as get_akshare_balance_sheet,
        get_cashflow as get_akshare_cashflow,
        get_income_statement as get_akshare_income_statement,
        get_news as get_akshare_news,
        get_global_news as get_akshare_global_news,
        get_insider_transactions as get_akshare_insider_transactions,
        AKShareDataError,
    )
    _akshare_available = True
except ImportError:
    AKShareDataError = None
    logger.debug("akshare not installed — AKShare vendor disabled")

# BaoStock (completely free, no auth)
_baostock_available = False
try:
    from .baostock_provider import (
        get_stock_data as get_baostock_stock,
        get_indicators as get_baostock_indicators,
        get_fundamentals as get_baostock_fundamentals,
        get_balance_sheet as get_baostock_balance_sheet,
        get_cashflow as get_baostock_cashflow,
        get_income_statement as get_baostock_income_statement,
        get_news as get_baostock_news,
        get_global_news as get_baostock_global_news,
        get_insider_transactions as get_baostock_insider_transactions,
        BaoStockDataError,
    )
    _baostock_available = True
except ImportError:
    BaoStockDataError = None
    logger.debug("baostock not installed — BaoStock vendor disabled")

# JoinQuant (free account required at joinquant.com)
_joinquant_available = False
try:
    from .joinquant_provider import (
        get_stock_data as get_joinquant_stock,
        get_indicators as get_joinquant_indicators,
        get_fundamentals as get_joinquant_fundamentals,
        get_balance_sheet as get_joinquant_balance_sheet,
        get_cashflow as get_joinquant_cashflow,
        get_income_statement as get_joinquant_income_statement,
        get_news as get_joinquant_news,
        get_global_news as get_joinquant_global_news,
        get_insider_transactions as get_joinquant_insider_transactions,
        JoinQuantDataError,
        JoinQuantRateLimitError,
    )
    _joinquant_available = True
except ImportError:
    JoinQuantDataError = None
    JoinQuantRateLimitError = None
    logger.debug("jqdatasdk not installed — JoinQuant vendor disabled")

# Configuration and routing logic
from .config import get_config

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    }
}

VENDOR_LIST = [
    "joinquant",
    "akshare",
    "baostock",
    "tushare",
    "yfinance",
    "alpha_vantage",
]

# ---------------------------------------------------------------------------
# Build VENDOR_METHODS dynamically based on which packages are installed
# ---------------------------------------------------------------------------

VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "tushare": get_tushare_stock,
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    # technical_indicators
    "get_indicators": {
        "tushare": get_tushare_indicators,
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "tushare": get_tushare_fundamentals,
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "tushare": get_tushare_balance_sheet,
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "tushare": get_tushare_cashflow,
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "tushare": get_tushare_income_statement,
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "tushare": get_tushare_news,
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "tushare": get_tushare_global_news,
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "tushare": get_tushare_insider_transactions,
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
}

# Inject optional vendors when their packages are available
if _akshare_available:
    VENDOR_METHODS["get_stock_data"]["akshare"] = get_akshare_stock
    VENDOR_METHODS["get_indicators"]["akshare"] = get_akshare_indicators
    VENDOR_METHODS["get_fundamentals"]["akshare"] = get_akshare_fundamentals
    VENDOR_METHODS["get_balance_sheet"]["akshare"] = get_akshare_balance_sheet
    VENDOR_METHODS["get_cashflow"]["akshare"] = get_akshare_cashflow
    VENDOR_METHODS["get_income_statement"]["akshare"] = get_akshare_income_statement
    VENDOR_METHODS["get_news"]["akshare"] = get_akshare_news
    VENDOR_METHODS["get_global_news"]["akshare"] = get_akshare_global_news
    VENDOR_METHODS["get_insider_transactions"]["akshare"] = get_akshare_insider_transactions

if _baostock_available:
    VENDOR_METHODS["get_stock_data"]["baostock"] = get_baostock_stock
    VENDOR_METHODS["get_indicators"]["baostock"] = get_baostock_indicators
    VENDOR_METHODS["get_fundamentals"]["baostock"] = get_baostock_fundamentals
    VENDOR_METHODS["get_balance_sheet"]["baostock"] = get_baostock_balance_sheet
    VENDOR_METHODS["get_cashflow"]["baostock"] = get_baostock_cashflow
    VENDOR_METHODS["get_income_statement"]["baostock"] = get_baostock_income_statement
    VENDOR_METHODS["get_news"]["baostock"] = get_baostock_news
    VENDOR_METHODS["get_global_news"]["baostock"] = get_baostock_global_news
    VENDOR_METHODS["get_insider_transactions"]["baostock"] = get_baostock_insider_transactions

if _joinquant_available:
    VENDOR_METHODS["get_stock_data"]["joinquant"] = get_joinquant_stock
    VENDOR_METHODS["get_indicators"]["joinquant"] = get_joinquant_indicators
    VENDOR_METHODS["get_fundamentals"]["joinquant"] = get_joinquant_fundamentals
    VENDOR_METHODS["get_balance_sheet"]["joinquant"] = get_joinquant_balance_sheet
    VENDOR_METHODS["get_cashflow"]["joinquant"] = get_joinquant_cashflow
    VENDOR_METHODS["get_income_statement"]["joinquant"] = get_joinquant_income_statement
    VENDOR_METHODS["get_news"]["joinquant"] = get_joinquant_news
    VENDOR_METHODS["get_global_news"]["joinquant"] = get_joinquant_global_news
    VENDOR_METHODS["get_insider_transactions"]["joinquant"] = get_joinquant_insider_transactions


def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")

def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support.

    The fallback chain is built from:
    1. Primary vendors from config (comma-separated, e.g. "joinquant,tushare,akshare")
    2. All remaining available vendors appended as further fallbacks

    Fallback triggers include rate-limit errors AND vendor-specific "not
    supported" errors (e.g. BaoStockDataError for news methods), ensuring
    that vendors which don't implement a particular method gracefully defer
    to the next vendor in the chain.
    """
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    # Build fallback chain: primary vendors first, then remaining available vendors
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    # Errors that trigger fallback to the next vendor:
    # - Rate-limit errors (vendor temporarily unavailable)
    # - Data errors from vendors that don't support a method (e.g. BaoStock news)
    _fallback_errors = [AlphaVantageRateLimitError, TushareRateLimitError]
    if YFRateLimitError is not None:
        _fallback_errors.append(YFRateLimitError)
    if AKShareDataError is not None:
        _fallback_errors.append(AKShareDataError)
    if BaoStockDataError is not None:
        _fallback_errors.append(BaoStockDataError)
    if JoinQuantDataError is not None:
        _fallback_errors.append(JoinQuantDataError)
    if JoinQuantRateLimitError is not None:
        _fallback_errors.append(JoinQuantRateLimitError)
    fallback_errors = tuple(_fallback_errors)

    last_error = None
    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except fallback_errors as e:
            logger.info(f"Vendor '{vendor}' for '{method}' fell back: {e}")
            last_error = e
            continue  # Fallback to next vendor

    raise RuntimeError(f"No available vendor for '{method}' (last error: {last_error})")