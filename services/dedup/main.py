"""
Точка входа сервиса dedup. Работает независимо от ingestion — свой
процесс, свой цикл — чтобы дедуп можно было прогонять чаще/реже и
масштабировать отдельно (см. БЛОК 1 — сервисы должны быть независимо
масштабируемыми).
"""

import os
import time

from services.dedup.hash import run_dedup_pass
from shared.logging import get_logger

os.environ.setdefault("SERVICE_NAME", "dedup")
logger = get_logger(__name__)

POLL_INTERVAL_SECONDS = int(os.environ.get("DEDUP_POLL_INTERVAL", "120"))


def main() -> None:
    logger.info(f"Dedup service starting, poll interval = {POLL_INTERVAL_SECONDS}s")
    while True:
        try:
            run_dedup_pass()
        except Exception as e:
            logger.error(f"Dedup pass failed: {e}", exc_info=True)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
