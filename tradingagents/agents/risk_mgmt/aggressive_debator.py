from tradingagents.agents.utils.agent_utils import get_language_instruction


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        # Detect if this is a Chinese A-share stock
        ticker = state.get("company_of_interest", "")
        is_cn = ticker.strip().upper().endswith((".SS", ".SH", ".SZ"))

        cn_opportunity_addendum = ""
        if is_cn:
            cn_opportunity_addendum = """

IMPORTANT: This is a Chinese A-share stock. Leverage these A-share specific opportunities in your argument:
1. **T+1 creates contrarian opportunities**: When retail investors panic-sell the next day after bad news, it creates cheaper entry points. Sophisticated investors can accumulate during these forced-selling windows.
2. **Price limit rebounds (涨停/跌停反弹)**: After a stock hits limit down, it often rebounds the next day. Historical patterns show limit-down followed by recovery is a common A-share pattern.
3. **Policy-benefited sectors**: If this company is in a government-favored sector (新能源, 半导体, 高端制造), policy tailwinds can be extremely powerful in China.
4. **Northbound fund conviction (北向资金)**: If foreign institutional investors are increasing their position via northbound channels, this is a strong validation signal — they have done extensive due diligence.
5. **Margin balance as conviction signal (融资余额)**: Rising margin balance shows investors are willing to use leverage to bet on this stock — a sign of strong conviction.
6. **Chip concentration (筹码集中)**: If shareholder count is decreasing, it means smart money is accumulating while weak hands are leaving — classic bullish setup.
Use these A-share dynamics to strengthen your bullish case."""

        prompt = f"""As the Aggressive Risk Analyst, your role is to actively champion high-reward, high-risk opportunities, emphasizing bold strategies and competitive advantages. When evaluating the trader's decision or plan, focus intently on the potential upside, growth potential, and innovative benefits—even when these come with elevated risk. Use the provided market data and sentiment analysis to strengthen your arguments and challenge the opposing views. Specifically, respond directly to each point made by the conservative and neutral analysts, countering with data-driven rebuttals and persuasive reasoning. Highlight where their caution might miss critical opportunities or where their assumptions may be overly conservative. Here is the trader's decision:

{trader_decision}

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances to demonstrate why your high-reward perspective offers the best path forward. Incorporate insights from the following sources into your arguments:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here are the last arguments from the conservative analyst: {current_conservative_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.
{cn_opportunity_addendum}
Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of risk-taking to outpace market norms. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why a high-risk approach is optimal. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
