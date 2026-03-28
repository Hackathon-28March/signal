"""
router.py — Routing decision node
Decides which actions to take based on classification + frequency + urgency.

Routing table (from CLAUDE.md):
  BUG urgency >= 7              → Jira P1,  Slack #engineering
  BUG urgency < 7               → Jira P2,  no Slack
  FEATURE_REQUEST freq >= 5     → Jira Story, Notion, Slack #product
  FEATURE_REQUEST freq < 5      → log to Senso only
  CHURN_RISK                    → Slack #cs-team immediately, digest
  PRAISE                        → Senso only, digest
  QUESTION                      → Senso only (no digest)

Frequency multiplier:
  3-4 signals → urgency +2
  5+ signals  → urgency +4
"""

from typing import List
from pydantic import BaseModel
import railtracks as rt


class RouterInput(BaseModel):
    classification: str
    urgency: int
    customer: str
    company: str
    text: str
    key_phrases: List[str]
    sentiment: str
    frequency: int   # from Senso memory search


class Action(BaseModel):
    type: str        # "jira" | "notion" | "slack" | "senso" | "digest"
    payload: dict


class RouterOutput(BaseModel):
    actions: List[Action]
    effective_urgency: int


def _frequency_boost(urgency: int, frequency: int) -> int:
    if frequency >= 5:
        return min(10, urgency + 4)
    if frequency >= 3:
        return min(10, urgency + 2)
    return urgency


@rt.function_node
async def decide_actions(input: RouterInput) -> RouterOutput:
    """
    Apply routing rules to produce an ordered list of actions.
    Returns actions list and the effective urgency after frequency boost.
    """
    eff_urgency = _frequency_boost(input.urgency, input.frequency)
    actions: List[Action] = []
    c = input.classification

    if c == "BUG":
        priority = "Highest" if eff_urgency >= 7 else "High"
        actions.append(Action(type="jira", payload={
            "summary": f"[Signal] Bug: {', '.join(input.key_phrases[:2])} — {input.company}",
            "description": (
                f"Customer: {input.customer} at {input.company}\n"
                f"Urgency: {eff_urgency}/10 (raw: {input.urgency}/10)\n"
                f"Frequency: {input.frequency} similar signals\n"
                f"Sentiment: {input.sentiment}\n\n"
                f"Full transcript:\n{input.text}"
            ),
            "priority": priority,
            "issue_type": "Task",
            "customer_quote": input.text[:300],
        }))
        if eff_urgency >= 7:
            actions.append(Action(type="slack", payload={
                "channel_hint": "#engineering",
            }))

    elif c == "FEATURE_REQUEST":
        if input.frequency >= 5:
            actions.append(Action(type="jira", payload={
                "summary": f"[Signal] Feature: {', '.join(input.key_phrases[:2])} — {input.company}",
                "description": (
                    f"Requested by {input.customer} at {input.company}\n"
                    f"Signal count: {input.frequency}\n"
                    f"Urgency: {eff_urgency}/10\n\n"
                    f"Full transcript:\n{input.text}"
                ),
                "priority": "High",
                "issue_type": "Task",
                "customer_quote": input.text[:300],
            }))
            actions.append(Action(type="notion", payload={
                "title": f"[Signal] {', '.join(input.key_phrases[:2])}",
                "description": (
                    f"Requested by {input.customer} at {input.company}.\n"
                    f"Signal count: {input.frequency}\n\n{input.text}"
                ),
                "priority": "P2 - High",
                "signal_count": input.frequency,
            }))
            actions.append(Action(type="slack", payload={
                "channel_hint": "#product",
            }))

    elif c == "CHURN_RISK":
        actions.append(Action(type="slack", payload={
            "channel_hint": "#cs-team",
        }))

    # Everything except QUESTION goes to digest
    if c != "QUESTION":
        actions.append(Action(type="digest", payload={}))

    # All signals go to Senso
    actions.append(Action(type="senso", payload={}))

    return RouterOutput(actions=actions, effective_urgency=eff_urgency)


def route(classification: str, urgency: int, frequency: int,
          customer: str, company: str, text: str,
          key_phrases: list, sentiment: str) -> RouterOutput:
    """Synchronous wrapper for use outside async context."""
    import asyncio
    return asyncio.run(decide_actions(RouterInput(
        classification=classification,
        urgency=urgency,
        customer=customer,
        company=company,
        text=text,
        key_phrases=key_phrases,
        sentiment=sentiment,
        frequency=frequency,
    )))
