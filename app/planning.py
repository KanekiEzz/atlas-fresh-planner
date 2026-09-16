from __future__ import annotations

from collections import defaultdict

from .models import (
    QUALITY_RANK,
    SEGMENTS,
    Allocation,
    Client,
    ClientResult,
    LocalResidual,
    PlanningResult,
    Segment,
    SupplyLot,
    WorkbookData,
)


STEP_T = 5.0


class PlanningInvariantError(Exception):
    pass


def is_compatible(client: Client, segment: Segment) -> bool:
    if client.acceptance_mode == "EXACT":
        return segment == client.requested_segment
    return QUALITY_RANK[segment] <= QUALITY_RANK[client.requested_segment]


def quality_upgrade_label(client: Client, segment: Segment) -> str:
    return "EXACT" if segment == client.requested_segment else "UPGRADED"


def quality_upgrade_distance(client: Client, segment: Segment) -> int:
    return QUALITY_RANK[client.requested_segment] - QUALITY_RANK[segment]


def sorted_clients(clients: list[Client]) -> list[Client]:
    return sorted(clients, key=lambda client: (-client.export_price_per_t_eur, client.client_id))


def generate_plan(data: WorkbookData) -> PlanningResult:
    supply = [
        SupplyLot(farm_id=farm.farm_id, segment=segment, actual_t=farm.actual_t[segment], remaining_t=farm.actual_t[segment])
        for farm in data.farms
        for segment in SEGMENTS
        if farm.actual_t[segment] > 0
    ]

    allocations_by_key: dict[tuple[str, Segment, str, str, float], Allocation] = {}
    client_allocated = defaultdict(float)
    client_revenue = defaultdict(float)
    station_remaining = data.station.export_conditioning_capacity_t
    processed_clients = sorted_clients(data.clients)

    for client in processed_clients:
        demand_remaining = client.demand_t
        while demand_remaining >= STEP_T and station_remaining >= STEP_T:
            compatible = [
                lot
                for lot in supply
                if lot.remaining_t >= STEP_T and is_compatible(client, lot.segment)
            ]
            if not compatible:
                break
            compatible.sort(key=lambda lot: (quality_upgrade_distance(client, lot.segment), lot.farm_id))
            selected = compatible[0]
            selected.remaining_t -= STEP_T
            demand_remaining -= STEP_T
            station_remaining -= STEP_T
            client_allocated[client.client_id] += STEP_T
            client_revenue[client.client_id] += STEP_T * client.export_price_per_t_eur

            upgrade = quality_upgrade_label(client, selected.segment)
            key = (selected.farm_id, selected.segment, client.client_id, upgrade, client.export_price_per_t_eur)
            if key not in allocations_by_key:
                allocations_by_key[key] = Allocation(
                    farm_id=selected.farm_id,
                    segment=selected.segment,
                    client_id=client.client_id,
                    tonnes=0.0,
                    quality_upgrade=upgrade,
                    export_price_per_t_eur=client.export_price_per_t_eur,
                    export_revenue_eur=0.0,
                )
            allocations_by_key[key].tonnes += STEP_T
            allocations_by_key[key].export_revenue_eur += STEP_T * client.export_price_per_t_eur

    allocations = list(allocations_by_key.values())

    local_residuals = [
        LocalResidual(
            farm_id=lot.farm_id,
            segment=lot.segment,
            tonnes=lot.remaining_t,
            reference_price_per_t_eur=data.station.reference_prices[lot.segment],
            local_value_eur=lot.remaining_t * data.station.local_market_ratio * data.station.reference_prices[lot.segment],
        )
        for lot in sorted(supply, key=lambda item: (item.farm_id, item.segment))
        if lot.remaining_t > 0
    ]

    client_results = _client_results(data.clients, client_allocated, client_revenue, station_remaining, supply)
    farm_rows = _farm_rows(data, local_residuals)

    expected_by_segment = {
        segment: round(sum(farm.expected_daily_capacity_t * farm.expected_mix[segment] for farm in data.farms), 10)
        for segment in SEGMENTS
    }
    actual_by_segment = {segment: sum(farm.actual_t[segment] for farm in data.farms) for segment in SEGMENTS}
    expected_total = sum(farm.expected_daily_capacity_t for farm in data.farms)
    actual_total = sum(actual_by_segment.values())
    exported_t = sum(allocation.tonnes for allocation in allocations)
    local_t = sum(residual.tonnes for residual in local_residuals)
    export_revenue = sum(allocation.export_revenue_eur for allocation in allocations)
    local_value = sum(residual.local_value_eur for residual in local_residuals)
    segment_variance = {segment: actual_by_segment[segment] - expected_by_segment[segment] for segment in SEGMENTS}

    result = PlanningResult(
        data_health="VALIDATED",
        farms_count=len(data.farms),
        clients_count=len(data.clients),
        station_capacity_t=data.station.export_conditioning_capacity_t,
        expected_total_t=expected_total,
        actual_total_t=actual_total,
        production_variance_t=actual_total - expected_total,
        expected_by_segment_t=expected_by_segment,
        actual_by_segment_t=actual_by_segment,
        segment_variance_t=segment_variance,
        exported_t=exported_t,
        local_t=local_t,
        export_rate=exported_t / actual_total if actual_total else 0.0,
        export_revenue_eur=export_revenue,
        local_value_eur=local_value,
        total_value_eur=export_revenue + local_value,
        allocations=allocations,
        local_residuals=local_residuals,
        clients=client_results,
        farms=farm_rows,
        production_alerts=_production_alerts(farm_rows, segment_variance),
    )
    result.impact = _impact_map(result)
    enforce_invariants(data, result)
    return result


def _client_results(
    clients: list[Client],
    client_allocated: dict[str, float],
    client_revenue: dict[str, float],
    station_remaining: float,
    supply: list[SupplyLot],
) -> list[ClientResult]:
    remaining_supply = {(lot.farm_id, lot.segment): lot.remaining_t for lot in supply}
    results: list[ClientResult] = []
    for client in sorted_clients(clients):
        allocated = client_allocated[client.client_id]
        remaining = client.demand_t - allocated
        if remaining <= 0:
            status = "COMPLETE"
            reason = ""
        else:
            status = "UNSERVED" if allocated == 0 else "PARTIAL"
            has_compatible_supply = any(
                qty >= STEP_T and is_compatible(client, segment)
                for (_, segment), qty in remaining_supply.items()
            )
            reason = "STATION_CAPACITY_REACHED" if station_remaining < STEP_T and has_compatible_supply else "INSUFFICIENT_COMPATIBLE_SEGMENT"
        results.append(
            ClientResult(
                client_id=client.client_id,
                client_name=client.client_name,
                acceptance_mode=client.acceptance_mode,
                requested_segment=client.requested_segment,
                demand_t=client.demand_t,
                export_price_per_t_eur=client.export_price_per_t_eur,
                allocated_t=allocated,
                remaining_t=remaining,
                export_revenue_eur=client_revenue[client.client_id],
                status=status,  # type: ignore[arg-type]
                shortage_reason=reason,  # type: ignore[arg-type]
            )
        )
    return results


def _farm_rows(data: WorkbookData, local_residuals: list[LocalResidual]) -> list[dict]:
    local_by_farm_segment = defaultdict(float)
    for residual in local_residuals:
        local_by_farm_segment[(residual.farm_id, residual.segment)] += residual.tonnes

    rows: list[dict] = []
    for farm in sorted(data.farms, key=lambda item: item.farm_id):
        expected_by_segment = {
            segment: farm.expected_daily_capacity_t * farm.expected_mix[segment]
            for segment in SEGMENTS
        }
        actual_total = sum(farm.actual_t.values())
        row = {
            "farm_id": farm.farm_id,
            "farm_name": farm.farm_name,
            "expected_capacity_t": farm.expected_daily_capacity_t,
            "actual_total_t": actual_total,
            "variance_t": actual_total - farm.expected_daily_capacity_t,
            "segments": {},
            "local_residual_t": sum(local_by_farm_segment[(farm.farm_id, segment)] for segment in SEGMENTS),
        }
        for segment in SEGMENTS:
            row["segments"][segment] = {
                "expected_t": expected_by_segment[segment],
                "actual_t": farm.actual_t[segment],
                "variance_t": farm.actual_t[segment] - expected_by_segment[segment],
                "local_residual_t": local_by_farm_segment[(farm.farm_id, segment)],
            }
        rows.append(row)
    return rows


def _production_alerts(farm_rows: list[dict], segment_variance: dict[Segment, float]) -> list[dict]:
    alerts: list[dict] = []
    for segment, variance in segment_variance.items():
        if variance < 0:
            alerts.append(
                {
                    "type": "segment_gap",
                    "severity": "important" if segment == "A" else "normal",
                    "label": f"Segment {segment} below plan",
                    "detail": f"{abs(variance):.1f} t short versus expected plan.",
                    "segment": segment,
                    "tonnes": variance,
                }
            )
    farm_gaps: list[dict] = []
    for farm in farm_rows:
        for segment in SEGMENTS:
            variance = farm["segments"][segment]["variance_t"]
            if variance < 0:
                farm_gaps.append(
                    {
                        "type": "farm_segment_gap",
                        "severity": "important" if segment == "A" else "normal",
                        "label": f"{farm['farm_id']} Segment {segment} gap",
                        "detail": f"{abs(variance):.1f} t short; click the variance to trace affected clients.",
                        "farm_id": farm["farm_id"],
                        "segment": segment,
                        "tonnes": variance,
                    }
                )
    farm_gaps.sort(key=lambda item: (item["tonnes"], item["farm_id"], item["segment"]))
    return alerts + farm_gaps[:6]


def _impact_map(result: PlanningResult) -> dict[str, dict]:
    at_risk = [client for client in result.clients if client.status != "COMPLETE"]
    map_: dict[str, dict] = {}
    allocations_by_farm_segment = defaultdict(list)
    local_by_farm_segment = defaultdict(float)
    for allocation in result.allocations:
        allocations_by_farm_segment[(allocation.farm_id, allocation.segment)].append(allocation)
    for residual in result.local_residuals:
        local_by_farm_segment[(residual.farm_id, residual.segment)] += residual.tonnes

    for farm in result.farms:
        for segment in SEGMENTS:
            segment_row = farm["segments"][segment]
            key = f"{farm['farm_id']}:{segment}"
            allocated = allocations_by_farm_segment[(farm["farm_id"], segment)]
            affected = [
                {
                    "client_id": client.client_id,
                    "allocated_t": client.allocated_t,
                    "remaining_t": client.remaining_t,
                    "shortage_reason": client.shortage_reason,
                }
                for client in at_risk
                if any(allocation.client_id == client.client_id for allocation in allocated)
                or (client.shortage_reason == "INSUFFICIENT_COMPATIBLE_SEGMENT" and segment == client.requested_segment)
            ]
            map_[key] = {
                "farm_id": farm["farm_id"],
                "segment": segment,
                "expected_t": segment_row["expected_t"],
                "actual_t": segment_row["actual_t"],
                "variance_t": segment_row["variance_t"],
                "allocated_t": sum(allocation.tonnes for allocation in allocated),
                "local_t": local_by_farm_segment[(farm["farm_id"], segment)],
                "allocations": [
                    {
                        "client_id": allocation.client_id,
                        "tonnes": allocation.tonnes,
                        "quality_upgrade": allocation.quality_upgrade,
                    }
                    for allocation in allocated
                ],
                "affected_clients": affected,
            }
    return map_


def enforce_invariants(data: WorkbookData, result: PlanningResult) -> None:
    if result.exported_t - data.station.export_conditioning_capacity_t > 1e-9:
        raise PlanningInvariantError("export exceeds station capacity")

    client_demand = {client.client_id: client.demand_t for client in data.clients}
    client_allocated = defaultdict(float)
    supply_actual = {
        (farm.farm_id, segment): farm.actual_t[segment]
        for farm in data.farms
        for segment in SEGMENTS
    }
    supply_allocated = defaultdict(float)
    client_map = {client.client_id: client for client in data.clients}
    for allocation in result.allocations:
        client_allocated[allocation.client_id] += allocation.tonnes
        supply_allocated[(allocation.farm_id, allocation.segment)] += allocation.tonnes
        if not is_compatible(client_map[allocation.client_id], allocation.segment):
            raise PlanningInvariantError("allocation is not quality compatible")

    for client_id, allocated in client_allocated.items():
        if allocated - client_demand[client_id] > 1e-9:
            raise PlanningInvariantError("client allocation exceeds demand")
    for key, allocated in supply_allocated.items():
        if allocated - supply_actual[key] > 1e-9:
            raise PlanningInvariantError("farm-segment allocation exceeds supply")
    if abs(result.exported_t + result.local_t - result.actual_total_t) > 1e-9:
        raise PlanningInvariantError("export plus local residual does not equal actual received")
