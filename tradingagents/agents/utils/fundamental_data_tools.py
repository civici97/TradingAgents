from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing comprehensive fundamental data
    """
    return route_to_vendor("get_fundamentals", ticker, curr_date)


@tool
def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve balance sheet data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing balance sheet data
    """
    return route_to_vendor("get_balance_sheet", ticker, freq, curr_date)


@tool
def get_cashflow(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve cash flow statement data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing cash flow statement data
    """
    return route_to_vendor("get_cashflow", ticker, freq, curr_date)


@tool
def get_income_statement(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve income statement data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing income statement data
    """
    return route_to_vendor("get_income_statement", ticker, freq, curr_date)


# ============================================================================
# A-Share Specific Tools (Tushare only, no vendor routing)
# ============================================================================

@tool
def get_holder_count(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Get shareholder count trends (股东人数变化) for Chinese A-share stocks.
    A decreasing holder count indicates chip concentration (筹码集中), typically bullish.
    An increasing holder count indicates chip dispersion, typically bearish.
    Only works for A-share stocks (.SS/.SH/.SZ tickers).
    """
    from tradingagents.dataflows.tushare_provider import get_holder_count as _get
    return _get(ticker)


@tool
def get_top_holders(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Get top 10 shareholders and northbound fund holdings (十大股东 + 北向资金).
    Shows institutional ownership, major shareholder changes, and foreign capital flows.
    Only works for A-share stocks (.SS/.SH/.SZ tickers).
    """
    from tradingagents.dataflows.tushare_provider import get_top_holders as _get
    return _get(ticker)


@tool
def get_margin_data(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Get margin trading data (融资融券) for Chinese A-share stocks.
    Rising margin balance indicates leveraged bullish sentiment.
    Falling margin balance indicates deleveraging or bearish sentiment.
    Only works for A-share stocks (.SS/.SH/.SZ tickers).
    """
    from tradingagents.dataflows.tushare_provider import get_margin_data as _get
    return _get(ticker)


@tool
def get_share_unlock(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Get share unlock schedule (限售解禁) for Chinese A-share stocks.
    Upcoming large unlock events create potential selling pressure.
    Only works for A-share stocks (.SS/.SH/.SZ tickers).
    """
    from tradingagents.dataflows.tushare_provider import get_share_unlock as _get
    return _get(ticker)


# ============================================================================
# AKShare-powered A-Share Enhanced Tools (free, no credentials needed)
# ============================================================================

@tool
def get_fund_flow(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Get individual stock fund flow data (个股资金流向) from AKShare.
    Shows main force (主力), large (大单), medium (中单), small (小单) net inflows.
    Main force net inflow > 0 indicates institutional buying = typically bullish.
    Main force net outflow indicates institutional selling = typically bearish.
    Only works for A-share stocks (.SS/.SH/.SZ tickers).
    """
    from tradingagents.dataflows.akshare_provider import get_fund_flow as _get
    return _get(ticker)


@tool
def get_lhb_data(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Get Dragon Tiger Board data (龙虎榜) from AKShare.
    Shows which institutions and brokerages are buying/selling on unusual trading days.
    LHB appearances indicate significant unusual trading activity and institutional interest.
    Only works for A-share stocks (.SS/.SH/.SZ tickers).
    """
    from tradingagents.dataflows.akshare_provider import get_lhb_data as _get
    return _get(ticker)


@tool
def get_macro_china(
    indicator: Annotated[str, "macro indicator: gdp, cpi, pmi, m2, shibor"] = "gdp",
) -> str:
    """
    Get Chinese macroeconomic data from AKShare.
    Available indicators:
    - gdp: GDP growth rate
    - cpi: Consumer Price Index (monthly)
    - pmi: Purchasing Managers Index (manufacturing)
    - m2: Money supply M2
    - shibor: Shanghai Interbank Offered Rate (overnight)
    Use this to understand the macro environment for Chinese stock analysis.
    """
    from tradingagents.dataflows.akshare_provider import get_macro_china as _get
    return _get(indicator)