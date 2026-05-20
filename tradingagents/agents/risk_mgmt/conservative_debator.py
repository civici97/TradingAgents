from tradingagents.agents.utils.agent_utils import get_language_instruction


def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        # Detect if this is a Chinese A-share stock
        ticker = state.get("company_of_interest", "")
        is_cn = ticker.strip().upper().endswith((".SS", ".SH", ".SZ"))

        cn_risk_addendum = ""
        if is_cn:
            cn_risk_addendum = """

IMPORTANT: This is a Chinese A-share stock. You MUST evaluate these A-share specific risks:
1. **T+1 Liquidity Risk**: Shares bought today CANNOT be sold until tomorrow. If the stock drops sharply after purchase, the investor is trapped for at least one trading day. Factor this into position sizing and entry timing.
2. **Price Limit Lock-in Risk**: With ±10% daily limits, if a stock hits 跌停 (limit down), sellers cannot exit even if they want to. Multiple consecutive limit-downs can trap investors for days.
3. **Policy/Regulatory Risk**: Chinese regulators can abruptly change industry policies (precedents: education/tutoring 2021, gaming, real estate). Is this company in a policy-sensitive sector?
4. **Major Shareholder Pledge Risk (大股东质押)**: If major shareholders have pledged a high percentage of their shares, a price decline could trigger forced liquidation, creating a death spiral.
5. **Share Unlock Selling Pressure (限售解禁)**: Check if large blocks of restricted shares are about to unlock. This creates significant supply pressure.
6. **Northbound Capital Flight (北向资金外流)**: If northbound funds are reducing their position, this is a bearish signal from sophisticated foreign institutional investors.
7. **Margin Deleveraging Risk (融资盘风险)**: If margin balance is high and the stock starts declining, forced margin calls can accelerate the selloff.
Assess EACH of these risks explicitly in your analysis."""

        prompt = f"""As the Conservative Risk Analyst, your primary objective is to protect assets, minimize volatility, and ensure steady, reliable growth. You prioritize stability, security, and risk mitigation, carefully assessing potential losses, economic downturns, and market volatility. When evaluating the trader's decision or plan, critically examine high-risk elements, pointing out where the decision may expose the firm to undue risk and where more cautious alternatives could secure long-term gains. Here is the trader's decision:

{trader_decision}

Your task is to actively counter the arguments of the Aggressive and Neutral Analysts, highlighting where their views may overlook potential threats or fail to prioritize sustainability. Respond directly to their points, drawing from the following data sources to build a convincing case for a low-risk approach adjustment to the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.
{cn_risk_addendum}
Engage by questioning their optimism and emphasizing the potential downsides they may have overlooked. Address each of their counterpoints to showcase why a conservative stance is ultimately the safest path for the firm's assets. Focus on debating and critiquing their arguments to demonstrate the strength of a low-risk strategy over their approaches. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction()

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
