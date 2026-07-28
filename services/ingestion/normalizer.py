"""
Нормализация текста raw_item ПОСЛЕ сбора, ДО дедупа/кластеризации:
убираем HTML-теги источника, лишние пробелы, служебные "читайте нас в...".
Отдельный шаг (а не встроенный в фетчеры), чтобы dedup/clustering всегда
получали текст в едином, предсказуемом виде независимо от источника.
"""

import html
import re

SOURCE_MENTION_PATTERNS = [
    r"https?://\S+",
    r"читайте\s+(далее|полностью|на сайте)[^.!?]*[.!?]?",
    r"подпис(ывайтесь|ка)\s+на\s+(наш\s+)?канал[^.!?]*[.!?]?",
    r"скачайте?\s+(наше\s+)?приложение[^.!?]*[.!?]?",
]


def normalize_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = html.unescape(raw_text)
    text = re.sub(r"<[^>]+>", " ", text)
    for pattern in SOURCE_MENTION_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def normalize_raw_item(title: str, body: str) -> tuple[str, str]:
    return normalize_text(title), normalize_text(body)
