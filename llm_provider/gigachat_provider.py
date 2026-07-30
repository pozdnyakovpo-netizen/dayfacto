"""GigaChat как провайдер.

Важно: существующий chat-bot не трогаем — он живёт своей жизнью в отдельном
процессе. Здесь только новый, независимый клиент для editorial/critique.
"""

from __future__ import annotations

import os
import time
import uuid

import requests

from .base import BaseProvider, LLMPermanentError, LLMRequest, LLMTransientError

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


class GigaChatProvider(BaseProvider):
    name = "gigachat"

    def __init__(
        self,
        auth_key: str | None = None,
        model: str = "GigaChat-Pro",
        scope: str | None = None,
        verify_ssl: bool | str = True,
        timeout: int = 60,
    ):
        self.auth_key = auth_key or os.environ.get("GIGACHAT_AUTH_KEY", "")
        if not self.auth_key:
            raise LLMPermanentError("GIGACHAT_AUTH_KEY не задан")
        self.model = model
        self.scope = scope or os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.verify_ssl = verify_ssl   # у Сбера свой CA — путь к сертификату сюда
        self.timeout = timeout
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._session = requests.Session()

    # ------------------------------------------------------------------
    def _access_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        try:
            r = self._session.post(
                OAUTH_URL,
                headers={
                    "Authorization": f"Basic {self.auth_key}",
                    "RqUID": str(uuid.uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"scope": self.scope},
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        except requests.RequestException as exc:
            raise LLMTransientError(f"OAuth недоступен: {exc}") from exc

        if r.status_code in (401, 403):
            raise LLMPermanentError(f"OAuth отверг ключ: {r.status_code} {r.text[:200]}")
        if r.status_code >= 400:
            raise LLMTransientError(f"OAuth ошибка {r.status_code}: {r.text[:200]}")

        payload = r.json()
        self._token = payload["access_token"]
        # expires_at приходит в миллисекундах
        self._token_exp = payload.get("expires_at", 0) / 1000 or time.time() + 1500
        return self._token

    # ------------------------------------------------------------------
    def _complete(self, req: LLMRequest) -> tuple[str, int, int]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        }
        try:
            r = self._session.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {self._access_token()}",
                    "Content-Type": "application/json",
                    "X-Request-ID": str(uuid.uuid4()),
                },
                json=body,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        except requests.RequestException as exc:
            raise LLMTransientError(f"Сетевая ошибка GigaChat: {exc}") from exc

        if r.status_code == 401:
            self._token = None                       # протух — следующий retry обновит
            raise LLMTransientError("GigaChat 401, токен сброшен")
        if r.status_code == 429 or r.status_code >= 500:
            raise LLMTransientError(f"GigaChat {r.status_code}: {r.text[:200]}")
        if r.status_code >= 400:
            raise LLMPermanentError(f"GigaChat {r.status_code}: {r.text[:200]}")

        payload = r.json()
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMTransientError(f"Неожиданная форма ответа GigaChat: {exc}") from exc

        usage = payload.get("usage", {})
        return text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
