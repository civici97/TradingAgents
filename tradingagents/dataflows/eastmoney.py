"""东方财富股吧 (East Money Guba) discussion fetcher.

东方财富股吧 is the largest Chinese stock discussion forum, similar to
Reddit's r/wallstreetbets but organized per-stock.  Every listed stock
has its own "股吧" (stock bar) where retail investors post opinions,
analysis, and react to market events.

The fetcher scrapes the public HTML pages which require no authentication.
Returns formatted plaintext blocks ready for prompt injection.
"""

from __future__ import annotations

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

# East Money Guba HTML list page
_LIST_URL = "https://guba.eastmoney.com/list,{code}.html"


def _to_eastmoney_code(ticker: str) -> str:
    """Convert yfinance/tushare ticker to East Money stock code.

    600989.SS  -> 600989
    600989.SH  -> 600989
    000001.SZ  -> 000001
    SH600989   -> 600989
    """
    ticker = ticker.strip().upper()

    # Remove Xueqiu-style prefix
    if ticker.startswith(("SH", "SZ")) and len(ticker) > 2:
        return ticker[2:]

    # Remove suffix
    base = ticker.split(".")[0]
    return base


def _scrape_guba_html(code: str, timeout: float = 10.0) -> list[dict]:
    """Scrape the Guba HTML list page for recent post titles."""
    url = _LIST_URL.format(code=code)
    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.warning("东方财富股吧 fetch failed for %s: %s", code, exc)
        return []

    posts = []

    # Primary pattern: extract titles from class="title" elements
    title_matches = re.findall(
        r'class="title"[^>]*>.*?<a[^>]*>([^<]+)</a>',
        html,
        re.DOTALL,
    )

    if title_matches:
        for title in title_matches:
            title = title.strip()
            if title and len(title) > 2:
                posts.append({"title": title})
    else:
        # Fallback: try news link pattern
        fallback_matches = re.findall(
            r'<a[^>]*href="/news[^"]*"[^>]*>([^<]{5,})</a>',
            html,
        )
        for title in fallback_matches:
            title = title.strip()
            if title and len(title) > 2:
                posts.append({"title": title})

    return posts


def fetch_eastmoney_posts(
    ticker: str,
    limit: int = 20,
    timeout: float = 10.0,
) -> str:
    """Fetch recent 东方财富股吧 posts for a stock.

    Returns a formatted plaintext block ready for prompt injection.
    """
    code = _to_eastmoney_code(ticker)

    posts = _scrape_guba_html(code, timeout)

    if not posts:
        return f"<东方财富股吧 unavailable or no posts found for {code}>"

    lines = []
    bullish = bearish = neutral = 0

    for post in posts[:limit]:
        title = post.get("title", "")

        # Simple sentiment heuristic based on Chinese keywords
        if any(kw in title for kw in (
            "看多", "看涨", "买入", "利好", "牛", "加仓", "突破",
            "上涨", "翻倍", "起飞", "大涨", "抄底", "机会", "低估",
            "拉升", "涨停", "反弹", "新高",
        )):
            bullish += 1
            tag = "看多/Bullish"
        elif any(kw in title for kw in (
            "看空", "看跌", "卖出", "利空", "熊", "减仓", "下跌",
            "崩", "割肉", "高估", "套牢", "暴跌", "跑路", "危险",
            "烂", "阴跌", "跌停", "垃圾",
        )):
            bearish += 1
            tag = "看空/Bearish"
        else:
            neutral += 1
            tag = "中性/Neutral"

        lines.append(f"[{tag}] {title}")

    total = bullish + bearish + neutral
    bull_pct = round(100 * bullish / total) if total else 0
    bear_pct = round(100 * bearish / total) if total else 0
    summary = (
        f"东方财富股吧 East Money Guba — {code} — {total} recent posts\n"
        f"看多/Bullish: {bullish} ({bull_pct}%) · "
        f"看空/Bearish: {bearish} ({bear_pct}%) · "
        f"中性/Neutral: {neutral}"
    )
    return summary + "\n\n" + "\n".join(lines)
