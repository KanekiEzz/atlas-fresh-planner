"""Environment and availability checker for Ollama in Atlas Fresh."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def check_ollama() -> int:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "").strip()

    print("=== Atlas Fresh Planning Assistant: Ollama Environment ===")
    print(f"OLLAMA_BASE_URL : {base_url}")
    if model:
        print(f"OLLAMA_MODEL    : {model}")
    else:
        print("OLLAMA_MODEL    : [NOT SET] (Assistant will use deterministic fallback)")

    endpoints = [f"{base_url}/api/tags"]
    if "://localhost:" in base_url:
        endpoints.append(base_url.replace("://localhost:", "://127.0.0.1:") + "/api/tags")

    connected = False
    models_list = []

    for ep in endpoints:
        try:
            req = urllib.request.Request(ep, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                connected = True
                models_list = [m.get("name", "") for m in data.get("models", [])]
                break
        except Exception:
            continue

    if not connected:
        print("\n[STATUS] Ollama server is NOT running or unreachable.")
        print("To enable AI explanations, start Ollama locally:")
        print("   1. ollama serve")
        print("   2. export OLLAMA_MODEL=mistral:latest")
        print("   3. make backend")
        print("\nNOTE: Atlas Fresh will run normally and automatically use grounded")
        print("deterministic summaries while Ollama is unavailable.")
        return 0

    print("\n[STATUS] Ollama server is running and reachable.")
    models_str = ", ".join(models_list) if models_list else "None"
    print(f"Available models: {models_str}")

    if model:
        matched = any(
            m == model
            or m.startswith(model + ":")
            or model.startswith(m.split(":")[0])
            for m in models_list
        )
        if matched:
            print(f"[STATUS] Configured model '{model}' is installed and ready.")
        else:
            print(f"[WARNING] Configured model '{model}' was not found in installed models.")
            print(f"         Run: ollama pull {model}")
            print("         (The assistant will use deterministic fallback until model is available)")
    else:
        print("[INFO] Set OLLAMA_MODEL to enable AI explanations (e.g. export OLLAMA_MODEL=mistral:latest).")

    return 0


if __name__ == "__main__":
    sys.exit(check_ollama())
