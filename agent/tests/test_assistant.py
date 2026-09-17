"""Comprehensive test suite for the Atlas Fresh AI Planning Assistant."""
from __future__ import annotations

import copy
import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.fallback import generate_deterministic_fallback
from agent.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaNotConfiguredError,
    OllamaTimeoutError,
)
from agent.router import (
    INTENT_CLIENTS_AT_RISK,
    INTENT_FARM_SEGMENT_GAPS,
    INTENT_LOCAL_RESIDUAL_VALUE,
    route_intent,
)
from agent.service import AssistantService
from agent.tools import (
    get_clients_at_risk,
    get_farm_segment_gaps,
    get_local_residual_value,
    run_tool,
)
from agent.validation import OutputValidationError, validate_ai_response
from app.planning import generate_plan
from app.validation import load_workbook


ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = ROOT / "backend/data/Atlas_Fresh_Production_Commercial_Data.xlsx"
if not WORKBOOK.exists():
    WORKBOOK = ROOT / "Atlas_Fresh_Production_Commercial_Data.xlsx"


class TestAssistant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workbook_data = load_workbook(WORKBOOK)
        cls.plan = generate_plan(cls.workbook_data)

    def setUp(self):
        # Clear simulation env vars
        os.environ.pop("ATLAS_ASSISTANT_SIMULATE", None)

    def test_router_all_supported_intents(self):
        """Test constrained routing correctly identifies the 3 approved intents."""
        # Intent 1: clients at risk
        client_questions = [
            "Which clients are at risk and why?",
            "Which clients are partially served?",
            "Which clients are not fully served?",
            "Why is C02 at risk?",
            "Which customers have shortages?",
            "Who is shorted and why?",
        ]
        for q in client_questions:
            result = route_intent(q)
            self.assertIsNotNone(result, f"Failed to route: {q}")
            intent, tool = result
            self.assertEqual(intent, INTENT_CLIENTS_AT_RISK)
            self.assertEqual(tool, "get_clients_at_risk")

        # Intent 2: farm / segment gaps
        farm_questions = [
            "Which farm/segment gaps matter most today?",
            "Which farm gaps matter most today?",
            "Which farms are short?",
            "Where are the biggest production gaps?",
            "Which segments are causing shortages?",
            "What are today's biggest supply gaps?",
            "Which farm/segment shortages matter?",
        ]
        for q in farm_questions:
            result = route_intent(q)
            self.assertIsNotNone(result, f"Failed to route: {q}")
            intent, tool = result
            self.assertEqual(intent, INTENT_FARM_SEGMENT_GAPS)
            self.assertEqual(tool, "get_farm_segment_gaps")

        # Intent 3: local residual value
        local_questions = [
            "Why are 60t going local and what is their estimated value?",
            "Why are 60 t going local and what is their estimated value?",
            "Why are 60t going local?",
            "Why is fruit going to the local market?",
            "How much is going local?",
            "What is the value of the local residual?",
            "Why didn't all the apples get exported?",
            "What is the estimated value of the local tonnes?",
        ]
        for q in local_questions:
            result = route_intent(q)
            self.assertIsNotNone(result, f"Failed to route: {q}")
            intent, tool = result
            self.assertEqual(intent, INTENT_LOCAL_RESIDUAL_VALUE)
            self.assertEqual(tool, "get_local_residual_value")

    def test_1_grounded_supported_answer_clients_at_risk(self):
        """Test 1: Grounded answer for clients at risk with valid IDs."""
        mock_ollama = MagicMock(spec=OllamaClient)
        mock_ollama.is_configured.return_value = True
        mock_ollama.model = "test-model"
        mock_ollama.generate_explanation.return_value = json.dumps({
            "answer": "3 clients are at risk: C02 and C09 face segment shortages, while C08 was constrained by station capacity.",
            "evidence": [
                {"type": "client", "id": "C02"},
                {"type": "client", "id": "C08"},
                {"type": "client", "id": "C09"},
            ],
        })

        service = AssistantService(ollama_client=mock_ollama)
        status, resp = service.answer_question("Which clients are at risk and why?", self.plan)

        self.assertEqual(status, 200)
        self.assertEqual(resp["mode"], "ai")
        self.assertEqual(resp["intent"], INTENT_CLIENTS_AT_RISK)
        self.assertTrue(resp["ok"])
        self.assertIn("C02", resp["answer"])
        
        # Verify evidence contains only real client IDs
        known_clients = {c.client_id for c in self.plan.clients}
        for item in resp["evidence"]:
            self.assertEqual(item["type"], "client")
            self.assertIn(item["id"], known_clients)

    def test_2_farm_segment_question(self):
        """Test 2: Farm/segment gaps with valid farm/segment identifiers."""
        mock_ollama = MagicMock(spec=OllamaClient)
        mock_ollama.is_configured.return_value = True
        mock_ollama.model = "test-model"
        mock_ollama.generate_explanation.return_value = json.dumps({
            "answer": "The main production gap is Segment A at 60t below plan, with F02 having a 20t deficit in Segment C.",
            "evidence": [
                {"type": "segment", "id": "A"},
                {"type": "farm", "id": "F02"},
                {"type": "segment", "id": "C"},
            ],
        })

        service = AssistantService(ollama_client=mock_ollama)
        status, resp = service.answer_question("Which farm/segment gaps matter most today?", self.plan)

        self.assertEqual(status, 200)
        self.assertEqual(resp["mode"], "ai")
        self.assertEqual(resp["intent"], INTENT_FARM_SEGMENT_GAPS)
        
        known_farms = {f["farm_id"] for f in self.plan.farms}
        known_segments = {"A", "B", "C", "D"}

        for item in resp["evidence"]:
            if item["type"] == "farm":
                self.assertIn(item["id"], known_farms)
            elif item["type"] == "segment":
                self.assertIn(item["id"], known_segments)

    def test_3_local_residual_question(self):
        """Test 3: Local residual tonnes/value using current deterministic values."""
        mock_ollama = MagicMock(spec=OllamaClient)
        mock_ollama.is_configured.return_value = True
        mock_ollama.model = "test-model"
        mock_ollama.generate_explanation.return_value = json.dumps({
            "answer": f"{self.plan.local_t:.0f}t go local because the export station reached its 500t capacity limit. The local residual value is EUR {self.plan.local_value_eur:,.0f}.",
            "evidence": [
                {"type": "farm", "id": "F03"},
                {"type": "segment", "id": "D"},
            ],
        })

        service = AssistantService(ollama_client=mock_ollama)
        status, resp = service.answer_question("Why are 60t going local and what is their estimated value?", self.plan)

        self.assertEqual(status, 200)
        self.assertEqual(resp["mode"], "ai")
        self.assertEqual(resp["intent"], INTENT_LOCAL_RESIDUAL_VALUE)
        self.assertIn(str(int(self.plan.local_t)), resp["answer"])
        self.assertIn(f"{self.plan.local_value_eur:,.0f}", resp["answer"])

    def test_4_unsupported_question(self):
        """Test 4: Rejects non-analytical or modification requests."""
        unsupported_questions = [
            "Write Python code for me.",
            "What is the weather?",
            "Change the allocation.",
            "Optimize the plan.",
            "What should I do tomorrow?",
            "Calculate a new scenario.",
            "Write a poem.",
            "Delete C02.",
            "Change farm F01.",
        ]
        service = AssistantService()
        for q in unsupported_questions:
            status, resp = service.answer_question(q, self.plan)
            self.assertEqual(status, 400, f"Question was not rejected: {q}")
            self.assertFalse(resp["ok"])
            self.assertEqual(resp["status"], "unsupported")
            self.assertEqual(resp["error"], "unsupported_question")
            self.assertIn("I can only explain", resp["message"])

    def test_5_unknown_evidence_id(self):
        """Test 5: Hallucinated evidence ID (e.g. C99) is rejected and triggers fallback."""
        mock_ollama = MagicMock(spec=OllamaClient)
        mock_ollama.is_configured.return_value = True
        mock_ollama.model = "test-model"
        # Ollama hallucinates unknown client ID C99
        mock_ollama.generate_explanation.return_value = json.dumps({
            "answer": "C99 is at risk of shortage.",
            "evidence": [{"type": "client", "id": "C99"}],
        })

        service = AssistantService(ollama_client=mock_ollama)
        status, resp = service.answer_question("Which clients are at risk and why?", self.plan)

        self.assertEqual(status, 200)
        # Must fall back to deterministic summary and NOT output C99 as evidence
        self.assertEqual(resp["mode"], "deterministic")
        self.assertEqual(resp["status"], "fallback")
        self.assertEqual(resp["provider_error"], "invalid_model_output")
        for item in resp["evidence"]:
            self.assertNotEqual(item["id"], "C99")

    def test_6_ollama_unavailable(self):
        """Test 6: Handles connection failure with deterministic fallback."""
        mock_ollama = MagicMock(spec=OllamaClient)
        mock_ollama.is_configured.return_value = True
        mock_ollama.generate_explanation.side_effect = OllamaConnectionError("Connection refused")

        service = AssistantService(ollama_client=mock_ollama)
        status, resp = service.answer_question("Which clients are at risk and why?", self.plan)

        self.assertEqual(status, 200)
        self.assertEqual(resp["mode"], "deterministic")
        self.assertEqual(resp["status"], "fallback")
        self.assertEqual(resp["provider_error"], "ollama_unavailable")
        self.assertIn("deterministic summary", resp["answer"].lower())
        self.assertIn("unavailable", resp["provider_state"].lower())

    def test_7_ollama_timeout(self):
        """Test 7: Handles timeout with deterministic fallback."""
        mock_ollama = MagicMock(spec=OllamaClient)
        mock_ollama.is_configured.return_value = True
        mock_ollama.generate_explanation.side_effect = OllamaTimeoutError("Timed out")

        service = AssistantService(ollama_client=mock_ollama)
        status, resp = service.answer_question("Why are 60t going local and what is their estimated value?", self.plan)

        self.assertEqual(status, 200)
        self.assertEqual(resp["mode"], "deterministic")
        self.assertEqual(resp["status"], "fallback")
        self.assertEqual(resp["provider_error"], "provider_timeout")
        self.assertIn("timed out", resp["provider_state"].lower())

    def test_8_read_only_boundary(self):
        """Test 8: Verify assistant is strictly read-only and never mutates planning context."""
        plan_copy = copy.deepcopy(self.plan)

        service = AssistantService()
        # Call with various questions
        service.answer_question("Which clients are at risk and why?", self.plan)
        service.answer_question("Which farm/segment gaps matter most today?", self.plan)
        service.answer_question("Why are 60t going local and what is their estimated value?", self.plan)
        service.answer_question("Write Python code for me.", self.plan)

        # Assert no mutations occurred to self.plan
        self.assertEqual(self.plan.expected_total_t, plan_copy.expected_total_t)
        self.assertEqual(self.plan.actual_total_t, plan_copy.actual_total_t)
        self.assertEqual(self.plan.exported_t, plan_copy.exported_t)
        self.assertEqual(self.plan.local_t, plan_copy.local_t)
        self.assertEqual(self.plan.export_revenue_eur, plan_copy.export_revenue_eur)
        self.assertEqual(self.plan.local_value_eur, plan_copy.local_value_eur)
        self.assertEqual(len(self.plan.allocations), len(plan_copy.allocations))
        self.assertEqual(len(self.plan.clients), len(plan_copy.clients))
        self.assertEqual(len(self.plan.local_residuals), len(plan_copy.local_residuals))

    def test_deterministic_fallback_when_not_configured(self):
        """Test fallback when OLLAMA_MODEL is empty."""
        client = OllamaClient(base_url="http://localhost:11434", model="")
        service = AssistantService(ollama_client=client)

        status, resp = service.answer_question("Which clients are at risk and why?", self.plan)
        self.assertEqual(status, 200)
        self.assertEqual(resp["mode"], "deterministic")
        self.assertEqual(resp["provider_error"], "not_configured")
        self.assertIn("not configured", resp["provider_state"].lower())

    def test_deterministic_fallback_uses_server_result(self):
        """Test that deterministic fallback accurately reflects server numbers without hardcoding."""
        facts, valid_entities = get_local_residual_value(self.plan)
        answer, evidence = generate_deterministic_fallback("local_residual_value", facts)

        self.assertIn(f"{self.plan.local_t:.1f}", answer)
        self.assertIn(f"{self.plan.local_value_eur:,.0f}", answer)
        self.assertIn(f"{self.plan.station_capacity_t:.0f}", answer)


if __name__ == "__main__":
    unittest.main()
