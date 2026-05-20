"""BaoStock data provider for Chinese A-share stocks.

BaoStock is a completely free financial data library that provides:
- Daily/weekly/monthly K-line data
- **Free minute-level data** (5/15/30/60 min) — a key advantage
- Profitability, growth, solvency, and operational efficiency indicators
- No API key or registration required

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
# Lazy-initialized BaoStock connection
# ---------------------------------------------------------------------------
_bs = None
_logged_in = False


class BaoStockDataError(Exception):
    """Raised when BaoStock returns unexpected data or a connection error."""


def _get_bs():
    """Return a logged-in baostock module handle (lazy init)."""
    global _bs, _logged_in
    if _bs is None:
        try:
            import baostock as bs
            _bs = bs
        except ImportError:
            raise ImportError(
                "baostock is not installed. Install it with: "
                "pip install 'tradingagents[baostock]'  or  pip install baostock"
            )
    if not _logged_in:
        lg = _bs.login()
        if lg.error_code != "0":
            logger.warning(f"BaoStock login warning: {lg.error_msg}")
        _logged_in = True
    return _bs


def _convert_ticker(symbol: str) -> str:
    """Convert yfinance/tushare-style ticker to BaoStock format.

    600989.SS  -> sh.600989
    600989.SH  -> sh.600989
    000001.SZ  -> sz.000001
    SH600989   -> sh.600989
    """
    symbol = symbol.strip().upper()

    # Xueqiu-style prefix
    if symbol.startswith("SH") and len(symbol) > 2 and symbol[2:].isdigit():
        return f"sh.{symbol[2:]}"
    if symbol.startswith("SZ") and len(symbol) > 2 and symbol[2:].isdigit():
        return f"sz.{symbol[2:]}"

    # Has suffix
    if symbol.endswith((".SS", ".SH")):
        base = symbol.split(".")[0]
        return f"sh.{base}"
    if symbol.endswith(".SZ"):
        base = symbol.split(".")[0]
        return f"sz.{base}"

    # Pure digits — guess exchange
    base = symbol.split(".")[0]
    if base.isdigit():
        if base.startswith(("6", "9")):
            return f"sh.{base}"
        else:
            return f"sz.{base}"

    return f"sh.{symbol}"


def _rs_to_df(rs) -> pd.DataFrame:
    """Convert BaoStock ResultData to pandas DataFrame."""
    rows = []
    while (rs.error_code == "0") and rs.next():
        rows.append(rs.get_row_data())
    return pd.DataFrame(rows, columns=rs.fields)


# ============================================================================
# OHLCV Stock Price Data
# ============================================================================

def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Get OHLCV stock data from BaoStock."""
    bs = _get_bs()
    bs_code = _convert_ticker(symbol)

    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="2",  # 前复权
        )

        if rs.error_code != "0":
            raise BaoStockDataError(f"BaoStock error: {rs.error_msg}")

        data = _rs_to_df(rs)
    except BaoStockDataError:
        raise
    except Exception as e:
        raise BaoStockDataError(f"BaoStock stock data error for {symbol}: {e}")

    if data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    # Rename columns to match standard format
    data = data.rename(columns={
        "date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    })

    # Convert numeric columns
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

    # Round numerical values
    for col in ["Open", "High", "Low", "Close"]:
        if col in data.columns:
            data[col] = data[col].round(2)

    csv_string = data.to_csv(index=False)

    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data source: BaoStock\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


# ============================================================================
# Technical Indicators (uses stockstats on BaoStock data)
# ============================================================================

def _load_ohlcv_baostock(symbol: str, curr_date: str) -> pd.DataFrame:
    """Load OHLCV data from BaoStock with caching, for stockstats calculations."""
    from .config import get_config
    from .utils import safe_ticker_component
    from .stockstats_utils import _clean_dataframe

    safe_symbol = safe_ticker_component(symbol)
    config = get_config()
    bs = _get_bs()
    bs_code = _convert_ticker(symbol)

    # Cache: 5 years of data
    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today_date.strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{safe_symbol}-BaoStock-data-{start_str}-{end_str}.csv",
    )

    if os.path.exists(data_file):
        data = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
    else:
        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume",
                start_date=start_str,
                end_date=end_str,
                frequency="d",
                adjustflag="2",
            )
            data = _rs_to_df(rs)
        except Exception as e:
            logger.error(f"BaoStock OHLCV load error for {symbol}: {e}")
            return pd.DataFrame()

        if data.empty:
            return pd.DataFrame()

        # Rename to standard format
        data = data.rename(columns={
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        })
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")
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
    """Get technical indicators using BaoStock data + stockstats."""
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
        data = _load_ohlcv_baostock(symbol, curr_date)
        if data.empty:
            return f"No data available for {symbol}"

        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        df[indicator]  # trigger calculation

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
        logger.error(f"Error getting BaoStock indicators: {e}")
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
    """Get company fundamentals from BaoStock (profitability + growth)."""
    bs = _get_bs()
    bs_code = _convert_ticker(ticker)

    try:
        lines = []
        lines.append(f"# Company Fundamentals for {ticker.upper()}")
        lines.append(f"# Data source: BaoStock")
        lines.append(f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Determine year and quarter from curr_date
        if curr_date:
            dt = pd.to_datetime(curr_date)
            year = dt.year
            quarter = (dt.month - 1) // 3
            if quarter == 0:
                year -= 1
                quarter = 4
        else:
            today = pd.Timestamp.today()
            year = today.year
            quarter = max(1, (today.month - 1) // 3)

        # Profitability indicators
        try:
            rs = bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
            data = _rs_to_df(rs)
            if not data.empty:
                lines.append("## Profitability Indicators\n")
                row = data.iloc[0]
                profit_map = [
                    ("ROE (Return on Equity)", "roeAvg"),
                    ("Net Profit Margin", "npMargin"),
                    ("Gross Profit Margin", "gpMargin"),
                    ("Net Profit (万元)", "netProfit"),
                    ("EPS (Earnings Per Share)", "epsTTM"),
                    ("Revenue (万元)", "operatingRevenue"),
                ]
                for label, col in profit_map:
                    val = row.get(col, "")
                    if val and str(val).strip():
                        lines.append(f"{label}: {val}")
        except Exception as e:
            logger.warning(f"BaoStock profit data failed: {e}")

        # Growth indicators
        try:
            rs = bs.query_growth_data(code=bs_code, year=year, quarter=quarter)
            data = _rs_to_df(rs)
            if not data.empty:
                lines.append("\n## Growth Indicators\n")
                row = data.iloc[0]
                growth_map = [
                    ("YoY Net Profit Growth", "YOYEquity"),
                    ("YoY Revenue Growth", "YOYNI"),
                    ("YoY ROE Growth", "YOYROE"),
                    ("YoY EPS Growth", "YOYEPSBasic"),
                ]
                for label, col in growth_map:
                    val = row.get(col, "")
                    if val and str(val).strip():
                        lines.append(f"{label}: {val}")
        except Exception as e:
            logger.warning(f"BaoStock growth data failed: {e}")

        # Solvency indicators
        try:
            rs = bs.query_dupont_data(code=bs_code, year=year, quarter=quarter)
            data = _rs_to_df(rs)
            if not data.empty:
                lines.append("\n## DuPont Analysis\n")
                row = data.iloc[0]
                dupont_map = [
                    ("DuPont ROE", "dupontROE"),
                    ("Asset Turnover", "dupontAssetTurn"),
                    ("Equity Multiplier", "dupontEquityMultiplier"),
                    ("Net Profit Margin (DuPont)", "dupontNetMargin"),
                    ("Asset/Liability Ratio", "dupontAssetSto498"),
                ]
                for label, col in dupont_map:
                    val = row.get(col, "")
                    if val and str(val).strip():
                        lines.append(f"{label}: {val}")
        except Exception as e:
            logger.warning(f"BaoStock DuPont data failed: {e}")

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
    """Get balance sheet data from BaoStock."""
    bs = _get_bs()
    bs_code = _convert_ticker(ticker)

    try:
        if curr_date:
            dt = pd.to_datetime(curr_date)
            year = dt.year
            quarter = (dt.month - 1) // 3
            if quarter == 0:
                year -= 1
                quarter = 4
        else:
            today = pd.Timestamp.today()
            year = today.year
            quarter = max(1, (today.month - 1) // 3)

        # Collect multiple quarters/years
        all_data = []
        limit = 4 if freq.lower() == "quarterly" else 3
        y, q = year, quarter
        for _ in range(limit):
            try:
                rs = bs.query_balance_data(code=bs_code, year=y, quarter=q)
                data = _rs_to_df(rs)
                if not data.empty:
                    all_data.append(data)
            except Exception:
                pass
            q -= 1
            if q <= 0:
                q = 4
                y -= 1

        if not all_data:
            return f"No balance sheet data found for symbol '{ticker}'"

        combined = pd.concat(all_data, ignore_index=True)
        csv_string = combined.to_csv(index=False)

        header = f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        header += f"# Data source: BaoStock\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get cash flow data from BaoStock."""
    bs = _get_bs()
    bs_code = _convert_ticker(ticker)

    try:
        if curr_date:
            dt = pd.to_datetime(curr_date)
            year = dt.year
            quarter = (dt.month - 1) // 3
            if quarter == 0:
                year -= 1
                quarter = 4
        else:
            today = pd.Timestamp.today()
            year = today.year
            quarter = max(1, (today.month - 1) // 3)

        all_data = []
        limit = 4 if freq.lower() == "quarterly" else 3
        y, q = year, quarter
        for _ in range(limit):
            try:
                rs = bs.query_cash_flow_data(code=bs_code, year=y, quarter=q)
                data = _rs_to_df(rs)
                if not data.empty:
                    all_data.append(data)
            except Exception:
                pass
            q -= 1
            if q <= 0:
                q = 4
                y -= 1

        if not all_data:
            return f"No cash flow data found for symbol '{ticker}'"

        combined = pd.concat(all_data, ignore_index=True)
        csv_string = combined.to_csv(index=False)

        header = f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        header += f"# Data source: BaoStock\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get income statement data from BaoStock (via profit data)."""
    bs = _get_bs()
    bs_code = _convert_ticker(ticker)

    try:
        if curr_date:
            dt = pd.to_datetime(curr_date)
            year = dt.year
            quarter = (dt.month - 1) // 3
            if quarter == 0:
                year -= 1
                quarter = 4
        else:
            today = pd.Timestamp.today()
            year = today.year
            quarter = max(1, (today.month - 1) // 3)

        all_data = []
        limit = 4 if freq.lower() == "quarterly" else 3
        y, q = year, quarter
        for _ in range(limit):
            try:
                rs = bs.query_profit_data(code=bs_code, year=y, quarter=q)
                data = _rs_to_df(rs)
                if not data.empty:
                    all_data.append(data)
            except Exception:
                pass
            q -= 1
            if q <= 0:
                q = 4
                y -= 1

        if not all_data:
            return f"No income statement data found for symbol '{ticker}'"

        combined = pd.concat(all_data, ignore_index=True)
        csv_string = combined.to_csv(index=False)

        header = f"# Income Statement data for {ticker.upper()} ({freq})\n"
        header += f"# Data source: BaoStock\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

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
    """BaoStock does not provide news data."""
    raise BaoStockDataError("BaoStock does not support news data")


def get_global_news(
    curr_date: Annotated[str, "current date YYYY-MM-DD"],
    look_back_days: Annotated[int, "how many days to look back"] = 7,
    limit: Annotated[int, "max articles"] = 10,
) -> str:
    """BaoStock does not provide news data."""
    raise BaoStockDataError("BaoStock does not support global news data")


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    """BaoStock does not provide insider transaction data."""
    raise BaoStockDataError("BaoStock does not support insider transaction data")
