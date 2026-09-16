from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from app.models import Client, Farm, Station, WorkbookData
from app.planning import generate_plan, is_compatible, sorted_clients
from app.validation import WorkbookValidationError, load_workbook


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "public/Atlas_Fresh_Production_Commercial_Data.xlsx"


def farm(farm_id: str, actual: dict[str, float]) -> Farm:
    return Farm(
        farm_id=farm_id,
        farm_name=f"Farm {farm_id}",
        expected_daily_capacity_t=sum(actual.values()),
        expected_mix={"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25},
        actual_t={"A": actual.get("A", 0.0), "B": actual.get("B", 0.0), "C": actual.get("C", 0.0), "D": actual.get("D", 0.0)},
    )


def station(capacity: float = 500.0) -> Station:
    return Station(
        station_id="STATION-01",
        export_conditioning_capacity_t=capacity,
        local_market_ratio=0.1,
        reference_prices={"A": 1500.0, "B": 1250.0, "C": 1000.0, "D": 750.0},
    )


class PlanningTests(unittest.TestCase):
    def test_baseline_output_from_workbook(self):
        data = load_workbook(WORKBOOK)
        plan = generate_plan(data)

        self.assertEqual(plan.expected_total_t, 600.0)
        self.assertEqual(plan.actual_total_t, 560.0)
        self.assertEqual(plan.station_capacity_t, 500.0)
        self.assertEqual(plan.actual_by_segment_t, {"A": 90.0, "B": 160.0, "C": 180.0, "D": 130.0})
        self.assertEqual(plan.exported_t, 500.0)
        self.assertEqual(plan.local_t, 60.0)
        self.assertAlmostEqual(plan.export_rate, 500.0 / 560.0)
        self.assertEqual(plan.export_revenue_eur, 549500.0)
        self.assertEqual(plan.local_value_eur, 4500.0)
        self.assertEqual(plan.total_value_eur, 554000.0)

        at_risk = {client.client_id: client.shortage_reason for client in plan.clients if client.status != "COMPLETE"}
        self.assertEqual(
            at_risk,
            {
                "C02": "INSUFFICIENT_COMPATIBLE_SEGMENT",
                "C09": "INSUFFICIENT_COMPATIBLE_SEGMENT",
                "C08": "STATION_CAPACITY_REACHED",
            },
        )

    def test_client_price_ordering(self):
        clients = [
            Client("C02", "Second", "EXACT", "A", 5.0, 100.0),
            Client("C01", "First", "EXACT", "A", 5.0, 100.0),
            Client("C03", "Premium", "EXACT", "A", 5.0, 200.0),
        ]
        self.assertEqual([client.client_id for client in sorted_clients(clients)], ["C03", "C01", "C02"])

    def test_exact_compatibility(self):
        client = Client("C01", "Exact B", "EXACT", "B", 10.0, 100.0)
        self.assertFalse(is_compatible(client, "A"))
        self.assertTrue(is_compatible(client, "B"))
        self.assertFalse(is_compatible(client, "C"))

    def test_minimum_compatibility_and_quality_preference(self):
        data = WorkbookData(
            farms=[farm("F01", {"A": 5.0}), farm("F02", {"B": 5.0}), farm("F03", {"C": 5.0})],
            clients=[Client("C01", "Minimum C", "MINIMUM", "C", 15.0, 1000.0)],
            station=station(),
        )
        plan = generate_plan(data)
        self.assertEqual([(a.farm_id, a.segment) for a in plan.allocations], [("F03", "C"), ("F02", "B"), ("F01", "A")])

    def test_station_capacity_limit(self):
        data = WorkbookData(
            farms=[farm("F01", {"D": 30.0})],
            clients=[Client("C01", "Minimum D", "MINIMUM", "D", 30.0, 700.0)],
            station=station(capacity=10.0),
        )
        plan = generate_plan(data)
        self.assertEqual(plan.exported_t, 10.0)
        self.assertEqual(plan.local_t, 20.0)
        self.assertEqual(plan.clients[0].shortage_reason, "STATION_CAPACITY_REACHED")

    def test_local_residual_calculation(self):
        data = WorkbookData(
            farms=[farm("F01", {"D": 15.0})],
            clients=[Client("C01", "Exact D", "EXACT", "D", 5.0, 750.0)],
            station=station(),
        )
        plan = generate_plan(data)
        self.assertEqual(plan.local_t, 10.0)
        self.assertEqual(plan.local_value_eur, 750.0)

    def test_invalid_workbook_validation_duplicate_client(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_path = Path(tmpdir) / "invalid.xlsx"
            with zipfile.ZipFile(WORKBOOK) as source, zipfile.ZipFile(invalid_path, "w") as target:
                for name in source.namelist():
                    content = source.read(name)
                    if name == "xl/worksheets/sheet3.xml":
                        content = content.decode("utf-8").replace(">C02<", ">C01<", 1).encode("utf-8")
                    target.writestr(name, content)

            with self.assertRaises(WorkbookValidationError) as ctx:
                load_workbook(invalid_path)
            self.assertTrue(any(error.problem == "duplicate ID" for error in ctx.exception.errors))


if __name__ == "__main__":
    unittest.main()
