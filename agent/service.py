"""Assistant service orchestrating routing, tools, Ollama interaction, and fallback."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from .fallback import generate_deterministic_fallback
from .ollama_client import (
    OllamaAssistantError,
    OllamaClient,
    OllamaConnectionError,
    OllamaNotConfiguredError,
    OllamaTimeoutError,
)
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .router import route_intent
from .tools import run_tool
from .validation import OutputValidationError, validate_ai_response


class AssistantService:
    """Read-only Planning Assistant service."""

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.ollama_client = ollama_client or OllamaClient()

    def answer_question(self, question: str, plan: Any) -> Tuple[int, Dict[str, Any]]:
        """Process an analytical question against current planning data.
        
        Returns (http_status_code, response_payload).
        """
        # Route intent
        routed = route_intent(question)
        if routed is None:
            return 400, {
                "status": "unsupported",
                "ok": False,
                "mode": "deterministic",
                "error": "unsupported_question",
                "message": (
                    "I can only explain:\n"
                    "• clients at risk\n"
                    "• farm/segment supply gaps\n"
                    "• local residual tonnes and value"
                ),
                "evidence": [],
            }

        intent, tool_name = routed

        # Extract deterministic facts using approved tool
        try:
            facts, valid_entities = run_tool(tool_name, plan)
        except Exception as exc:
            return 500, {
                "status": "error",
                "ok": False,
                "mode": "deterministic",
                "error": "tool_error",
                "message": f"Failed to extract planning facts: {exc}",
                "evidence": [],
            }

        # Check if Ollama is configured
        if not self.ollama_client.is_configured():
            provider_state = "Ollama is not configured. Showing a deterministic summary instead."
            answer, evidence = generate_deterministic_fallback(
                intent, facts, provider_reason=provider_state
            )
            return 200, {
                "status": "fallback",
                "ok": True,
                "mode": "deterministic",
                "intent": intent,
                "provider_error": "not_configured",
                "provider_state": provider_state,
                "answer": answer,
                "evidence": evidence,
            }

        # Attempt AI explanation with Ollama
        user_prompt = build_user_prompt(question, facts)
        try:
            raw_output = self.ollama_client.generate_explanation(SYSTEM_PROMPT, user_prompt)
            answer, evidence = validate_ai_response(raw_output, valid_entities, intent)
            model_name = self.ollama_client.model or "Ollama"

            return 200, {
                "status": "success",
                "ok": True,
                "mode": "ai",
                "intent": intent,
                "provider_state": f"AI Assistant ({model_name})",
                "answer": answer,
                "evidence": evidence,
            }

        except OllamaNotConfiguredError:
            provider_state = "Ollama is not configured. Showing a deterministic summary instead."
            answer, evidence = generate_deterministic_fallback(intent, facts, provider_state)
            return 200, {
                "status": "fallback",
                "ok": True,
                "mode": "deterministic",
                "intent": intent,
                "provider_error": "not_configured",
                "provider_state": provider_state,
                "answer": answer,
                "evidence": evidence,
            }

        except OllamaTimeoutError:
            provider_state = "The AI assistant timed out. Showing a deterministic summary instead."
            answer, evidence = generate_deterministic_fallback(intent, facts, provider_state)
            return 200, {
                "status": "fallback",
                "ok": True,
                "mode": "deterministic",
                "intent": intent,
                "provider_error": "provider_timeout",
                "provider_state": provider_state,
                "answer": answer,
                "evidence": evidence,
            }

        except OllamaConnectionError:
            provider_state = "Ollama is currently unavailable. Showing a deterministic summary instead."
            answer, evidence = generate_deterministic_fallback(intent, facts, provider_state)
            return 200, {
                "status": "fallback",
                "ok": True,
                "mode": "deterministic",
                "intent": intent,
                "provider_error": "ollama_unavailable",
                "provider_state": provider_state,
                "answer": answer,
                "evidence": evidence,
            }

        except OutputValidationError as exc:
            provider_state = f"The AI response could not be validated ({exc}). Showing a deterministic summary instead."
            answer, evidence = generate_deterministic_fallback(
                intent, facts, "The AI response could not be validated. Showing a deterministic summary instead."
            )
            return 200, {
                "status": "fallback",
                "ok": True,
                "mode": "deterministic",
                "intent": intent,
                "provider_error": "invalid_model_output",
                "provider_state": provider_state,
                "answer": answer,
                "evidence": evidence,
            }

        except Exception as exc:
            provider_state = f"Unexpected provider error: {exc}. Showing a deterministic summary instead."
            answer, evidence = generate_deterministic_fallback(intent, facts, provider_state)
            return 200, {
                "status": "fallback",
                "ok": True,
                "mode": "deterministic",
                "intent": intent,
                "provider_error": "unexpected_error",
                "provider_state": provider_state,
                "answer": answer,
                "evidence": evidence,
            }


# Module-level singleton (re-created on first call and on explicit reset)
_default_service: Optional[AssistantService] = None


def get_assistant_service() -> AssistantService:
    global _default_service
    if _default_service is None:
        _default_service = AssistantService()
    return _default_service


def reset_assistant_service() -> None:
    """Force the next call to create a fresh service (picks up new env vars)."""
    global _default_service
    _default_service = None


def assistant_answer(question: str, plan: Any) -> Tuple[int, Dict[str, Any]]:
    """Helper entrypoint for backend server.

    A fresh AssistantService (and OllamaClient) is built on every request so
    that changes to OLLAMA_MODEL / OLLAMA_TIMEOUT env vars are always respected
    without restarting the backend.
    """
    return AssistantService().answer_question(question, plan)
