from tradingagents.agents.utils.agent_utils import get_language_instruction


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        # Detect if this is a Chinese A-share stock
        ticker = state.get("company_of_interest", "")
        is_cn = ticker.strip().upper().endswith((".SS", ".SH", ".SZ"))

        cn_balance_addendum = ""
        if is_cn:
            cn_balance_addendum = """

IMPORTANT: This is a Chinese A-share stock. Apply these A-share specific balancing considerations:
1. **T+1 demands disciplined position sizing**: Since you cannot sell same-day, initial position should be smaller than in T+0 markets. Suggest building positions in 2-3 tranches over multiple days.
2. **Entry timing matters more in A-shares**: Consider entering near the end of the trading session (14:30-14:50) to minimize overnight gap risk from T+1.
3. **Price limit as both risk and opportunity**: ±10% daily limits contain downside but also limit upside. In your risk/reward calculation, account for the fact that maximum daily loss is capped.
4. **Balance northbound/margin signals against unlock risk**: If fundamentals show northbound funds buying and margin rising, but a major unlock is approaching, these are conflicting signals — recommend partial position with an unlock-date risk trigger.
5. **Policy sensitivity assessment**: Evaluate whether this sector is policy-favored or policy-at-risk. Propose scenario analysis for both cases.
6. **Practical stop-loss in T+1 context**: Since intraday stops don't work, recommend a "next-day stop" — if the stock opens below a threshold the next trading day, sell in the opening auction.
Synthesize these A-share factors into a balanced, practical recommendation."""

        prompt = f"""As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. You prioritize a well-rounded approach, evaluating the upsides and downsides while factoring in broader market trends, potential economic shifts, and diversification strategies.Here is the trader's decision:

{trader_decision}

Your task is to challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious. Use insights from the following data sources to support a moderate, sustainable strategy to adjust the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the conservative analyst: {current_conservative_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.
{cn_balance_addendum}
Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Challenge each of their points to illustrate why a moderate risk strategy might offer the best of both worlds, providing growth potential while safeguarding against extreme volatility. Focus on debating rather than simply presenting data, aiming to show that a balanced view can lead to the most reliable outcomes. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
