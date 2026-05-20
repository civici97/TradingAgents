"""JoinQuant (聚宽) data provider for Chinese A-share stocks.

JoinQuant provides institutional-grade financial data via its jqdatasdk.
Data quality is considered the best among free Chinese data sources:
- Professionally cleaned and validated
- Rich valuation data (PE/PB/PS with multiple calculation methods)
- Industry classification (Shenwan/CITIC)
- Full financial statement coverage

Requires a free account at https://www.joinquant.com.
Set JOINQUANT_USERNAME and JOINQUANT_PASSWORD environment variables.

Implements the same interface as tushare_provider.py / y_finance.py so it
can be registered as a vendor in interface.py.
"""

import logging
import os
from datetime import datetime
from typing import Annotated

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-initialized JoinQuant connection
# ---------------------------------------------------------------------------
_jq = None
_authenticated = False


class JoinQuantDataError(Exception):
    """Raised when JoinQuant returns unexpected data or a connection error."""


class JoinQuantRateLimitError(Exception):
    """Raised when JoinQuant daily quota is exceeded."""


def _get_jq():
    """Return an authenticated jqdatasdk module handle (lazy init)."""
    global _jq, _authenticated
    if _jq is None:
        try:
            import jqdatasdk as jq
            _jq = jq
        except ImportError:
            raise ImportError(
                "jqdatasdk is not installed. Install it with: "
                "pip install 'tradingagents[joinquant]'  or  pip install jqdatasdk"
            )
    if not _authenticated:
        username = os.environ.get("JOINQUANT_USERNAME", "")
        password = os.environ.get("JOINQUANT_PASSWORD", "")
        if not username or not password:
            raise RuntimeError(
                "JOINQUANT_USERNAME and JOINQUANT_PASSWORD environment variables "
                "are not set. Register at https://www.joinquant.com and set "
                "these in your .env file."
            )
        try:
            _jq.auth(username, password)
            _authenticated = True
        except Exception as e:
            err_msg = str(e).lower()
            if "quota" in err_msg or "limit" in err_msg or "exceed" in err_msg:
                raise JoinQuantRateLimitError(str(e))
            raise RuntimeError(f"JoinQuant authentication failed: {e}")
    return _jq


def _convert_ticker(symbol: str) -> str:
    """Convert yfinance/tushare-style ticker to JoinQuant format.

    600989.SS  -> 600989.XSHG
    600989.SH  -> 600989.XSHG
    000001.SZ  -> 000001.XSHE
    SH600989   -> 600989.XSHG
    """
    symbol = symbol.strip().upper()

    # Xueqiu-style prefix
    if symbol.startswith("SH") and len(symbol) > 2 and symbol[2:].isdigit():
        return f"{symbol[2:]}.XSHG"
    if symbol.startswith("SZ") and len(symbol) > 2 and symbol[2:].isdigit():
        return f"{symbol[2:]}.XSHE"

    # Has suffix
    if symbol.endswith((".SS", ".SH")):
        base = symbol.split(".")[0]
        return f"{base}.XSHG"
    if symbol.endswith(".SZ"):
        base = symbol.split(".")[0]
        return f"{base}.XSHE"

    # Pure digits — guess exchange
    base = symbol.split(".")[0]
    if base.isdigit():
        if base.startswith(("6", "9")):
            return f"{base}.XSHG"
        else:
            return f"{base}.XSHE"

    return symbol


def _safe_call(func):
    """Wrap a JoinQuant API call with quota-exceeded detection."""
    try:
        return func()
    except Exception as e:
        err_msg = str(e).lower()
        if any(kw in err_msg for kw in ("quota", "limit", "exceed", "次数")):
            raise JoinQuantRateLimitError(str(e))
        raise


# ============================================================================
# OHLCV Stock Price Data
# ============================================================================

def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Get OHLCV stock data from JoinQuant (highest quality)."""
    try:
        jq = _get_jq()
        data = _safe_call(lambda: jq.get_price(
            jq_code,
            start_date=start_date,
            end_date=end_date,
            frequency="daily",
            fields=["open", "high", "low", "close", "volume"],
            fq="pre",  # 前复权
        ))
    except JoinQuantRateLimitError:
        raise
    except (ImportError, RuntimeError) as e:
        # Map ImportError (missing package) and RuntimeError (missing credentials) 
        # to JoinQuantDataError so the fallback mechanism handles it gracefully.
        raise JoinQuantDataError(f"JoinQuant unavailable for {symbol}: {e}")
    except Exception as e:
        raise JoinQuantDataError(f"JoinQuant stock data error for {symbol}: {e}")

    if data is None or data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    # Reset index (date is the index in jqdatasdk)
    data = data.reset_index()
    data = data.rename(columns={
        "index": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    })

    # Round numerical values
    for col in ["Open", "High", "Low", "Close"]:
        if col in data.columns:
            data[col] = data[col].round(2)

    cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
    cols = [c for c in cols if c in data.columns]
    data = data[cols]

    csv_string = data.to_csv(index=False)

    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data source: JoinQuant (聚宽)\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


# ============================================================================
# Technical Indicators (uses stockstats on JoinQuant data)
# ============================================================================

def _load_ohlcv_joinquant(symbol: str, curr_date: str) -> pd.DataFrame:
    """Load OHLCV data from JoinQuant with caching, for stockstats calculations."""
    from .config import get_config
    from .utils import safe_ticker_component
    from .stockstats_utils import _clean_dataframe

    safe_symbol = safe_ticker_component(symbol)
    config = get_config()
    jq = _get_jq()
    jq_code = _convert_ticker(symbol)

    # Cache: 5 years of data
    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today_date.strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{safe_symbol}-JoinQuant-data-{start_str}-{end_str}.csv",
    )

    if os.path.exists(data_file):
        data = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
    else:
        try:
            data = _safe_call(lambda: jq.get_price(
                jq_code,
                start_date=start_str,
                end_date=end_str,
                frequency="daily",
                fields=["open", "high", "low", "close", "volume"],
                fq="pre",
            ))
        except Exception as e:
            logger.error(f"JoinQuant OHLCV load error for {symbol}: {e}")
            return pd.DataFrame()

        if data is None or data.empty:
            return pd.DataFrame()

        data = data.reset_index()
        data = data.rename(columns={
            "index": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        })
        data = data[["Date", "Open", "High", "Low", "Close", "Volume"]]
        data.to_csv(data_file, index=False, encoding="utf-8")

    data = _clean_dataframe(data)

    curr_date_dt = pd.to_datetime(curr_date)
    data = data[data["Date"] <= curr_date_dt]

    return data


def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator"],
    curr_date: Annotated[str, "current date YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Get technical indicators using JoinQuant data + stockstats."""
    from datetime import datetime as dt
    from dateutil.relativedelta import relativedelta
    from stockstats import wrap

    best_ind_params = {
        "close_50_sma": "50 SMA: Medium-term trend indicator.",
        "close_200_sma": "200 SMA: Long-term trend benchmark.",
        "close_10_ema": "10 EMA: Responsive short-term average.",
        "macd": "MACD: Momentum via EMA differences.",
        "macds": "MACD Signal: Smoothed MACD line.",
        "macdh": "MACD Histogram: Gap between MACD and signal.",
        "rsi": "RSI: Overbought/oversold conditions.",
        "boll": "Bollinger Middle: 20 SMA basis.",
        "boll_ub": "Bollinger Upper Band.",
        "boll_lb": "Bollinger Lower Band.",
        "atr": "ATR: Average true range volatility.",
        "vwma": "VWMA: Volume-weighted moving average.",
        "mfi": "MFI: Money Flow Index.",
    }

    if indicator not in best_ind_params:
        raise ValueError(
            f"Indicator {indicator} is not supported. "
            f"Please choose from: {list(best_ind_params.keys())}"
        )

    end_date = curr_date
    curr_date_dt = dt.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    try:
        data = _load_ohlcv_joinquant(symbol, curr_date)
        if data.empty:
            return f"No data available for {symbol}"

        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        df[indicator]

        result_dict = {}
        for _, row in df.iterrows():
            date_str = row["Date"]
            val = row[indicator]
            result_dict[date_str] = "N/A" if pd.isna(val) else str(val)

        current_dt = curr_date_dt
        ind_string = ""
        while current_dt >= before:
            date_str = current_dt.strftime("%Y-%m-%d")
            value = result_dict.get(date_str, "N/A: Not a trading day")
            ind_string += f"{date_str}: {value}\n"
            current_dt = current_dt - relativedelta(days=1)

    except Exception as e:
        logger.error(f"Error getting JoinQuant indicators: {e}")
        return f"Error calculating {indicator} for {symbol}: {e}"

    result_str = (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
        + ind_string
        + "\n\n"
        + best_ind_params.get(indicator, "No description available.")
    )
    return result_str


# ============================================================================
# Company Fundamentals
# ============================================================================

def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date"] = None,
) -> str:
    """Get company fundamentals from JoinQuant (highest quality valuation data)."""
    jq = _get_jq()
    jq_code = _convert_ticker(ticker)

    try:
        lines = []
        lines.append(f"# Company Fundamentals for {ticker.upper()}")
        lines.append(f"# Data source: JoinQuant (聚宽)")
        lines.append(f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        query_date = curr_date or datetime.now().strftime("%Y-%m-%d")

        # Valuation data (PE, PB, PS, market cap)
        try:
            q = jq.query(jq.valuation).filter(
                jq.valuation.code == jq_code
            )
            val_data = _safe_call(lambda: jq.get_fundamentals(q, date=query_date))
            if val_data is not None and not val_data.empty:
                row = val_data.iloc[0]
                lines.append("## Valuation Data\n")
                val_map = [
                    ("PE Ratio", "pe_ratio"),
                    ("PE Ratio (LYR)", "pe_ratio_lyr"),
                    ("PB Ratio", "pb_ratio"),
                    ("PS Ratio", "ps_ratio"),
                    ("PCF Ratio", "pcf_ratio"),
                    ("Market Cap (元)", "market_cap"),
                    ("Circulating Market Cap (元)", "circulating_market_cap"),
                    ("Turnover Ratio", "turnover_ratio"),
                    ("Capitalization (万股)", "capitalization"),
                    ("Circulating Cap (万股)", "circulating_cap"),
                ]
                for label, col in val_map:
                    val = row.get(col)
                    if pd.notna(val):
                        lines.append(f"{label}: {val}")
        except Exception as e:
            logger.warning(f"JoinQuant valuation data failed: {e}")

        # Company info via security info
        try:
            info = _safe_call(lambda: jq.get_security_info(jq_code))
            if info is not None:
                lines.append("\n## Company Info\n")
                lines.append(f"Name: {info.display_name}")
                lines.append(f"Type: {info.type}")
                lines.append(f"Start Date: {info.start_date}")
        except Exception as e:
            logger.warning(f"JoinQuant security info failed: {e}")

        # Industry classification (Shenwan)
        try:
            industry = _safe_call(lambda: jq.get_industry(jq_code, date=query_date))
            if industry and jq_code in industry:
                lines.append("\n## Industry Classification\n")
                for cls_type, cls_info in industry[jq_code].items():
                    lines.append(f"{cls_type}: {cls_info.get('industry_name', 'N/A')} ({cls_info.get('industry_code', '')})")
        except Exception as e:
            logger.warning(f"JoinQuant industry data failed: {e}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


# ============================================================================
# Financial Statements
# ============================================================================

def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get balance sheet data from JoinQuant."""
    jq = _get_jq()
    jq_code = _convert_ticker(ticker)

    try:
        q = jq.query(jq.balance).filter(
            jq.balance.code == jq_code
        )
        query_date = curr_date or datetime.now().strftime("%Y-%m-%d")

        # Get recent quarters
        limit = 4 if freq.lower() == "quarterly" else 3
        data = _safe_call(lambda: jq.get_fundamentals(q, date=query_date))

        if data is None or data.empty:
            return f"No balance sheet data found for symbol '{ticker}'"

        csv_string = data.to_csv(index=False)

        header = f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        header += f"# Data source: JoinQuant (聚宽)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except JoinQuantRateLimitError:
        raise
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get cash flow data from JoinQuant."""
    jq = _get_jq()
    jq_code = _convert_ticker(ticker)

    try:
        q = jq.query(jq.cash_flow).filter(
            jq.cash_flow.code == jq_code
        )
        query_date = curr_date or datetime.now().strftime("%Y-%m-%d")

        data = _safe_call(lambda: jq.get_fundamentals(q, date=query_date))

        if data is None or data.empty:
            return f"No cash flow data found for symbol '{ticker}'"

        csv_string = data.to_csv(index=False)

        header = f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        header += f"# Data source: JoinQuant (聚宽)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except JoinQuantRateLimitError:
        raise
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get income statement data from JoinQuant."""
    jq = _get_jq()
    jq_code = _convert_ticker(ticker)

    try:
        q = jq.query(jq.income).filter(
            jq.income.code == jq_code
        )
        query_date = curr_date or datetime.now().strftime("%Y-%m-%d")

        data = _safe_call(lambda: jq.get_fundamentals(q, date=query_date))

        if data is None or data.empty:
            return f"No income statement data found for symbol '{ticker}'"

        csv_string = data.to_csv(index=False)

        header = f"# Income Statement data for {ticker.upper()} ({freq})\n"
        header += f"# Data source: JoinQuant (聚宽)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except JoinQuantRateLimitError:
        raise
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


# ============================================================================
# News (not supported — will fall through to other vendors)
# ============================================================================

def get_news(
    ticker: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "start date YYYY-MM-DD"],
    end_date: Annotated[str, "end date YYYY-MM-DD"],
) -> str:
    """JoinQuant does not provide news data."""
    raise JoinQuantDataError("JoinQuant does not support news data")


def get_global_news(
    curr_date: Annotated[str, "current date YYYY-MM-DD"],
    look_back_days: Annotated[int, "how many days to look back"] = 7,
    limit: Annotated[int, "max articles"] = 10,
) -> str:
    """JoinQuant does not provide news data."""
    raise JoinQuantDataError("JoinQuant does not support global news data")


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    """JoinQuant does not provide insider transaction data."""
    raise JoinQuantDataError("JoinQuant does not support insider transaction data")
