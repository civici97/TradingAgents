"""AKShare data provider for Chinese A-share stocks.

AKShare is a completely free, open-source financial data library that
aggregates data from multiple public sources (EastMoney, Sina, SSE, SZSE,
CCTV, etc.). No API key or registration is required.

Implements the same interface as tushare_provider.py / y_finance.py so it
can be registered as a vendor in interface.py.

Key advantages over Tushare:
- No rate limits
- No token/registration required
- Broader coverage (LHB, fund flow, macro data)
- Better news sources (per-stock EastMoney news, CCTV, CLS)
"""

import logging
import os
import time
from datetime import datetime
from typing import Annotated

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-imported AKShare handle
# ---------------------------------------------------------------------------
_ak = None


class AKShareDataError(Exception):
    """Raised when AKShare returns unexpected data or a network error."""


def _get_ak():
    """Return the akshare module (lazy import)."""
    global _ak
    if _ak is None:
        try:
            import akshare as ak
            _ak = ak
        except ImportError:
            raise ImportError(
                "akshare is not installed. Install it with: "
                "pip install 'tradingagents[akshare]'  or  pip install akshare"
            )
    return _ak


def _convert_ticker(symbol: str) -> str:
    """Convert yfinance/tushare-style ticker to AKShare format (pure digits).

    600989.SS  -> 600989
    600989.SH  -> 600989
    000001.SZ  -> 000001
    SH600989   -> 600989
    """
    symbol = symbol.strip().upper()

    # Xueqiu-style prefix
    if symbol.startswith(("SH", "SZ")) and len(symbol) > 2 and symbol[2:].isdigit():
        return symbol[2:]

    # Remove any suffix after dot
    base = symbol.split(".")[0]
    return base


def _get_market(symbol: str) -> str:
    """Determine the market (exchange) for a symbol.

    Returns 'sh' for Shanghai, 'sz' for Shenzhen.
    """
    symbol = symbol.strip().upper()
    if symbol.endswith((".SS", ".SH")):
        return "sh"
    if symbol.endswith(".SZ"):
        return "sz"

    base = symbol.split(".")[0]
    if base.startswith(("6", "9")):
        return "sh"
    return "sz"


def _date_to_ak(date_str: str) -> str:
    """Convert YYYY-MM-DD to YYYYMMDD for AKShare."""
    return date_str.replace("-", "")


# ============================================================================
# OHLCV Stock Price Data
# ============================================================================

def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Get OHLCV stock data from AKShare (EastMoney source)."""
    ak = _get_ak()
    code = _convert_ticker(symbol)

    try:
        data = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=_date_to_ak(start_date),
            end_date=_date_to_ak(end_date),
            adjust="qfq",  # 前复权
        )
    except Exception as e:
        raise AKShareDataError(f"AKShare stock data error for {symbol}: {e}")

    if data is None or data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    # Rename columns to match standard format
    col_map = {
        "日期": "Date",
        "开盘": "Open",
        "收盘": "Close",
        "最高": "High",
        "最低": "Low",
        "成交量": "Volume",
        "成交额": "Amount",
        "振幅": "Amplitude",
        "涨跌幅": "Change_Pct",
        "涨跌额": "Change_Amt",
        "换手率": "Turnover",
    }
    data = data.rename(columns=col_map)

    # Select standard columns
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
    header += f"# Data source: AKShare (EastMoney)\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


# ============================================================================
# Technical Indicators (uses stockstats on AKShare data)
# ============================================================================

def _load_ohlcv_akshare(symbol: str, curr_date: str) -> pd.DataFrame:
    """Load OHLCV data from AKShare with caching, for stockstats calculations."""
    from .config import get_config
    from .utils import safe_ticker_component
    from .stockstats_utils import _clean_dataframe

    safe_symbol = safe_ticker_component(symbol)
    config = get_config()
    ak = _get_ak()
    code = _convert_ticker(symbol)

    # Cache: 5 years of data
    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y%m%d")
    end_str = today_date.strftime("%Y%m%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{safe_symbol}-AKShare-data-{start_date.strftime('%Y-%m-%d')}-{today_date.strftime('%Y-%m-%d')}.csv",
    )

    if os.path.exists(data_file):
        data = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
    else:
        try:
            data = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_str,
                end_date=end_str,
                adjust="qfq",
            )
        except Exception as e:
            logger.error(f"AKShare OHLCV load error for {symbol}: {e}")
            return pd.DataFrame()

        if data is None or data.empty:
            return pd.DataFrame()

        # Rename to standard format
        col_map = {
            "日期": "Date",
            "开盘": "Open",
            "收盘": "Close",
            "最高": "High",
            "最低": "Low",
            "成交量": "Volume",
        }
        data = data.rename(columns=col_map)
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
    """Get technical indicators using AKShare data + stockstats."""
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
        data = _load_ohlcv_akshare(symbol, curr_date)
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
        logger.error(f"Error getting AKShare indicators: {e}")
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
    """Get company fundamentals from AKShare (EastMoney source)."""
    ak = _get_ak()
    code = _convert_ticker(ticker)

    try:
        lines = []
        lines.append(f"# Company Fundamentals for {ticker.upper()}")
        lines.append(f"# Data source: AKShare (EastMoney)")
        lines.append(f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Basic company info
        try:
            info = ak.stock_individual_info_em(symbol=code)
            if info is not None and not info.empty:
                lines.append("## Company Profile\n")
                for _, row in info.iterrows():
                    item = row.get("item", row.iloc[0] if len(row) > 0 else "")
                    value = row.get("value", row.iloc[1] if len(row) > 1 else "")
                    if pd.notna(value) and str(value).strip():
                        lines.append(f"{item}: {value}")
        except Exception as e:
            logger.warning(f"AKShare company info failed for {code}: {e}")

        # Valuation indicators (PE, PB, PS, etc.)
        try:
            indicator_data = ak.stock_a_indicator_lg(symbol=code)
            if indicator_data is not None and not indicator_data.empty:
                # Filter by curr_date if provided
                if curr_date:
                    indicator_data["trade_date"] = pd.to_datetime(indicator_data["trade_date"])
                    cutoff = pd.to_datetime(curr_date)
                    indicator_data = indicator_data[indicator_data["trade_date"] <= cutoff]

                if not indicator_data.empty:
                    latest = indicator_data.iloc[-1]
                    lines.append("\n## Valuation Indicators\n")
                    val_map = [
                        ("PE Ratio (TTM)", "pe_ttm"),
                        ("PE Ratio", "pe"),
                        ("PB Ratio", "pb"),
                        ("PS Ratio (TTM)", "ps_ttm"),
                        ("Dividend Yield (%)", "dv_ratio"),
                        ("Total Market Value (亿元)", "total_mv"),
                    ]
                    for label, col in val_map:
                        val = latest.get(col)
                        if pd.notna(val):
                            lines.append(f"{label}: {val}")
        except Exception as e:
            logger.warning(f"AKShare valuation indicators failed for {code}: {e}")

        return "\n".join(lines)

    except Exception as e:
        raise AKShareDataError(f"Error retrieving fundamentals for {ticker}: {str(e)}")


# ============================================================================
# Financial Statements
# ============================================================================

def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get balance sheet data from AKShare (EastMoney source)."""
    ak = _get_ak()
    code = _convert_ticker(ticker)

    try:
        data = ak.stock_balance_sheet_by_report_em(symbol=code)

        if data is None or data.empty:
            return f"No balance sheet data found for symbol '{ticker}'"

        # Filter by curr_date if provided
        if curr_date:
            date_col = "REPORT_DATE_NAME" if "REPORT_DATE_NAME" in data.columns else None
            if date_col is None:
                # Try to find a date column
                for col in data.columns:
                    if "date" in col.lower() or "日期" in col:
                        date_col = col
                        break
            if date_col:
                data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
                cutoff = pd.to_datetime(curr_date)
                data = data[data[date_col] <= cutoff]

        # Take latest reports
        limit = 4 if freq.lower() == "quarterly" else 3
        data = data.head(limit)

        csv_string = data.to_csv(index=False)

        header = f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        header += f"# Data source: AKShare (EastMoney)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        raise AKShareDataError(f"Error retrieving balance sheet for {ticker}: {str(e)}")


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get cash flow data from AKShare (EastMoney source)."""
    ak = _get_ak()
    code = _convert_ticker(ticker)

    try:
        data = ak.stock_cash_flow_sheet_by_report_em(symbol=code)

        if data is None or data.empty:
            return f"No cash flow data found for symbol '{ticker}'"

        if curr_date:
            date_col = None
            for col in data.columns:
                if "date" in col.lower() or "日期" in col:
                    date_col = col
                    break
            if date_col:
                data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
                cutoff = pd.to_datetime(curr_date)
                data = data[data[date_col] <= cutoff]

        limit = 4 if freq.lower() == "quarterly" else 3
        data = data.head(limit)

        csv_string = data.to_csv(index=False)

        header = f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        header += f"# Data source: AKShare (EastMoney)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        raise AKShareDataError(f"Error retrieving cash flow for {ticker}: {str(e)}")


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get income statement data from AKShare (EastMoney source)."""
    ak = _get_ak()
    code = _convert_ticker(ticker)

    try:
        data = ak.stock_profit_sheet_by_report_em(symbol=code)

        if data is None or data.empty:
            return f"No income statement data found for symbol '{ticker}'"

        if curr_date:
            date_col = None
            for col in data.columns:
                if "date" in col.lower() or "日期" in col:
                    date_col = col
                    break
            if date_col:
                data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
                cutoff = pd.to_datetime(curr_date)
                data = data[data[date_col] <= cutoff]

        limit = 4 if freq.lower() == "quarterly" else 3
        data = data.head(limit)

        csv_string = data.to_csv(index=False)

        header = f"# Income Statement data for {ticker.upper()} ({freq})\n"
        header += f"# Data source: AKShare (EastMoney)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        raise AKShareDataError(f"Error retrieving income statement for {ticker}: {str(e)}")


# ============================================================================
# News
# ============================================================================

def get_news(
    ticker: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "start date YYYY-MM-DD"],
    end_date: Annotated[str, "end date YYYY-MM-DD"],
) -> str:
    """Get per-stock news from AKShare (EastMoney source).

    EastMoney provides higher quality per-stock news than Tushare's Sina source.
    """
    ak = _get_ak()
    code = _convert_ticker(ticker)

    try:
        data = ak.stock_news_em(symbol=code)

        if data is None or data.empty:
            return f"No news found for '{ticker}' between {start_date} and {end_date}"

        # Filter by date range
        date_col = None
        for col in data.columns:
            if "时间" in col or "date" in col.lower() or "发布" in col:
                date_col = col
                break

        if date_col:
            data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            data = data[(data[date_col] >= start_dt) & (data[date_col] <= end_dt)]

        # Limit to 20 articles
        data = data.head(20)

        articles = []
        for _, row in data.iterrows():
            # Try common column names for title and content
            title = (
                row.get("新闻标题", "") or row.get("title", "") or
                row.get("标题", "") or "N/A"
            )
            content = (
                row.get("新闻内容", "") or row.get("content", "") or
                row.get("内容", "") or ""
            )
            pub_date = ""
            if date_col:
                pub_date = str(row.get(date_col, ""))
            elif "发布时间" in row.index:
                pub_date = str(row.get("发布时间", ""))

            if content and len(str(content)) > 500:
                content = str(content)[:500] + "..."
            articles.append(f"**{title}** ({pub_date})\n{content}\n")

        header = f"# News related to {ticker.upper()}\n"
        header += f"# Period: {start_date} to {end_date}\n"
        header += f"# Data source: AKShare (EastMoney)\n"
        header += f"# Total articles: {len(articles)}\n\n"

        return header + "\n---\n".join(articles)

    except Exception as e:
        raise AKShareDataError(f"No news available for {ticker}: {str(e)}")


def get_global_news(
    curr_date: Annotated[str, "current date YYYY-MM-DD"],
    look_back_days: Annotated[int, "how many days to look back"] = 7,
    limit: Annotated[int, "max articles"] = 10,
) -> str:
    """Get global/macro news from AKShare.

    Uses CLS (财联社电报) for high-quality financial news.
    Falls back to CCTV news if CLS is unavailable.
    """
    ak = _get_ak()
    from datetime import datetime as dt, timedelta

    if look_back_days is None:
        look_back_days = 7
    if limit is None:
        limit = 10

    start_dt = dt.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)

    articles = []

    # Try CLS financial telegraph (财联社电报) first
    try:
        data = ak.stock_zh_a_alerts_cls()
        if data is not None and not data.empty:
            # Filter by date range
            date_col = None
            for col in data.columns:
                if "时间" in col or "date" in col.lower():
                    date_col = col
                    break

            if date_col:
                data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
                end_dt = pd.to_datetime(curr_date)
                data = data[
                    (data[date_col] >= pd.to_datetime(start_dt)) &
                    (data[date_col] <= end_dt)
                ]

            data = data.head(limit)

            for _, row in data.iterrows():
                title = row.get("标题", "") or row.get("title", "") or "N/A"
                content = row.get("内容", "") or row.get("content", "") or ""
                pub_date = str(row.get(date_col, "")) if date_col else ""

                if content and len(str(content)) > 300:
                    content = str(content)[:300] + "..."
                articles.append(f"**{title}** ({pub_date})\n{content}\n")
    except Exception as e:
        logger.warning(f"AKShare CLS news failed: {e}")

    # Fallback: CCTV news
    if not articles:
        try:
            date_str = _date_to_ak(curr_date)
            data = ak.news_cctv(date=date_str)
            if data is not None and not data.empty:
                data = data.head(limit)
                for _, row in data.iterrows():
                    title = row.get("title", "") or "N/A"
                    content = row.get("content", "") or ""
                    pub_date = row.get("date", "") or ""
                    if content and len(str(content)) > 300:
                        content = str(content)[:300] + "..."
                    articles.append(f"**{title}** ({pub_date})\n{content}\n")
        except Exception as e:
            logger.warning(f"AKShare CCTV news failed: {e}")

    if not articles:
        return "No global news available from AKShare."

    header = f"# Global Financial News\n"
    header += f"# Period: {start_dt.strftime('%Y-%m-%d')} to {curr_date}\n"
    header += f"# Data source: AKShare (CLS/CCTV)\n\n"

    return header + "\n---\n".join(articles)


# ============================================================================
# Insider Transactions
# ============================================================================

def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Get insider/shareholder transactions from AKShare (EastMoney source)."""
    ak = _get_ak()
    code = _convert_ticker(ticker)

    try:
        # Shareholder increase/decrease analysis
        data = ak.stock_gdfx_free_holding_analyse_em(symbol=code)

        if data is None or data.empty:
            return f"No insider transactions data found for symbol '{ticker}'"

        # Take recent transactions
        data = data.head(20)

        csv_string = data.to_csv(index=False)

        header = f"# Insider/Shareholder Transactions for {ticker.upper()}\n"
        header += f"# Data source: AKShare (EastMoney)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        raise AKShareDataError(f"Error retrieving insider transactions for {ticker}: {str(e)}")


# ============================================================================
# A-Share Enhanced Data (unique to AKShare, not in vendor routing)
# ============================================================================

def get_fund_flow(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Get individual stock fund flow data (个股资金流向).

    Shows main force (主力), super-large (超大单), large (大单),
    medium (中单), small (小单) net inflows.
    """
    ak = _get_ak()
    code = _convert_ticker(ticker)
    market = _get_market(ticker)

    try:
        data = ak.stock_individual_fund_flow(stock=code, market=market)

        if data is None or data.empty:
            return f"No fund flow data found for '{ticker}'"

        # Take recent 10 days
        data = data.tail(10)

        lines = [f"# Fund Flow Data (个股资金流向) for {ticker.upper()}"]
        lines.append(f"# Data source: AKShare (EastMoney)")
        lines.append(f"# Main force net inflow > 0 = institutional buying = bullish\n")

        csv_string = data.to_csv(index=False)
        return "\n".join(lines) + "\n" + csv_string

    except Exception as e:
        return f"Fund flow data unavailable for {ticker}: {str(e)}"


def get_lhb_data(
    ticker: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "start date YYYY-MM-DD"] = None,
    end_date: Annotated[str, "end date YYYY-MM-DD"] = None,
) -> str:
    """Get Dragon Tiger Board data (龙虎榜).

    Shows which institutions and brokerages are buying/selling.
    Requires high Tushare points but is free in AKShare.
    """
    ak = _get_ak()
    code = _convert_ticker(ticker)

    try:
        # Get individual stock LHB detail
        data = ak.stock_lhb_stock_statistic_em(symbol="近一月")

        if data is None or data.empty:
            return f"No LHB data found for '{ticker}'"

        # Filter for this stock
        code_col = None
        for col in data.columns:
            if "代码" in col or "code" in col.lower():
                code_col = col
                break

        if code_col:
            data = data[data[code_col].astype(str) == code]

        if data.empty:
            return f"No LHB data found for '{ticker}' in recent period"

        csv_string = data.to_csv(index=False)

        header = f"# Dragon Tiger Board (龙虎榜) for {ticker.upper()}\n"
        header += f"# Data source: AKShare (EastMoney)\n"
        header += f"# LHB appearances indicate unusual trading activity\n\n"

        return header + csv_string

    except Exception as e:
        return f"LHB data unavailable for {ticker}: {str(e)}"


def get_macro_china(
    indicator: Annotated[str, "macro indicator: gdp, cpi, pmi, m2, shibor"] = "gdp",
) -> str:
    """Get Chinese macroeconomic data.

    Available indicators:
    - gdp: GDP growth rate
    - cpi: Consumer Price Index
    - pmi: Purchasing Managers Index
    - m2: Money supply M2
    - shibor: Shanghai Interbank Offered Rate
    """
    ak = _get_ak()

    try:
        indicator = indicator.lower().strip()
        data = None
        title = ""

        if indicator == "gdp":
            data = ak.macro_china_gdp()
            title = "GDP Growth Rate"
        elif indicator == "cpi":
            data = ak.macro_china_cpi_monthly()
            title = "CPI Monthly"
        elif indicator == "pmi":
            data = ak.macro_china_pmi()
            title = "PMI (Manufacturing)"
        elif indicator == "m2":
            data = ak.macro_china_money_supply()
            title = "Money Supply (M2)"
        elif indicator == "shibor":
            data = ak.rate_interbank(market="上海银行间同业拆放利率(Shibor)", symbol="隔夜", indicator="利率")
            title = "SHIBOR Overnight Rate"
        else:
            return f"Unknown macro indicator: {indicator}. Choose from: gdp, cpi, pmi, m2, shibor"

        if data is None or data.empty:
            return f"No macro data available for indicator '{indicator}'"

        # Take recent 12 data points
        data = data.tail(12)

        csv_string = data.to_csv(index=False)

        header = f"# China Macro Data: {title}\n"
        header += f"# Data source: AKShare\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Macro data unavailable for {indicator}: {str(e)}"
