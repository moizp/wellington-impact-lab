"""Frontier reference via the Anthropic Messages API (docs/paper_plan.md 5.1).

Uses httpx (already a backend dependency). The key comes from ANTHROPIC_API_KEY and is never
written anywhere. Untested here: needs network access and an account with the model enabled.
Temperature 0 is requested; hosted models are not guaranteed deterministic, hence the plan's
3 repeats."""

import os
import time

import httpx

from . import Backend, Generation

_URL = "https://api.anthropic.com/v1/messages"


class AnthropicBackend(Backend):
    def __init__(self, model: str, timeout: float = 120.0, **_):
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.name = f"anthropic:{model}"
        self._model = model
        self._client = httpx.Client(
            timeout=timeout,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        )

    def generate(self, system, user, shots=None, example=None, max_new_tokens=160):
        messages = []
        for u, a in shots or []:
            messages += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
        messages.append({"role": "user", "content": user})
        body = {"model": self._model, "max_tokens": max_new_tokens, "temperature": 0.0,
                "system": system, "messages": messages}
        t0 = time.perf_counter()
        r = self._client.post(_URL, json=body)
        dt = time.perf_counter() - t0
        r.raise_for_status()
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage", {})
        return Generation(
            text=text,
            truncated=data.get("stop_reason") == "max_tokens",
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            seconds=dt,  # includes network: reported on its own axis, never merged with local latency
        )

    def close(self):
        self._client.close()
