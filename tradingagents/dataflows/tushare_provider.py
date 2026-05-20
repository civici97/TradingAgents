"""Tushare data provider for Chinese A-share stocks.

Implements the same interface as y_finance.py so it can be registered as
a vendor in interface.py. Tushare Pro API requires a token which is read
from the TUSHARE_TOKEN environment variable or from config.
"""

import os
import logging
import time
from datetime import datetime
from typing import Annotated

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-initialised Tushare Pro API handle
# ---------------------------------------------------------------------------
_pro = None


class TushareRateLimitError(Exception):
    """Raised when Tushare returns a rate-limit / quota error."""


# Global throttle: minimum seconds between consecutive Tushare API calls
_MIN_CALL_INTERVAL = 0.6  # seconds — Tushare free tier limits ~100 calls/min
_last_call_time = 0.0


def _throttle():
    """Ensure at least _MIN_CALL_INTERVAL seconds between API calls."""
    global _last_call_time
    now = time.time()
    elapsed = now - _last_call_time
    if elapsed < _MIN_CALL_INTERVAL:
        time.sleep(_MIN_CALL_INTERVAL - elapsed)
    _last_call_time = time.time()


def _get_pro():
    """Return a cached tushare pro api handle."""
    global _pro
    if _pro is None:
        import tushare as ts
        token = os.environ.get("TUSHARE_TOKEN", "")
        if not token:
            raise RuntimeError(
                "TUSHARE_TOKEN environment variable is not set. "
                "Please set it in your .env file."
            )
        ts.set_token(token)
        _pro = ts.pro_api()
    return _pro


def _ts_retry(func, max_retries=5, base_delay=5.0):
    """Retry a tushare call with exponential backoff on rate limits.

    Also applies global throttling to avoid hitting the rate limit in the
    first place.
    """
    for attempt in range(max_retries + 1):
        _throttle()
        try:
            return func()
        except Exception as e:
            err_msg = str(e).lower()
            is_rate_limit = any(kw in err_msg for kw in (
                "freq", "limit", "抱歉", "每分钟", "too many",
                "exceed", "quota", "请求过于频繁", "访问过快",
            ))
            if is_rate_limit:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Tushare rate limited, retrying in {delay:.0f}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                else:
                    raise TushareRateLimitError(str(e))
            else:
                raise


def _convert_ticker(symbol: str) -> str:
    """Convert yfinance-style ticker to tushare format.

    600989.SS -> 600989.SH  (Shanghai)
    000001.SZ -> 000001.SZ  (Shenzhen, same)
    600989    -> 600989.SH  (guess based on code prefix)
    """
    symbol = symbol.strip().upper()

    # Already has tushare suffix
    if symbol.endswith(".SH") or symbol.endswith(".SZ"):
        return symbol

    # yfinance Shanghai suffix
    if symbol.endswith(".SS"):
        return symbol[:-3] + ".SH"

    # Strip any other suffix and guess
    base = symbol.split(".")[0]
    if base.startswith(("6", "9")):
        return f"{base}.SH"
    else:
        return f"{base}.SZ"


def _date_to_ts(date_str: str) -> str:
    """Convert YYYY-MM-DD to YYYYMMDD for tushare."""
    return date_str.replace("-", "")


# ============================================================================
# OHLCV Stock Price Data
# ============================================================================

def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Get OHLCV stock data from Tushare."""
    pro = _get_pro()
    ts_code = _convert_ticker(symbol)

    data = _ts_retry(lambda: pro.daily(
        ts_code=ts_code,
        start_date=_date_to_ts(start_date),
        end_date=_date_to_ts(end_date),
    ))

    if data is None or data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    # Rename columns to match yfinance format
    data = data.rename(columns={
        "trade_date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "vol": "Volume",
        "amount": "Amount",
    })

    # Sort by date ascending
    data = data.sort_values("Date")

    # Format date
    data["Date"] = pd.to_datetime(data["Date"], format="%Y%m%d")

    # Select relevant columns
    cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
    cols = [c for c in cols if c in data.columns]
    data = data[cols]

    # Round numerical values
    for col in ["Open", "High", "Low", "Close"]:
        if col in data.columns:
            data[col] = data[col].round(2)

    csv_string = data.to_csv(index=False)

    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data source: Tushare\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


# ============================================================================
# Technical Indicators (uses stockstats on Tushare data)
# ============================================================================

def _load_ohlcv_tushare(symbol: str, curr_date: str) -> pd.DataFrame:
    """Load OHLCV data from Tushare with caching, for stockstats calculations."""
    from .config import get_config
    from .utils import safe_ticker_component
    from .stockstats_utils import _clean_dataframe

    safe_symbol = safe_ticker_component(symbol)
    config = get_config()
    pro = _get_pro()
    ts_code = _convert_ticker(symbol)

    # Cache: 5 years of data
    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y%m%d")
    end_str = today_date.strftime("%Y%m%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{safe_symbol}-Tushare-data-{start_date.strftime('%Y-%m-%d')}-{today_date.strftime('%Y-%m-%d')}.csv",
    )

    if os.path.exists(data_file):
        data = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
    else:
        data = _ts_retry(lambda: pro.daily(
            ts_code=ts_code,
            start_date=start_str,
            end_date=end_str,
        ))

        if data is None or data.empty:
            return pd.DataFrame()

        # Rename to standard format
        data = data.rename(columns={
            "trade_date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "vol": "Volume",
        })
        data = data.sort_values("Date")
        data["Date"] = pd.to_datetime(data["Date"], format="%Y%m%d")
        data = data[["Date", "Open", "High", "Low", "Close", "Volume"]]
        data.to_csv(data_file, index=False, encoding="utf-8")

    data = _clean_dataframe(data)

    # Filter to curr_date to prevent look-ahead bias
    curr_date_dt = pd.to_datetime(curr_date)
    data = data[data["Date"] <= curr_date_dt]

    return data


def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator"],
    curr_date: Annotated[str, "current date YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Get technical indicators using Tushare data + stockstats."""
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
        data = _load_ohlcv_tushare(symbol, curr_date)
        if data.empty:
            return f"No data available for {symbol}"

        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        df[indicator]  # trigger calculation

        # Build result
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
        logger.error(f"Error getting Tushare indicators: {e}")
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
    """Get company fundamentals from Tushare."""
    pro = _get_pro()
    ts_code = _convert_ticker(ticker)

    try:
        # Basic company info
        company_info = _ts_retry(lambda: pro.stock_company(
            ts_code=ts_code,
            fields="ts_code,chairman,manager,secretary,reg_capital,setup_date,"
                   "province,city,introduction,website,email,ann_date,"
                   "business_scope,employees,main_business",
        ))

        # Daily basic indicators (PE, PB, etc.)
        trade_date = _date_to_ts(curr_date) if curr_date else ""
        if trade_date:
            daily_basic = _ts_retry(lambda: pro.daily_basic(
                ts_code=ts_code,
                trade_date=trade_date,
                fields="ts_code,trade_date,close,turnover_rate,turnover_rate_f,"
                       "volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,"
                       "total_share,float_share,free_share,total_mv,circ_mv",
            ))
        else:
            daily_basic = None

        lines = []
        lines.append(f"# Company Fundamentals for {ticker.upper()}")
        lines.append(f"# Data source: Tushare")
        lines.append(f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        if company_info is not None and not company_info.empty:
            row = company_info.iloc[0]
            field_map = [
                ("Chairman", "chairman"),
                ("Manager", "manager"),
                ("Registered Capital", "reg_capital"),
                ("Setup Date", "setup_date"),
                ("Province", "province"),
                ("City", "city"),
                ("Website", "website"),
                ("Employees", "employees"),
                ("Main Business", "main_business"),
                ("Introduction", "introduction"),
            ]
            for label, col in field_map:
                val = row.get(col)
                if pd.notna(val) and str(val).strip():
                    lines.append(f"{label}: {val}")

        if daily_basic is not None and not daily_basic.empty:
            row = daily_basic.iloc[0]
            lines.append("")
            metric_map = [
                ("Close Price", "close"),
                ("PE Ratio (TTM)", "pe_ttm"),
                ("PE Ratio", "pe"),
                ("PB Ratio", "pb"),
                ("PS Ratio (TTM)", "ps_ttm"),
                ("Dividend Yield (%)", "dv_ratio"),
                ("Dividend Yield TTM (%)", "dv_ttm"),
                ("Total Market Value (万元)", "total_mv"),
                ("Circulating Market Value (万元)", "circ_mv"),
                ("Total Shares (万股)", "total_share"),
                ("Float Shares (万股)", "float_share"),
                ("Turnover Rate (%)", "turnover_rate"),
                ("Volume Ratio", "volume_ratio"),
            ]
            for label, col in metric_map:
                val = row.get(col)
                if pd.notna(val):
                    lines.append(f"{label}: {val}")

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
    """Get balance sheet data from Tushare."""
    pro = _get_pro()
    ts_code = _convert_ticker(ticker)

    try:
        # report_type: 1=合并报表
        if freq.lower() == "quarterly":
            data = _ts_retry(lambda: pro.balancesheet(
                ts_code=ts_code,
                report_type="1",
            ))
        else:
            data = _ts_retry(lambda: pro.balancesheet(
                ts_code=ts_code,
                report_type="1",
            ))

        if data is None or data.empty:
            return f"No balance sheet data found for symbol '{ticker}'"

        # Filter by curr_date if provided
        if curr_date:
            cutoff = curr_date.replace("-", "")
            data = data[data["ann_date"] <= cutoff]

        # Take latest 4 reports for quarterly, 3 for annual
        limit = 4 if freq.lower() == "quarterly" else 3
        data = data.head(limit)

        csv_string = data.to_csv(index=False)

        header = f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        header += f"# Data source: Tushare\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get cash flow data from Tushare."""
    pro = _get_pro()
    ts_code = _convert_ticker(ticker)

    try:
        data = _ts_retry(lambda: pro.cashflow(
            ts_code=ts_code,
            report_type="1",
        ))

        if data is None or data.empty:
            return f"No cash flow data found for symbol '{ticker}'"

        if curr_date:
            cutoff = curr_date.replace("-", "")
            data = data[data["ann_date"] <= cutoff]

        limit = 4 if freq.lower() == "quarterly" else 3
        data = data.head(limit)

        csv_string = data.to_csv(index=False)

        header = f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        header += f"# Data source: Tushare\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get income statement data from Tushare."""
    pro = _get_pro()
    ts_code = _convert_ticker(ticker)

    try:
        data = _ts_retry(lambda: pro.income(
            ts_code=ts_code,
            report_type="1",
        ))

        if data is None or data.empty:
            return f"No income statement data found for symbol '{ticker}'"

        if curr_date:
            cutoff = curr_date.replace("-", "")
            data = data[data["ann_date"] <= cutoff]

        limit = 4 if freq.lower() == "quarterly" else 3
        data = data.head(limit)

        csv_string = data.to_csv(index=False)

        header = f"# Income Statement data for {ticker.upper()} ({freq})\n"
        header += f"# Data source: Tushare\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


# ============================================================================
# News
# ============================================================================

def get_news(
    ticker: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "start date YYYY-MM-DD"],
    end_date: Annotated[str, "end date YYYY-MM-DD"],
) -> str:
    """Get news for a stock from Tushare.

    Falls back to major_news if ticker-specific news is unavailable.
    """
    pro = _get_pro()

    try:
        # Try CCTV news (financial news) as a general source
        data = _ts_retry(lambda: pro.news(
            src="sina",
            start_date=_date_to_ts(start_date),
            end_date=_date_to_ts(end_date),
        ))

        if data is None or data.empty:
            return f"No news found for '{ticker}' between {start_date} and {end_date}"

        # Limit to 20 articles
        data = data.head(20)

        articles = []
        for _, row in data.iterrows():
            title = row.get("title", "N/A")
            content = row.get("content", "")
            pub_date = row.get("datetime", "")
            if content and len(str(content)) > 500:
                content = str(content)[:500] + "..."
            articles.append(f"**{title}** ({pub_date})\n{content}\n")

        header = f"# News related to {ticker.upper()}\n"
        header += f"# Period: {start_date} to {end_date}\n"
        header += f"# Data source: Tushare (Sina Finance)\n"
        header += f"# Total articles: {len(articles)}\n\n"

        return header + "\n---\n".join(articles)

    except Exception as e:
        return f"No news available for {ticker}: {str(e)}"


def get_global_news(
    curr_date: Annotated[str, "current date YYYY-MM-DD"],
    look_back_days: Annotated[int, "how many days to look back"] = 7,
    limit: Annotated[int, "max articles"] = 10,
) -> str:
    """Get global/macro news from Tushare."""
    pro = _get_pro()
    from dateutil.relativedelta import relativedelta
    from datetime import datetime as dt

    start_dt = dt.strptime(curr_date, "%Y-%m-%d") - relativedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y%m%d")
    end_date = _date_to_ts(curr_date)

    try:
        data = _ts_retry(lambda: pro.news(
            src="sina",
            start_date=start_date,
            end_date=end_date,
        ))

        if data is None or data.empty:
            return "No global news available."

        data = data.head(limit)

        articles = []
        for _, row in data.iterrows():
            title = row.get("title", "N/A")
            content = row.get("content", "")
            pub_date = row.get("datetime", "")
            if content and len(str(content)) > 300:
                content = str(content)[:300] + "..."
            articles.append(f"**{title}** ({pub_date})\n{content}\n")

        header = f"# Global Financial News\n"
        header += f"# Period: {start_dt.strftime('%Y-%m-%d')} to {curr_date}\n"
        header += f"# Data source: Tushare (Sina Finance)\n\n"

        return header + "\n---\n".join(articles)

    except Exception as e:
        return f"No global news available: {str(e)}"


# ============================================================================
# Insider Transactions
# ============================================================================

def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Get insider/shareholder transactions from Tushare."""
    pro = _get_pro()
    ts_code = _convert_ticker(ticker)

    try:
        # stk_holdertrade: shareholder increase/decrease
        data = _ts_retry(lambda: pro.stk_holdertrade(
            ts_code=ts_code,
        ))

        if data is None or data.empty:
            return f"No insider transactions data found for symbol '{ticker}'"

        # Take recent transactions
        data = data.head(20)

        csv_string = data.to_csv(index=False)

        header = f"# Insider/Shareholder Transactions for {ticker.upper()}\n"
        header += f"# Data source: Tushare\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"
