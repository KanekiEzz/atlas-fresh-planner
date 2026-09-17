"""Ollama HTTP client for Atlas Fresh Planning Assistant.

Communicates with local Ollama instance server-side via standard library urllib.
Handles timeouts, connection failures, model unavailability, and simulation flags.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class OllamaAssistantError(Exception):
    """Base error for Ollama assistant interactions."""
    def __init__(self, message: str, error_code: str = "provider_error"):
        super().__init__(message)
        self.error_code = error_code


class OllamaNotConfiguredError(OllamaAssistantError):
    def __init__(self, message: str = "Ollama model is not configured."):
        super().__init__(message, "not_configured")


class OllamaConnectionError(OllamaAssistantError):
    def __init__(self, message: str = "Ollama server is unavailable or connection refused."):
        super().__init__(message, "ollama_unavailable")


class OllamaTimeoutError(OllamaAssistantError):
    def __init__(self, message: str = "Ollama request timed out."):
        super().__init__(message, "provider_timeout")


class OllamaProviderError(OllamaAssistantError):
    def __init__(self, message: str = "Ollama provider error."):
        super().__init__(message, "provider_error")


class OllamaMalformedResponseError(OllamaAssistantError):
    def __init__(self, message: str = "Ollama returned malformed or unexpected response."):
        super().__init__(message, "invalid_model_output")


class OllamaClient:
    """Client for server-side Ollama communication."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url if base_url is not None else os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model if model is not None else os.getenv("OLLAMA_MODEL", "").strip()
        env_timeout = os.getenv("OLLAMA_TIMEOUT", "120.0")
        try:
            self.timeout = float(timeout if timeout is not None else env_timeout)
        except ValueError:
            self.timeout = 120.0

    def is_configured(self) -> bool:
        """Check if Ollama base url and model are provided."""
        return bool(self.base_url and self.model)

    def generate_explanation(self, system_prompt: str, user_prompt: str) -> str:
        """Send prompt to Ollama and return the raw model message content."""
        # Check simulation hooks for automated testing
        simulation = os.getenv("ATLAS_ASSISTANT_SIMULATE", "").strip().lower()
        if simulation == "timeout":
            raise OllamaTimeoutError("Simulated Ollama timeout.")
        if simulation == "unavailable":
            raise OllamaConnectionError("Simulated Ollama connection failure.")
        if simulation == "invalid":
            return '{"answer": "C99 is shorted.", "evidence": [{"type": "client", "id": "C99"}]}'

        if not self.is_configured():
            raise OllamaNotConfiguredError(
                "Ollama is not configured. OLLAMA_MODEL environment variable must be set."
            )

        endpoints = [f"{self.base_url}/api/chat"]
        if "://localhost:" in self.base_url:
            endpoints.append(self.base_url.replace("://localhost:", "://127.0.0.1:") + "/api/chat")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,
            },
        }

        req_data = json.dumps(payload).encode("utf-8")
        last_connection_exc = None

        for endpoint in endpoints:
            req = urllib.request.Request(
                endpoint,
                data=req_data,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    resp_bytes = resp.read()
                    try:
                        resp_json = json.loads(resp_bytes.decode("utf-8"))
                    except json.JSONDecodeError as exc:
                        raise OllamaMalformedResponseError("Invalid JSON in Ollama HTTP response") from exc

                    message = resp_json.get("message", {})
                    content = message.get("content", "")
                    if not content and "response" in resp_json:
                        content = resp_json["response"]

                    if not content:
                        raise OllamaMalformedResponseError("Ollama response contains empty content")

                    return str(content)

            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    raise OllamaProviderError(
                        f"Ollama model '{self.model}' not found or /api/chat not supported (HTTP 404)."
                    ) from exc
                error_body = ""
                try:
                    error_body = exc.read().decode("utf-8")
                except Exception:
                    pass
                raise OllamaProviderError(f"Ollama HTTP {exc.code} error: {error_body or exc.reason}") from exc

            except TimeoutError as exc:
                raise OllamaTimeoutError(f"Ollama request timed out after {self.timeout}s: {exc}") from exc

            except (urllib.error.URLError, ConnectionRefusedError, OSError) as exc:
                if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError):
                    raise OllamaTimeoutError(f"Ollama connection timed out: {exc.reason}") from exc
                last_connection_exc = exc
                continue

        raise OllamaConnectionError(f"Cannot connect to Ollama at {self.base_url}: {last_connection_exc}")
