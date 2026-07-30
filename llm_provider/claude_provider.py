"""Claude как второй, взаимозаменяемый провайдер.

Ставится флагом в system_config, а не переписыванием кода.
"""

from __future__ import annotations

import os

import requests

from .base import BaseProvider, LLMPermanentError, LLMRequest, LLMTransientError

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class ClaudeProvider(BaseProvider):
    name = "claude"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-5",
        timeout: int = 90,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise LLMPermanentError("ANTHROPIC_API_KEY не задан")
        self.model = model
        self.timeout = timeout
        self._session = requests.Session()

    def _complete(self, req: LLMRequest) -> tuple[str, int, int]:
        body = {
            "model": self.model,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "system": req.system,
            "messages": [{"role": "user", "content": req.user}],
        }
        # Префилл "{" резко повышает вероятность чистого JSON без преамбулы.
        if req.json_schema is not None:
            body["messages"].append({"role": "assistant", "content": "{"})

        try:
            r = self._session.post(
                API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": API_VERSION,
                    "content-type": "application/json",
                },
                json=body,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LLMTransientError(f"Сетевая ошибка Anthropic: {exc}") from exc

        if r.status_code in (429, 529) or r.status_code >= 500:
            raise LLMTransientError(f"Anthropic {r.status_code}: {r.text[:200]}")
        if r.status_code >= 400:
            raise LLMPermanentError(f"Anthropic {r.status_code}: {r.text[:200]}")

        payload = r.json()
        text = "".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        )
        if req.json_schema is not None and text.strip():
            text = "{" + text          # возвращаем откушенную префиллом скобку

        usage = payload.get("usage", {})
        return text, usage.get("input_tokens", 0), usage.get("output_tokens", 0)
