from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from .models import SEGMENTS, Client, Farm, Station, ValidationErrorDetail, WorkbookData
from .xlsx_reader import read_workbook_tables, table_from_header


FARM_ID_RE = re.compile(r"^F\d{2}$")
CLIENT_ID_RE = re.compile(r"^C\d{2}$")
ACCEPTANCE_MODES = {"EXACT", "MINIMUM"}


class WorkbookValidationError(Exception):
    def __init__(self, errors: list[ValidationErrorDetail]) -> None:
        self.errors = errors
        super().__init__("Workbook validation failed")


def _error(sheet: str, entity_id: Any, field: str, problem: str) -> ValidationErrorDetail:
    return ValidationErrorDetail(sheet=sheet, entity_id=str(entity_id or "ROW"), field=field, problem=problem)


def _as_float(value: Any, sheet: str, entity_id: Any, field: str, errors: list[ValidationErrorDetail]) -> float:
    if value == "":
        errors.append(_error(sheet, entity_id, field, "missing numeric value"))
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append(_error(sheet, entity_id, field, "not a number"))
        return 0.0
    if not math.isfinite(number):
        errors.append(_error(sheet, entity_id, field, "not a finite number"))
        return 0.0
    return number


def _multiple_of_five(value: float) -> bool:
    return abs(value / 5 - round(value / 5)) < 1e-9


def _check_duplicate_ids(sheet: str, ids: list[str], errors: list[ValidationErrorDetail]) -> None:
    seen: set[str] = set()
    for entity_id in ids:
        if not entity_id:
            errors.append(_error(sheet, entity_id, "id", "missing ID"))
        elif entity_id in seen:
            errors.append(_error(sheet, entity_id, "id", "duplicate ID"))
        seen.add(entity_id)


def load_workbook(path: str | Path) -> WorkbookData:
    tables = read_workbook_tables(path)
    errors: list[ValidationErrorDetail] = []

    for sheet in ("Farms", "Clients", "Station"):
        if sheet not in tables:
            errors.append(_error(sheet, "", "sheet", "missing required sheet"))

    farms_table = table_from_header(tables.get("Farms", []), "farm_id")
    clients_table = table_from_header(tables.get("Clients", []), "client_id")
    station_table = table_from_header(tables.get("Station", []), "station_id")
    ref_table = table_from_header(tables.get("Station", []), "segment")

    if not farms_table:
        errors.append(_error("Farms", "", "farm_id", "missing farm table"))
    if not clients_table:
        errors.append(_error("Clients", "", "client_id", "missing client table"))
    if not station_table:
        errors.append(_error("Station", "", "station_id", "missing station table"))
    if not ref_table:
        errors.append(_error("Station", "", "segment", "missing segment reference prices"))

    farms = _parse_farms(farms_table, errors)
    clients = _parse_clients(clients_table, errors)
    station = _parse_station(station_table, ref_table, errors)

    _check_duplicate_ids("Farms", [farm.farm_id for farm in farms], errors)
    _check_duplicate_ids("Clients", [client.client_id for client in clients], errors)

    if errors:
        raise WorkbookValidationError(errors)

    return WorkbookData(farms=farms, clients=clients, station=station)


def _parse_farms(rows: list[dict[str, Any]], errors: list[ValidationErrorDetail]) -> list[Farm]:
    farms: list[Farm] = []
    for row in rows:
        farm_id = str(row.get("farm_id", "")).strip()
        if not FARM_ID_RE.match(farm_id):
            errors.append(_error("Farms", farm_id, "farm_id", "invalid farm ID"))
        name = str(row.get("farm_name", "")).strip()
        capacity = _as_float(row.get("expected_daily_capacity_t", ""), "Farms", farm_id, "expected_daily_capacity_t", errors)
        if capacity < 0:
            errors.append(_error("Farms", farm_id, "expected_daily_capacity_t", "negative quantity"))

        expected_mix = {}
        for segment in SEGMENTS:
            field = f"expected_{segment}_pct"
            value = _as_float(row.get(field, ""), "Farms", farm_id, field, errors)
            if value < 0 or value > 1:
                errors.append(_error("Farms", farm_id, field, "mix value outside 0-1"))
            expected_mix[segment] = value
        if abs(sum(expected_mix.values()) - 1.0) > 1e-6:
            errors.append(_error("Farms", farm_id, "expected_mix", "mix does not sum to 1.0"))

        actual_t = {}
        for segment in SEGMENTS:
            field = f"actual_{segment}_t"
            value = _as_float(row.get(field, ""), "Farms", farm_id, field, errors)
            if value < 0:
                errors.append(_error("Farms", farm_id, field, "negative quantity"))
            if not _multiple_of_five(value):
                errors.append(_error("Farms", farm_id, field, "actual quantity is not a multiple of 5 t"))
            actual_t[segment] = value
        farms.append(Farm(farm_id=farm_id, farm_name=name, expected_daily_capacity_t=capacity, expected_mix=expected_mix, actual_t=actual_t))
    return farms


def _parse_clients(rows: list[dict[str, Any]], errors: list[ValidationErrorDetail]) -> list[Client]:
    clients: list[Client] = []
    for row in rows:
        client_id = str(row.get("client_id", "")).strip()
        if not CLIENT_ID_RE.match(client_id):
            errors.append(_error("Clients", client_id, "client_id", "invalid client ID"))
        mode = str(row.get("acceptance_mode", "")).strip()
        if mode not in ACCEPTANCE_MODES:
            errors.append(_error("Clients", client_id, "acceptance_mode", "invalid acceptance mode"))
        segment = str(row.get("requested_segment", "")).strip()
        if segment not in SEGMENTS:
            errors.append(_error("Clients", client_id, "requested_segment", "invalid segment"))
            segment = "A"
        demand = _as_float(row.get("demand_t", ""), "Clients", client_id, "demand_t", errors)
        if demand < 0:
            errors.append(_error("Clients", client_id, "demand_t", "negative quantity"))
        if not _multiple_of_five(demand):
            errors.append(_error("Clients", client_id, "demand_t", "client demand is not a multiple of 5 t"))
        price = _as_float(row.get("export_price_per_t_eur", ""), "Clients", client_id, "export_price_per_t_eur", errors)
        if price < 0:
            errors.append(_error("Clients", client_id, "export_price_per_t_eur", "negative quantity"))
        clients.append(Client(client_id=client_id, client_name=str(row.get("client_name", "")).strip(), acceptance_mode=mode, requested_segment=segment, demand_t=demand, export_price_per_t_eur=price))  # type: ignore[arg-type]
    return clients


def _parse_station(station_rows: list[dict[str, Any]], ref_rows: list[dict[str, Any]], errors: list[ValidationErrorDetail]) -> Station:
    station_row = station_rows[0] if station_rows else {}
    station_id = str(station_row.get("station_id", "")).strip()
    capacity = _as_float(station_row.get("export_conditioning_capacity_t", ""), "Station", station_id, "export_conditioning_capacity_t", errors)
    if capacity <= 0 or not _multiple_of_five(capacity):
        errors.append(_error("Station", station_id, "export_conditioning_capacity_t", "invalid station capacity"))
    ratio = _as_float(station_row.get("local_market_ratio", ""), "Station", station_id, "local_market_ratio", errors)
    if ratio < 0 or ratio > 1:
        errors.append(_error("Station", station_id, "local_market_ratio", "ratio outside 0-1"))

    reference_prices = {}
    seen: set[str] = set()
    for row in ref_rows:
        segment = str(row.get("segment", "")).strip()
        if segment not in SEGMENTS:
            errors.append(_error("Station", segment, "segment", "invalid segment"))
            continue
        if segment in seen:
            errors.append(_error("Station", segment, "segment", "duplicate segment reference price"))
        seen.add(segment)
        price = _as_float(row.get("reference_export_price_per_t_eur", ""), "Station", segment, "reference_export_price_per_t_eur", errors)
        if price < 0:
            errors.append(_error("Station", segment, "reference_export_price_per_t_eur", "negative quantity"))
        reference_prices[segment] = price
    for segment in SEGMENTS:
        if segment not in reference_prices:
            errors.append(_error("Station", segment, "reference_export_price_per_t_eur", "missing segment reference price"))
            reference_prices[segment] = 0.0
    return Station(station_id=station_id, export_conditioning_capacity_t=capacity, local_market_ratio=ratio, reference_prices=reference_prices)
