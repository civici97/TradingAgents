from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_language_instruction,
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_holder_count,
    get_top_holders,
    get_margin_data,
    get_share_unlock,
    get_fund_flow,
    get_lhb_data,
)
from tradingagents.dataflows.config import get_config


def _is_cn_stock(ticker: str) -> bool:
    return ticker.strip().upper().endswith((".SS", ".SH", ".SZ"))


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        # Base tools for all markets
        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
        )

        # Add A-share specific tools and instructions
        if _is_cn_stock(ticker):
            tools.extend([
                get_holder_count,
                get_top_holders,
                get_margin_data,
                get_share_unlock,
                get_fund_flow,
                get_lhb_data,
            ])
            system_message += (
                "\n\n## A-Share Specific Analysis (Chinese market tools available)"
                "\nFor this Chinese A-share stock, you have additional tools that provide critical A-share data:"
                "\n- `get_holder_count`: 股东人数变化 — chip concentration indicator. Decreasing holder count = bullish (chips concentrating in fewer hands)."
                "\n- `get_top_holders`: 十大股东 + 北向资金 — institutional ownership and foreign capital flows. Rising northbound holdings = foreign investors are bullish."
                "\n- `get_margin_data`: 融资融券 — margin trading balance. Rising margin = leveraged bullish sentiment."
                "\n- `get_share_unlock`: 限售解禁 — upcoming share unlocks create potential selling pressure."
                "\n- `get_fund_flow`: 个股资金流向 — main force (主力) net inflow/outflow. Positive main force flow = institutional buying."
                "\n- `get_lhb_data`: 龙虎榜 — dragon tiger board. Shows institutional/brokerage buying on unusual trading days."
                "\n\nUse ALL of these tools in addition to the standard fundamental tools. In your report, include a dedicated section for A-share specific signals:"
                "\n1. **筹码集中度 (Chip Concentration)**: Is the holder count increasing or decreasing? What does this mean?"
                "\n2. **机构/外资动向 (Institutional/Foreign Flows)**: Are northbound funds increasing their position?"
                "\n3. **融资融券 (Margin Sentiment)**: Is margin balance rising or falling? What's the leverage direction?"
                "\n4. **限售解禁 (Unlock Risk)**: Any major unlocks coming? What's the potential selling pressure?"
                "\n5. **资金流向 (Fund Flow)**: Is main force (主力) buying or selling? What's the institutional direction?"
                "\n6. **龙虎榜 (Dragon Tiger Board)**: Any recent LHB appearances? Which institutions are active?"
                "\n7. **政策/行业风险 (Policy/Industry Risk)**: Is this industry subject to regulatory risk in China?"
            )

        system_message += get_language_instruction()

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
