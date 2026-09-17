"""Deterministic data tools for Atlas Fresh Planning Assistant.

These tools are strictly read-only explainer extractors. They NEVER calculate
allocations, modify data, change KPIs, or invent values. All numbers and entities
come directly from the authoritative PlanningResult.
"""
from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple


APPROVED_TOOLS = {
    "get_clients_at_risk",
    "get_farm_segment_gaps",
    "get_local_residual_value",
    "reject_question",
}


def _format_shortage_reason(reason: str) -> str:
    if reason == "INSUFFICIENT_COMPATIBLE_SEGMENT":
        return "insufficient compatible segment supply available"
    if reason == "STATION_CAPACITY_REACHED":
        return "export conditioning station capacity reached (500t limit)"
    return reason or "unknown constraint"


def get_clients_at_risk(plan: Any) -> Tuple[Dict[str, Any], Dict[str, Set[str]]]:
    """Extract minimal structured facts about clients with unmet demand."""
    at_risk_clients = [c for c in plan.clients if getattr(c, "status", "") != "COMPLETE"]

    clients_data: List[Dict[str, Any]] = []
    valid_client_ids: Set[str] = set()
    valid_segments: Set[str] = set()

    for client in at_risk_clients:
        client_id = str(getattr(client, "client_id", ""))
        valid_client_ids.add(client_id)
        segment = str(getattr(client, "requested_segment", ""))
        if segment:
            valid_segments.add(segment)

        allocated_t = float(getattr(client, "allocated_t", 0.0))
        demand_t = float(getattr(client, "demand_t", 0.0))
        remaining_t = float(getattr(client, "remaining_t", 0.0))
        service_level = "partially served" if allocated_t > 0 else "unserved"

        clients_data.append({
            "client_id": client_id,
            "client_name": str(getattr(client, "client_name", "")),
            "requested_quality": segment,
            "acceptance_mode": str(getattr(client, "acceptance_mode", "")),
            "wanted_tonnes": round(demand_t, 1),
            "received_tonnes": round(allocated_t, 1),
            "still_needed_tonnes": round(remaining_t, 1),
            "service_level": service_level,
            "plain_reason": _format_shortage_reason(str(getattr(client, "shortage_reason", ""))),
        })

    facts = {
        "intent": "clients_at_risk",
        "total_clients": len(getattr(plan, "clients", [])),
        "at_risk_count": len(at_risk_clients),
        "clients": clients_data,
    }

    all_client_ids = {str(getattr(c, "client_id", "")) for c in getattr(plan, "clients", [])}

    valid_entities = {
        "clients": valid_client_ids,
        "all_known_clients": all_client_ids,
        "farms": set(),
        "all_known_farms": {str(f.get("farm_id") if isinstance(f, dict) else getattr(f, "farm_id", "")) for f in getattr(plan, "farms", [])},
        "segments": {"A", "B", "C", "D"},
    }

    return facts, valid_entities


def get_farm_segment_gaps(plan: Any) -> Tuple[Dict[str, Any], Dict[str, Set[str]]]:
    """Extract minimal structured facts about farm and segment production shortfalls."""
    segment_variances = getattr(plan, "segment_variance_t", {}) or {}
    primary_segment_gaps: List[Dict[str, Any]] = []
    for seg, var in segment_variances.items():
        if var < 0:
            exp_t = getattr(plan, "expected_by_segment_t", {}).get(seg, 0.0)
            act_t = getattr(plan, "actual_by_segment_t", {}).get(seg, 0.0)
            primary_segment_gaps.append({
                "segment": seg,
                "expected_tonnes": round(float(exp_t), 1),
                "actual_tonnes": round(float(act_t), 1),
                "variance_tonnes": round(float(var), 1),
            })
    primary_segment_gaps.sort(key=lambda item: item["variance_tonnes"])

    # Extract farm-level segment shortfalls from farm rows
    farm_gaps: List[Dict[str, Any]] = []
    farm_rows = getattr(plan, "farms", [])
    valid_farm_ids: Set[str] = set()

    for farm in farm_rows:
        farm_id = farm.get("farm_id", "") if isinstance(farm, dict) else getattr(farm, "farm_id", "")
        if farm_id:
            valid_farm_ids.add(str(farm_id))

        segments = farm.get("segments", {}) if isinstance(farm, dict) else getattr(farm, "segments", {})
        for seg, details in segments.items():
            variance = details.get("variance_t", 0.0) if isinstance(details, dict) else getattr(details, "variance_t", 0.0)
            if variance < 0:
                exp_t = details.get("expected_t", 0.0) if isinstance(details, dict) else getattr(details, "expected_t", 0.0)
                act_t = details.get("actual_t", 0.0) if isinstance(details, dict) else getattr(details, "actual_t", 0.0)
                farm_gaps.append({
                    "farm_id": farm_id,
                    "farm_name": farm.get("farm_name", f"Farm {farm_id}") if isinstance(farm, dict) else getattr(farm, "farm_name", ""),
                    "segment": seg,
                    "expected_tonnes": round(float(exp_t), 1),
                    "actual_tonnes": round(float(act_t), 1),
                    "variance_tonnes": round(float(variance), 1),
                })

    # Sort gaps by worst shortage first
    farm_gaps.sort(key=lambda item: (item["variance_tonnes"], item["farm_id"]))

    facts = {
        "intent": "farm_segment_gaps",
        "primary_segment_shortfalls": primary_segment_gaps,
        "significant_farm_gaps": farm_gaps[:6],
    }

    valid_entities = {
        "clients": set(),
        "all_known_clients": {str(getattr(c, "client_id", "")) for c in getattr(plan, "clients", [])},
        "farms": valid_farm_ids,
        "all_known_farms": valid_farm_ids,
        "segments": {"A", "B", "C", "D"},
    }

    return facts, valid_entities


def get_local_residual_value(plan: Any) -> Tuple[Dict[str, Any], Dict[str, Set[str]]]:
    """Extract minimal structured facts about local residual tonnes and valuation."""
    local_residuals = getattr(plan, "local_residuals", [])
    local_t = float(getattr(plan, "local_t", 0.0))
    exported_t = float(getattr(plan, "exported_t", 0.0))
    station_capacity_t = float(getattr(plan, "station_capacity_t", 500.0))
    actual_total_t = float(getattr(plan, "actual_total_t", 0.0))
    local_value_eur = float(getattr(plan, "local_value_eur", 0.0))

    station_is_full = exported_t >= station_capacity_t

    main_residuals: List[Dict[str, Any]] = []
    valid_farms: Set[str] = set()
    valid_segments: Set[str] = set()

    for item in local_residuals:
        farm_id = str(getattr(item, "farm_id", ""))
        seg = str(getattr(item, "segment", ""))
        tonnes = float(getattr(item, "tonnes", 0.0))
        ref_price = float(getattr(item, "reference_price_per_t_eur", 0.0))
        val_eur = float(getattr(item, "local_value_eur", 0.0))

        if farm_id:
            valid_farms.add(farm_id)
        if seg:
            valid_segments.add(seg)

        main_residuals.append({
            "farm_id": farm_id,
            "segment": seg,
            "tonnes": round(tonnes, 1),
            "reference_price_eur": round(ref_price, 0),
            "local_value_eur": round(val_eur, 0),
        })

    all_farm_ids = {str(f.get("farm_id") if isinstance(f, dict) else getattr(f, "farm_id", "")) for f in getattr(plan, "farms", [])}

    facts = {
        "intent": "local_residual_value",
        "tonnes_going_local": round(local_t, 1),
        "estimated_local_value_eur": round(local_value_eur, 0),
        "exported_tonnes": round(exported_t, 1),
        "station_limit_tonnes": round(station_capacity_t, 1),
        "total_received_tonnes": round(actual_total_t, 1),
        "station_is_full": station_is_full,
        "pricing_explanation": "Local residual fruit is valued at 10% of the segment reference export price",
        "main_farms_sending_local": main_residuals,
    }

    valid_entities = {
        "clients": set(),
        "all_known_clients": {str(getattr(c, "client_id", "")) for c in getattr(plan, "clients", [])},
        "farms": valid_farms or all_farm_ids,
        "all_known_farms": all_farm_ids,
        "segments": valid_segments or {"A", "B", "C", "D"},
    }

    return facts, valid_entities


def reject_question(_plan: Any) -> Tuple[Dict[str, Any], Dict[str, Set[str]]]:
    """Return rejection facts for unsupported questions."""
    facts = {
        "intent": "unsupported_question",
        "supported_topics": [
            "clients at risk and shortage reasons",
            "farm and segment production gaps",
            "local residual tonnes and estimated local value",
        ],
    }
    valid_entities = {
        "clients": set(),
        "all_known_clients": set(),
        "farms": set(),
        "all_known_farms": set(),
        "segments": set(),
    }
    return facts, valid_entities


def run_tool(name: str, plan: Any) -> Tuple[Dict[str, Any], Dict[str, Set[str]]]:
    """Dispatch execution to an approved deterministic tool."""
    if name not in APPROVED_TOOLS:
        raise ValueError(f"Unauthorized tool: {name}. Permitted tools: {sorted(APPROVED_TOOLS)}")

    tools_map = {
        "get_clients_at_risk": get_clients_at_risk,
        "get_farm_segment_gaps": get_farm_segment_gaps,
        "get_local_residual_value": get_local_residual_value,
        "reject_question": reject_question,
    }
    return tools_map[name](plan)
