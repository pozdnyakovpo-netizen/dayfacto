"""
Общий retry-декоратор с экспоненциальным backoff — используется всеми
сервисами для сетевых вызовов (Telegram API, GigaChat/Claude, RSS-фиды).
"""

import functools
import random
import time
from typing import Callable, Tuple, Type

from shared.logging import get_logger

logger = get_logger(__name__)


def retry_with_backoff(
    max_attempts: int = 4,
    base_delay: float = 1.5,
    max_delay: float = 30.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
):
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_attempts:
                        break
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay) + random.uniform(0, 0.5)
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e} — retry in {delay:.1f}s"
                    )
                    time.sleep(delay)
            raise last_exc

        return wrapper

    return decorator
