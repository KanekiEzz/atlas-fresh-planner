"""Strict validation and entity checking for Ollama output.

Ensures no hallucinated IDs (e.g. C99, F99) or ungrounded claims reach the user.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Set, Tuple


class OutputValidationError(Exception):
    """Raised when Ollama output is malformed, hallucinated, or unverifiable."""
    def __init__(self, message: str):
        super().__init__(message)


def clean_raw_output(raw: str) -> str:
    """Strip markdown code fences and whitespace from raw LLM output."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def validate_ai_response(
    raw_output: str,
    valid_entities: Dict[str, Set[str]],
    expected_intent: str,
) -> Tuple[str, List[Dict[str, str]]]:
    """Validate and clean Ollama output against the deterministic entity whitelist.
    
    Returns (cleaned_answer, validated_evidence_list).
    Raises OutputValidationError if output is unparseable or contains hallucinated entities.
    """
    cleaned_json = clean_raw_output(raw_output)
    try:
        data = json.loads(cleaned_json)
    except json.JSONDecodeError as exc:
        raise OutputValidationError(f"Model output is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise OutputValidationError("Model output is not a JSON object")

    answer = str(data.get("answer", "")).strip()
    if not answer:
        raise OutputValidationError("Model output has empty 'answer'")

    raw_evidence = data.get("evidence", [])
    if not isinstance(raw_evidence, list):
        raise OutputValidationError("'evidence' field must be a list")

    all_known_clients = valid_entities.get("all_known_clients", set())
    all_known_farms = valid_entities.get("all_known_farms", set())
    valid_segments = valid_entities.get("segments", {"A", "B", "C", "D"})

    # Check for hallucinated IDs mentioned in the text answer
    text_client_mentions = re.findall(r"\bC\d+\b", answer)
    for cid in text_client_mentions:
        if cid not in all_known_clients:
            raise OutputValidationError(f"Hallucinated client ID '{cid}' in answer text")

    text_farm_mentions = re.findall(r"\bF\d+\b", answer)
    for fid in text_farm_mentions:
        if fid not in all_known_farms:
            raise OutputValidationError(f"Hallucinated farm ID '{fid}' in answer text")

    validated_evidence: List[Dict[str, str]] = []
    has_unknown_id = False

    for item in raw_evidence:
        item_type = ""
        item_id = ""

        if isinstance(item, dict):
            item_type = str(item.get("type", "")).strip().lower()
            item_id = str(item.get("id", "")).strip()
        elif isinstance(item, str):
            # Normalize string evidence if model returned plain strings
            item_str = item.strip()
            if re.match(r"^C\d+$", item_str):
                item_type = "client"
                item_id = item_str
            elif re.match(r"^F\d+$", item_str):
                item_type = "farm"
                item_id = item_str
            elif item_str in valid_segments or re.match(r"^Segment\s+([A-D])$", item_str):
                item_type = "segment"
                match = re.match(r"^Segment\s+([A-D])$", item_str)
                item_id = match.group(1) if match else item_str
            else:
                has_unknown_id = True
                continue

        # Validate against known entities
        if item_type == "client":
            if item_id in all_known_clients:
                validated_evidence.append({"type": "client", "id": item_id})
            else:
                has_unknown_id = True
        elif item_type == "farm":
            if item_id in all_known_farms:
                validated_evidence.append({"type": "farm", "id": item_id})
            else:
                has_unknown_id = True
        elif item_type == "segment":
            seg = item_id.replace("Segment", "").strip()
            if seg in valid_segments:
                validated_evidence.append({"type": "segment", "id": seg})
            else:
                has_unknown_id = True
        else:
            has_unknown_id = True

    # If the model introduced unknown/hallucinated IDs in evidence, reject the response
    if has_unknown_id and not validated_evidence:
        raise OutputValidationError("Evidence contained invalid or unknown IDs")

    # Deduplicate validated evidence while preserving order
    seen: Set[Tuple[str, str]] = set()
    deduped_evidence: List[Dict[str, str]] = []
    for ev in validated_evidence:
        key = (ev["type"], ev["id"])
        if key not in seen:
            seen.add(key)
            deduped_evidence.append(ev)

    return answer, deduped_evidence
