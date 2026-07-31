from __future__ import annotations

import json
import os

import requests

from .base import BaseProvider, LLMRequest, LLMPermanentError, LLMTransientError

API = ("https://generativelanguage.googleapis.com/v1beta/models/"
       "%s:generateContent")


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None,
                 model: str = "gemini-2.5-flash", timeout: int = 90):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise LLMPermanentError("GEMINI_API_KEY не задан")
        self.model = model
        self.timeout = timeout
        self._session = requests.Session()

    def _complete(self, req: LLMRequest) -> tuple[str, int, int]:
        body = {
            "contents": [{"role": "user", "parts": [{"text": req.user}]}],
            "generationConfig": {
                "temperature": req.temperature,
                "maxOutputTokens": req.max_tokens,
            },
        }
        if req.system:
            body["systemInstruction"] = {"parts": [{"text": req.system}]}
        if req.json_schema is not None:
            body["generationConfig"]["responseMimeType"] = "application/json"

        try:
            r = self._session.post(
                API % self.model,
                params={"key": self.api_key},
                headers={"content-type": "application/json"},
                json=body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMTransientError("Сетевая ошибка Gemini: %s" % exc) from exc

        if r.status_code in (429, 500, 502, 503, 504):
            raise LLMTransientError("Gemini %s: %s" % (r.status_code, r.text[:200]))
        if r.status_code >= 400:
            raise LLMPermanentError("Gemini %s: %s" % (r.status_code, r.text[:200]))
        return self._parse(r.json())

    @staticmethod
    def _parse(d: dict) -> tuple[str, int, int]:
        cands = d.get("candidates") or []
        if not cands:
            raise LLMTransientError("Gemini: пустой ответ %s" % str(d)[:200])
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise LLMTransientError("Gemini: ответ без текста")
        u = d.get("usageMetadata") or {}
        return (text,
                int(u.get("promptTokenCount") or 0),
                int(u.get("candidatesTokenCount") or 0))

    def health(self) -> bool:
        return bool(self.api_key)
