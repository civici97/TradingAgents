"""雪球 (Xueqiu/Snowball) stock discussion fetcher.

Xueqiu is the leading Chinese stock social platform, equivalent to
StockTwits for the Chinese A-share market.

NOTE: Xueqiu uses Aliyun WAF which blocks most programmatic access.
This module attempts to fetch data but degrades gracefully if blocked.
When Xueqiu is unavailable, the sentiment analyst still has 东方财富股吧
data as a complementary source.

Returns formatted plaintext blocks ready for prompt injection.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def _to_xueqiu_symbol(ticker: str) -> str:
    """Convert yfinance/tushare ticker to Xueqiu symbol format.

    600989.SS  -> SH600989
    600989.SH  -> SH600989
    000001.SZ  -> SZ000001
    """
    ticker = ticker.strip().upper()
    if ticker.endswith((".SS", ".SH")):
        base = ticker.split(".")[0]
        return f"SH{base}"
    if ticker.endswith(".SZ"):
        base = ticker.split(".")[0]
        return f"SZ{base}"
    base = ticker.split(".")[0]
    if base.isdigit():
        if base.startswith(("6", "9")):
            return f"SH{base}"
        else:
            return f"SZ{base}"
    return ticker


def fetch_xueqiu_posts(
    ticker: str,
    limit: int = 20,
    timeout: float = 10.0,
) -> str:
    """Fetch recent Xueqiu discussion posts for a stock.

    Tries to scrape the stock page HTML. If blocked by WAF, returns a
    graceful placeholder so the LLM can still work with other sources.
    """
    symbol = _to_xueqiu_symbol(ticker)

    try:
        # Use requests for cookie-based session if available
        import requests
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})

        # Visit home to get cookies
        session.get("https://xueqiu.com/", timeout=timeout)

        # Fetch the stock page
        resp = session.get(
            f"https://xueqiu.com/S/{symbol}",
            headers={"Referer": "https://xueqiu.com/"},
            timeout=timeout,
        )

        if resp.status_code != 200:
            return f"<xueqiu unavailable: HTTP {resp.status_code}>"

        html = resp.text

        # Try to extract discussion data from the rendered HTML
        # Xueqiu embeds some data in script tags or renderData
        posts = []

        # Pattern 1: Look for timeline data in rendered HTML
        # The stock page sometimes includes post data in JSON script blocks
        json_matches = re.findall(
            r'"text"\s*:\s*"([^"]{10,300})"',
            html,
        )

        if json_matches:
            for text in json_matches[:limit]:
                # Unescape JSON string
                try:
                    text = text.encode().decode("unicode_escape", errors="replace")
                except Exception:
                    pass
                text = re.sub(r"<[^>]+>", "", text).strip()
                if text and len(text) > 5:
                    posts.append(text)

        # Pattern 2: Look for discussion titles
        if not posts:
            title_matches = re.findall(
                r'class="AnonymousHome_home__topic__title[^"]*"[^>]*>([^<]+)<',
                html,
            )
            posts.extend(t.strip() for t in title_matches if t.strip())

        if not posts:
            return f"<xueqiu unavailable: WAF protection blocked data extraction for {symbol}>"

        # Sentiment analysis
        lines = []
        bullish = bearish = neutral = 0

        for text in posts[:limit]:
            if any(kw in text for kw in (
                "看多", "看涨", "买入", "利好", "牛", "加仓", "突破",
                "上涨", "翻倍", "起飞", "大涨", "抄底", "机会", "低估",
            )):
                bullish += 1
                tag = "看多/Bullish"
            elif any(kw in text for kw in (
                "看空", "看跌", "卖出", "利空", "熊", "减仓", "下跌",
                "崩", "割肉", "高估", "套牢", "暴跌", "跑路", "危险",
                "烂", "阴跌",
            )):
                bearish += 1
                tag = "看空/Bearish"
            else:
                neutral += 1
                tag = "中性/Neutral"

            if len(text) > 200:
                text = text[:200] + "…"
            lines.append(f"[{tag}] {text}")

        total = bullish + bearish + neutral
        bull_pct = round(100 * bullish / total) if total else 0
        bear_pct = round(100 * bearish / total) if total else 0
        summary = (
            f"雪球 Xueqiu — {symbol} — {total} recent posts\n"
            f"看多/Bullish: {bullish} ({bull_pct}%) · "
            f"看空/Bearish: {bearish} ({bear_pct}%) · "
            f"中性/Neutral: {neutral}"
        )
        return summary + "\n\n" + "\n".join(lines)

    except Exception as exc:
        logger.warning("Xueqiu fetch failed for %s: %s", ticker, exc)
        return f"<xueqiu unavailable: {type(exc).__name__}: {exc}>"
