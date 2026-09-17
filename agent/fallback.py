"""Deterministic fallback generator for Atlas Fresh Planning Assistant.

Generates structured, grounded explanations directly from the deterministic tool facts
whenever Ollama is not configured, unreachable, times out, or returns invalid output.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


def generate_deterministic_fallback(
    intent: str,
    facts: Dict[str, Any],
    provider_reason: str = "Ollama is not configured or unavailable.",
) -> Tuple[str, List[Dict[str, str]]]:
    """Generate a deterministic decision summary grounded in current facts."""
    header = f"Planning Assistant — deterministic summary\n\n{provider_reason}\n\n"

    if intent == "clients_at_risk":
        clients = facts.get("clients", [])
        at_risk_count = facts.get("at_risk_count", len(clients))
        if not clients:
            body = "All commercial clients are fully served according to the current plan."
            evidence = []
        else:
            client_bullets = []
            evidence = []
            for client in clients:
                cid = client["client_id"]
                service = client.get("service_level", "partially served")
                needed = client.get("still_needed_tonnes", 0.0)
                reason = client.get("plain_reason", "supply shortage")
                quality = client.get("requested_quality", "")
                client_bullets.append(
                    f"• {cid} is {service} ({needed:.1f} t remaining, requested Segment {quality}) because {reason}."
                )
                evidence.append({"type": "client", "id": cid})
            body = f"{at_risk_count} clients are at risk today:\n" + "\n".join(client_bullets)

        return header + body, evidence

    if intent == "farm_segment_gaps":
        seg_gaps = facts.get("primary_segment_shortfalls", [])
        farm_gaps = facts.get("significant_farm_gaps", [])
        evidence: List[Dict[str, str]] = []

        seg_lines = []
        for sg in seg_gaps:
            seg = sg["segment"]
            var_t = abs(sg["variance_tonnes"])
            seg_lines.append(f"Segment {seg} is {var_t:.1f} t below plan")
            evidence.append({"type": "segment", "id": seg})

        farm_lines = []
        for fg in farm_gaps[:4]:
            fid = fg["farm_id"]
            seg = fg["segment"]
            var_t = abs(fg["variance_tonnes"])
            farm_lines.append(f"• {fid} (Segment {seg}): {var_t:.1f} t short versus expected capacity.")
            evidence.append({"type": "farm", "id": fid})
            evidence.append({"type": "segment", "id": seg})

        seg_summary = "; ".join(seg_lines) if seg_lines else "No overall segment deficit."
        body = f"The primary production deficit is: {seg_summary}.\nKey farm-level shortfalls:\n" + "\n".join(farm_lines)

        # Deduplicate evidence
        seen = set()
        deduped = []
        for ev in evidence:
            key = (ev["type"], ev["id"])
            if key not in seen:
                seen.add(key)
                deduped.append(ev)

        return header + body, deduped

    if intent == "local_residual_value":
        local_t = facts.get("tonnes_going_local", 0.0)
        local_val = facts.get("estimated_local_value_eur", 0.0)
        station_limit = facts.get("station_limit_tonnes", 500.0)
        received_t = facts.get("total_received_tonnes", 0.0)
        station_full = facts.get("station_is_full", True)

        reason = (
            f"the export conditioning station reached its maximum {station_limit:.0f} t/day capacity limit (total received: {received_t:.0f} t)"
            if station_full
            else "available compatible export demand was exhausted"
        )

        body = (
            f"{local_t:.1f} t of fruit are diverted to the local market because {reason}. "
            f"The estimated local value is EUR {local_val:,.0f}, calculated at 10% of the segment reference export price."
        )

        residuals = facts.get("main_farms_sending_local", [])
        evidence: List[Dict[str, str]] = []
        for res in residuals[:6]:
            if res.get("farm_id"):
                evidence.append({"type": "farm", "id": res["farm_id"]})
            if res.get("segment"):
                evidence.append({"type": "segment", "id": res["segment"]})

        seen = set()
        deduped = []
        for ev in evidence:
            key = (ev["type"], ev["id"])
            if key not in seen:
                seen.add(key)
                deduped.append(ev)

        return header + body, deduped

    return header + "This question is not supported by the assistant.", []
