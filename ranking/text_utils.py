from __future__ import annotations

import re

STOPWORDS = {
    "в", "во", "на", "с", "со", "по", "за", "из", "от", "до", "к", "ко", "у",
    "о", "об", "обо", "для", "при", "над", "под", "про", "без", "через",
    "и", "а", "но", "или", "что", "как", "это", "все", "уже", "еще", "ещё",
    "не", "ни", "же", "бы", "ли", "то", "так", "там", "тут", "был", "была",
    "было", "были", "будет", "быть", "его", "ее", "её", "их", "он", "она",
    "они", "мы", "вы", "я", "тот", "та", "те", "этот", "эта", "эти",
}

_WORD = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)

_SUFFIXES = (
    "ами", "ями", "ого", "его", "ому", "ему", "ыми", "ими", "ой", "ей",
    "ая", "яя", "ое", "ее", "ые", "ие", "ов", "ев", "ом", "ем", "ах", "ях",
    "ую", "юю", "ам", "ям", "ы", "и", "а", "я", "о", "е", "у", "ю",
)
MIN_STEM = 4


def stem(word: str) -> str:
    for suf in _SUFFIXES:
        if len(word) - len(suf) >= MIN_STEM and word.endswith(suf):
            return word[: -len(suf)]
    return word


def tokenize(text: str) -> set[str]:
    out: set[str] = set()
    for raw in _WORD.findall((text or "").lower()):
        if raw in STOPWORDS or len(raw) < 3:
            continue
        out.add(stem(raw))
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def overlap_coefficient(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))
