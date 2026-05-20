"""Sentiment analyst — multi-source sentiment analysis for a target ticker.

Previously named ``social_media_analyst``. Renamed and redesigned because
the old version had a prompt that demanded social-media analysis but the
only tool available was Yahoo Finance news — which led LLMs to fabricate
Reddit/X/StockTwits content under prompt pressure (verified live).

The redesigned agent pre-fetches three complementary data sources before
the LLM is invoked and injects them into the prompt as structured blocks:

  For US/international stocks:
    1. News headlines     — Yahoo Finance (institutional framing)
    2. StockTwits messages — retail-trader posts indexed by cashtag
    3. Reddit posts        — r/wallstreetbets, r/stocks, r/investing

  For Chinese A-share stocks:
    1. News headlines     — Tushare / Yahoo Finance
    2. 雪球 (Xueqiu)      — China's StockTwits, investor social platform
    3. 东方财富股吧 (East Money Guba) — China's Reddit for stocks

See: https://github.com/TauricResearch/TradingAgents/issues/557
"""

from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news,
)
from tradingagents.dataflows.reddit import fetch_reddit_posts
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages
from tradingagents.dataflows.xueqiu import fetch_xueqiu_posts
from tradingagents.dataflows.eastmoney import fetch_eastmoney_posts


_CN_SUFFIXES = (".SS", ".SH", ".SZ")


def _is_cn_stock(ticker: str) -> bool:
    """Detect if a ticker is a Chinese A-share stock."""
    t = ticker.strip().upper()
    return t.endswith(_CN_SUFFIXES)


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    Pre-fetches news + social media data, injects them into the prompt
    as structured blocks, and produces a sentiment report in a single
    LLM call.  Automatically selects Chinese or US social platforms
    based on ticker suffix.
    """

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = build_instrument_context(ticker)

        # Pre-fetch all sources. Each fetcher degrades gracefully.
        news_block = get_news.func(ticker, start_date, end_date)

        if _is_cn_stock(ticker):
            # Chinese A-share: use 雪球 + 东方财富股吧
            social_block_1 = fetch_xueqiu_posts(ticker, limit=20)
            social_block_2 = fetch_eastmoney_posts(ticker, limit=20)
            system_message = _build_cn_system_message(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                news_block=news_block,
                xueqiu_block=social_block_1,
                eastmoney_block=social_block_2,
            )
        else:
            # US/international: use StockTwits + Reddit
            stocktwits_block = fetch_stocktwits_messages(ticker, limit=30)
            reddit_block = fetch_reddit_posts(ticker)
            system_message = _build_system_message(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                news_block=news_block,
                stocktwits_block=stocktwits_block,
                reddit_block=reddit_block,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        # No bind_tools — the data is already in the prompt; a single LLM
        # call produces the report directly.
        chain = prompt | llm
        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "sentiment_report": result.content,
        }

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
) -> str:
    """Assemble the sentiment-analyst system message with structured data blocks."""
    return f"""You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}, drawing on three complementary data sources that have already been collected for you.

## Data sources (pre-fetched, in this prompt)

### News headlines — Yahoo Finance, past 7 days
Institutional framing. Fact-driven, slower-moving signal.

<start_of_news>
{news_block}
<end_of_news>

### StockTwits messages — retail-trader social platform indexed by cashtag
Fast-moving signal. Each message carries a user-labeled sentiment tag (Bullish / Bearish / no-label) plus the message body.

<start_of_stocktwits>
{stocktwits_block}
<end_of_stocktwits>

### Reddit posts — r/wallstreetbets, r/stocks, r/investing (past 7 days)
Community discussion. Engagement signal via upvote score and comment count. Subreddit character matters (r/wallstreetbets is often contrarian/exuberant; r/stocks more measured; r/investing longer-term).

<start_of_reddit>
{reddit_block}
<end_of_reddit>

## How to analyze this data (best practices)

1. **Read the StockTwits Bullish/Bearish ratio as a leading retail-sentiment signal.** A 70/30 bullish/bearish split is moderately bullish; ≥90/10 may indicate over-extension and contrarian risk; 50/50 is uncertainty. Sample size matters — base rates on the actual message count, not percentages alone.

2. **Look for cross-source divergences.** If news framing is bearish but StockTwits is overwhelmingly bullish, that mismatch is itself a signal — it can mean retail is leaning into a thesis the news flow hasn't caught up to (or vice versa, that retail is chasing while institutions are cautious).

3. **Weight Reddit posts by engagement.** A 400-upvote / 200-comment thread reflects community attention; a 3-upvote post is noise. Read the body excerpts for context — the title alone often misleads.

4. **Distinguish opinion from event.** A news headline ("Nvidia announces $500M Corning deal") is an event; a StockTwits post ("buying NVDA, this is going to moon") is opinion. Both are inputs but should be weighted differently in your conclusions.

5. **Identify recurring narrative themes.** What topic keeps coming up across sources? That's the dominant narrative driving current sentiment.

6. **Be honest about data limits.** If StockTwits returned only a handful of messages, or one or more sources returned an "<unavailable>" placeholder, the sentiment read is less robust — flag this caveat explicitly. If the sources are silent on a given subreddit, say so.

7. **Identify catalysts and risks** that emerge across sources — news of upcoming earnings, product launches, competitive threats, macro headlines, etc.

8. **Past sentiment is not predictive.** Frame your conclusions as signal for the trader to weigh alongside fundamentals and technicals, not as a price call.

## Output

Produce a sentiment report covering, in order:

1. **Overall sentiment direction** — Bullish / Bearish / Neutral / Mixed — with a brief confidence note based on data quality and sample size.
2. **Source-by-source breakdown** — what each of news / StockTwits / Reddit is telling you, with specific evidence (cite message counts, ratios, notable posts).
3. **Divergences, alignments, and key narratives** across sources.
4. **Catalysts and risks** surfaced by the data.
5. **Markdown table** at the end summarizing key sentiment signals, their direction, source, and supporting evidence.

{get_language_instruction()}"""


def _build_cn_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    xueqiu_block: str,
    eastmoney_block: str,
) -> str:
    """Assemble the sentiment-analyst system message for Chinese A-share stocks."""
    return f"""You are a financial market sentiment analyst specializing in Chinese A-share stocks. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}, drawing on three complementary data sources that have already been collected for you.

## Data sources (pre-fetched, in this prompt)

### 新闻 (News) — past 7 days
Institutional framing. Fact-driven, slower-moving signal. Typically the most reliable source for fundamental events (earnings, policy, sector trends).

<start_of_news>
{news_block}
<end_of_news>

### 雪球 (Xueqiu/Snowball) — China's leading investor social platform
Xueqiu is a relatively high-quality investor community — users include professional fund managers, sell-side analysts, and experienced retail investors. Sentiment from Xueqiu tends to be more considered and analytical. Treat this as a **direct sentiment signal** (similar to StockTwits for US stocks). Each post includes engagement metrics (likes, replies).

<start_of_xueqiu>
{xueqiu_block}
<end_of_xueqiu>

### 东方财富股吧 (East Money Guba) — ⚠️ CONTRARIAN INDICATOR
**CRITICAL**: 东方财富股吧 is China's largest stock discussion forum, dominated by unsophisticated retail investors (散户). Post quality is very low — emotional, reactive, and herd-driven. In A-share investing, "股吧看反" (read Guba in reverse) is a well-known heuristic:

- When 股吧 is **extremely bearish** (>70% 看空, posts like "割肉", "垃圾", "跑路") → Often signals a **contrarian BUY** / potential bottom
- When 股吧 is **extremely bullish** (>70% 看多, posts like "翻倍", "起飞", "冲") → Often signals a **contrarian SELL** / potential top
- When sentiment is **mixed or neutral** → No strong contrarian signal; sentiment is unreliable

The value of 股吧 is NOT in what it says, but in the **extremity of its emotion** as a crowd-psychology indicator.

<start_of_eastmoney>
{eastmoney_block}
<end_of_eastmoney>

## How to analyze this data (best practices)

1. **News is ground truth.** Start with news headlines to understand the factual backdrop — earnings, policy changes, sector developments, macro events. This is the most reliable source.

2. **雪球 provides nuanced sentiment.** If 雪球 data is available, treat it as a relatively thoughtful consensus read. Look for specific arguments, catalysts cited, and engagement patterns. High-engagement bearish posts from experienced users are a stronger signal than raw counts.

3. **东方财富股吧 is a CONTRARIAN indicator — invert it.** Do NOT take 股吧 sentiment at face value. Instead:
   - If >70% of 股吧 posts are bearish/panicking → Flag this as a **potential bottom signal** (retail capitulation)
   - If >70% of 股吧 posts are euphoric/bullish → Flag this as a **potential top signal** (retail FOMO)
   - If sentiment is mixed → 股吧 provides no useful signal; disregard it
   - Look for **extreme emotional language** (割肉/套牢/垃圾 = capitulation; 翻倍/起飞/冲 = euphoria) as the strongest contrarian signals

4. **Cross-reference contrarian signals with news.** The most powerful signal is when 股吧 shows extreme bearishness BUT news shows positive catalysts (or vice versa). This divergence is highly actionable.

5. **Identify catalysts and risks** — policy changes (产业政策), earnings reports, sector rotation, macro headlines (降息/降准), northbound fund flows (北向资金).

6. **Consider A-share market characteristics** — 涨停/跌停 (price limits), 主力/游资 (institutional vs hot money) dynamics, 融资融券 (margin trading) sentiment.

7. **Be honest about data limits.** If one or more sources returned an "<unavailable>" placeholder, clearly state which sources are missing and how that affects confidence.

## Output

Produce a sentiment report covering, in order:

1. **Overall sentiment direction** — 看多/Bullish / 看空/Bearish / 中性/Neutral / 分歧/Mixed — with a confidence level and explanation.
2. **News analysis** — key events, institutional framing, fundamental drivers.
3. **雪球 sentiment** (if available) — investor consensus, key arguments, notable opinions.
4. **东方财富股吧 contrarian read** — describe the raw sentiment, then explain what it means as a contrarian indicator. Explicitly state whether the crowd's emotional state suggests a contrarian opportunity or not.
5. **Divergences and cross-source synthesis** — where do the sources agree? Where do they disagree? Which divergences are most actionable?
6. **Catalysts, risks, and key narratives**.
7. **Markdown table** summarizing: Signal | Direction | Source | Contrarian? | Evidence.

{get_language_instruction()}"""


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
def create_social_media_analyst(llm):
    """Deprecated alias for :func:`create_sentiment_analyst`.

    Kept so existing code that imports ``create_social_media_analyst``
    continues to work.

    .. deprecated::
        Import :func:`create_sentiment_analyst` directly instead.
    """
    import warnings
    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)

