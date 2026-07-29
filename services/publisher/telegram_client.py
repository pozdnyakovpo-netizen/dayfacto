from __future__ import annotations

import logging
import os

_PROXY = os.environ.get('TELEGRAM_PROXY', '')
_PROXIES = {'http': _PROXY, 'https': _PROXY} if _PROXY else None
import time

import requests

log = logging.getLogger("publisher.telegram")
API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    pass


class TelegramClient:
    def __init__(self, token: str | None = None, timeout: int = 30):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not self.token:
            raise TelegramError("TELEGRAM_BOT_TOKEN не задан")
        self.timeout = timeout
        self.s = requests.Session()

    def _call(self, method: str, **params) -> dict:
        url = API.format(token=self.token, method=method)
        for attempt in range(1, 4):
            try:
                r = self.s.post(url, json=params, timeout=self.timeout, proxies=_PROXIES)
            except requests.RequestException as exc:
                if attempt == 3:
                    raise TelegramError(f"сеть: {exc}") from exc
                time.sleep(2 ** attempt)
                continue

            data = r.json()
            if data.get("ok"):
                return data["result"]

            if r.status_code == 429:
                wait = data.get("parameters", {}).get("retry_after", 5)
                log.warning("rate limit, пауза %s с", wait)
                time.sleep(wait + 1)
                continue

            desc = data.get("description") or r.text[:200]
            raise TelegramError(f"{method}: {desc}")

        raise TelegramError(f"{method}: исчерпаны попытки")

    def send(self, chat_id: str, text: str, silent: bool = False) -> int:
        res = self._call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            disable_notification=silent,
        )
        return res["message_id"]

    def me(self) -> str:
        return self._call("getMe").get("username", "?")
