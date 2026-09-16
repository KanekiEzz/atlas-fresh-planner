from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Segment = Literal["A", "B", "C", "D"]
AcceptanceMode = Literal["EXACT", "MINIMUM"]
ClientStatus = Literal["COMPLETE", "PARTIAL", "UNSERVED"]
ShortageReason = Literal["INSUFFICIENT_COMPATIBLE_SEGMENT", "STATION_CAPACITY_REACHED", ""]

SEGMENTS: list[Segment] = ["A", "B", "C", "D"]
QUALITY_RANK: dict[Segment, int] = {"A": 0, "B": 1, "C": 2, "D": 3}


@dataclass(frozen=True)
class ValidationErrorDetail:
    sheet: str
    entity_id: str
    field: str
    problem: str


@dataclass(frozen=True)
class Farm:
    farm_id: str
    farm_name: str
    expected_daily_capacity_t: float
    expected_mix: dict[Segment, float]
    actual_t: dict[Segment, float]


@dataclass(frozen=True)
class Client:
    client_id: str
    client_name: str
    acceptance_mode: AcceptanceMode
    requested_segment: Segment
    demand_t: float
    export_price_per_t_eur: float


@dataclass(frozen=True)
class Station:
    station_id: str
    export_conditioning_capacity_t: float
    local_market_ratio: float
    reference_prices: dict[Segment, float]


@dataclass(frozen=True)
class WorkbookData:
    farms: list[Farm]
    clients: list[Client]
    station: Station


@dataclass
class SupplyLot:
    farm_id: str
    segment: Segment
    actual_t: float
    remaining_t: float


@dataclass
class Allocation:
    farm_id: str
    segment: Segment
    client_id: str
    tonnes: float
    quality_upgrade: str
    export_price_per_t_eur: float
    export_revenue_eur: float


@dataclass
class LocalResidual:
    farm_id: str
    segment: Segment
    tonnes: float
    reference_price_per_t_eur: float
    local_value_eur: float


@dataclass
class ClientResult:
    client_id: str
    client_name: str
    acceptance_mode: AcceptanceMode
    requested_segment: Segment
    demand_t: float
    export_price_per_t_eur: float
    allocated_t: float
    remaining_t: float
    export_revenue_eur: float
    status: ClientStatus
    shortage_reason: ShortageReason


@dataclass
class PlanningResult:
    data_health: str
    farms_count: int
    clients_count: int
    station_capacity_t: float
    expected_total_t: float
    actual_total_t: float
    production_variance_t: float
    expected_by_segment_t: dict[Segment, float]
    actual_by_segment_t: dict[Segment, float]
    segment_variance_t: dict[Segment, float]
    exported_t: float
    local_t: float
    export_rate: float
    export_revenue_eur: float
    local_value_eur: float
    total_value_eur: float
    allocations: list[Allocation]
    local_residuals: list[LocalResidual]
    clients: list[ClientResult]
    farms: list[dict]
    production_alerts: list[dict]
    impact: dict[str, dict] = field(default_factory=dict)
