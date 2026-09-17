"""Constrained intent routing for Atlas Fresh Planning Assistant.

Matches questions strictly to one of the three approved intents, or rejects them.
No autonomous tool-calling or arbitrary function execution is allowed.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple


INTENT_CLIENTS_AT_RISK = "clients_at_risk"
INTENT_FARM_SEGMENT_GAPS = "farm_segment_gaps"
INTENT_LOCAL_RESIDUAL_VALUE = "local_residual_value"

APPROVED_INTENTS = {
    INTENT_CLIENTS_AT_RISK,
    INTENT_FARM_SEGMENT_GAPS,
    INTENT_LOCAL_RESIDUAL_VALUE,
}

TOOL_MAP = {
    INTENT_CLIENTS_AT_RISK: "get_clients_at_risk",
    INTENT_FARM_SEGMENT_GAPS: "get_farm_segment_gaps",
    INTENT_LOCAL_RESIDUAL_VALUE: "get_local_residual_value",
}

# Patterns indicating clear out-of-scope requests or action attempts
REJECT_PATTERNS = [
    r"\bwrite\s+(?:python|code|script|poem|story|essay)\b",
    r"\bpython\b",
    r"\bweather\b",
    r"\bdelete\b",
    r"\bdrop\b",
    r"\bupdate\b",
    r"\bmodify\b",
    r"\bchange\b",
    r"\boptimize\b",
    r"\bcalculate\s+a?\s*new\b",
    r"\brecalculate\b",
    r"\bwhat\s+should\s+i\s+do\s+tomorrow\b",
    r"\bwho\s+are\s+you\b",
    r"\bjoke\b",
]

# Client risk patterns
CLIENT_RISK_PATTERNS = [
    r"\bclient(?:s)?\s+at\s+risk\b",
    r"\bpartially\s+served\b",
    r"\bnot\s+fully\s+served\b",
    r"\bwho\s+is\s+shorted\b",
    r"\bwhich\s+customers?\b",
    r"\bwhich\s+clients?\b",
    r"\bcustomers?\s+have\s+shortages\b",
    r"\bwhy\s+is\s+c0?\d+\s+(?:at\s+risk|short|shorted|unserved)\b",
    r"\bclient\s+risk\b",
    r"\bclients?\b",
    r"\bcustomers?\b",
]

# Farm / segment gaps patterns
FARM_SEGMENT_PATTERNS = [
    r"\bfarm(?:s)?\b",
    r"\bsegment(?:s)?\b",
    r"\bgap(?:s)?\b",
    r"\bproduction\s+gap(?:s)?\b",
    r"\bsupply\s+gap(?:s)?\b",
    r"\bfarms?\s+(?:are\s+)?short\b",
    r"\bproduction\s+shortfall(?:s)?\b",
    r"\bbiggest\s+production\b",
    r"\bbiggest\s+supply\b",
    r"\bmatter\s+most\b",
    r"\bproduction\s+signal\b",
    r"\bshortages?\s+matter\b",
]

# Local residual patterns
LOCAL_RESIDUAL_PATTERNS = [
    r"\blocal\b",
    r"\bresidual\b",
    r"\bgoing\s+local\b",
    r"\blocal\s+market\b",
    r"\blocal\s+value\b",
    r"\blocal\s+tonnes?\b",
    r"\bwhy\s+didn'?t\s+all\b",
    r"\bnot\s+all\s+(?:the\s+)?apples\b",
    r"\bwhy\s+are\s+\d+\s*t\s+going\s+local\b",
    r"\bestimated\s+value\s+of\s+(?:the\s+)?local\b",
]


def route_intent(question: str) -> Optional[Tuple[str, str]]:
    """Determine the single approved intent and tool for the question.
    
    Returns (intent, tool_name) if supported, or None if question is out-of-scope.
    """
    if not question or not isinstance(question, str):
        return None

    cleaned = question.strip().lower()
    if not cleaned:
        return None

    # Check for immediate rejection patterns
    for pattern in REJECT_PATTERNS:
        if re.search(pattern, cleaned):
            return None

    # Check for exact matches to suggested canonical questions
    if "clients are at risk" in cleaned or "who is shorted" in cleaned or "customers have shortages" in cleaned:
        return INTENT_CLIENTS_AT_RISK, TOOL_MAP[INTENT_CLIENTS_AT_RISK]

    if "farm/segment" in cleaned or "farm gaps" in cleaned or "farms are short" in cleaned or "production gaps" in cleaned:
        return INTENT_FARM_SEGMENT_GAPS, TOOL_MAP[INTENT_FARM_SEGMENT_GAPS]

    if "going local" in cleaned or "local residual" in cleaned or "local market" in cleaned or ("estimated value" in cleaned and "local" in cleaned):
        return INTENT_LOCAL_RESIDUAL_VALUE, TOOL_MAP[INTENT_LOCAL_RESIDUAL_VALUE]

    # Score matches across the three intents
    scores = {
        INTENT_CLIENTS_AT_RISK: 0,
        INTENT_FARM_SEGMENT_GAPS: 0,
        INTENT_LOCAL_RESIDUAL_VALUE: 0,
    }

    # High-signal primary topic keywords
    if re.search(r"\b(?:client|clients|customer|customers)\b", cleaned):
        scores[INTENT_CLIENTS_AT_RISK] += 3
    if re.search(r"\b(?:farm|farms|segment|segments)\b", cleaned):
        scores[INTENT_FARM_SEGMENT_GAPS] += 3
    if re.search(r"\b(?:local|residual|exported|station)\b", cleaned):
        scores[INTENT_LOCAL_RESIDUAL_VALUE] += 3

    for pattern in CLIENT_RISK_PATTERNS:
        if re.search(pattern, cleaned):
            scores[INTENT_CLIENTS_AT_RISK] += 1

    for pattern in FARM_SEGMENT_PATTERNS:
        if re.search(pattern, cleaned):
            scores[INTENT_FARM_SEGMENT_GAPS] += 1

    for pattern in LOCAL_RESIDUAL_PATTERNS:
        if re.search(pattern, cleaned):
            scores[INTENT_LOCAL_RESIDUAL_VALUE] += 1

    # Specific client references like "c02" or "c08"
    if re.search(r"\bc0?\d+\b", cleaned):
        scores[INTENT_CLIENTS_AT_RISK] += 3

    # Specific farm references like "f01" or "f02"
    if re.search(r"\bf0?\d+\b", cleaned):
        scores[INTENT_FARM_SEGMENT_GAPS] += 3

    # Rank intents
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_intent, best_score = ranked[0]

    if best_score > 0:
        return best_intent, TOOL_MAP[best_intent]

    return None
