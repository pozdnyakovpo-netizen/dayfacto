"""Контур памяти: связывание материалов в нормативные сюжеты."""
import re
import unicodedata

STOP = {"года", "году", "года", "решение", "приказ", "постановление",
        "федеральной", "россии", "российской", "федерации", "союза",
        "комиссии", "совета", "коллегии", "евразийского", "экономического"}

DOC_RE = re.compile(
    r"(решени[ея]|приказ|постановлени[ея]|распоряжени[ея]|соглашени[ея]|"
    r"федеральн\w+ закон)[^№]{0,80}?(?:от\s*(\d{2})\.(\d{2})\.(\d{4}))?"
    r"[^№]{0,30}№\s*([\d\-/А-Яа-яA-Za-z]+)", re.I)


def doc_key(doc_number: str) -> str:
    """Нормализованный ключ документа: вид + номер + год."""
    if not doc_number:
        return ""
    m = DOC_RE.search(doc_number)
    if not m:
        return ""
    kind = m.group(1).lower()[:6]
    year = m.group(4) or ""
    num = re.sub(r"\s+", "", m.group(5) or "").lower()
    return "%s-%s-%s" % (kind, num, year) if num else ""


def fingerprint(*texts) -> set:
    """Основы значимых слов для сравнения сюжетов."""
    t = " ".join(x or "" for x in texts).lower()
    t = unicodedata.normalize("NFKC", t)
    words = re.findall(r"[а-яёa-z]{6,}", t)
    return {w[:6] for w in words if w not in STOP}


def similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def slugify(title: str) -> str:
    t = re.sub(r"[^\w\s-]", "", (title or "").lower())
    t = re.sub(r"\s+", "-", t.strip())[:80]
    return t or "subject"


SOURCE_TIER = {"ФТС": 1.0, "ЕЭК": 1.0, "Правительство": 0.95,
               "Альта": 0.75, "ТГ — ФТС": 0.95, "ТГ — Альта": 0.7}


def source_tier(name: str) -> float:
    """Уровень источника: первоисточник или пересказ."""
    n = (name or "")
    for k, v in SOURCE_TIER.items():
        if n.startswith(k):
            return v
    return 0.5


def trust_index(change: dict, sources: list, has_doc_url: bool = False) -> float:
    """Индекс доверия 0..1: источник, реквизиты, подтверждения, документ."""
    tiers = [source_tier(s) for s in sources] or [0.4]
    best = max(tiers)
    independent = len({s.split("—")[0].strip() for s in sources}) if sources else 1

    score = 0.0
    score += 0.35 * best
    score += 0.20 * min(1.0, (independent - 1) / 2)
    if (change.get("doc_number") or "").strip():
        score += 0.20
    if change.get("date_status") == "exact":
        score += 0.15
    elif change.get("date_status") in ("relative", "conditional", "month"):
        score += 0.05
    if (change.get("scope") or "").strip():
        score += 0.05
    if has_doc_url:
        score += 0.05
    return round(min(1.0, score), 2)


EFFECT_WEIGHT = {
    "duty_rate": 1.0,        # деньги напрямую
    "preference": 0.9,
    "tnved_code": 0.85,
    "restriction": 0.85,     # запрет — риск непоставки
    "control": 0.7,          # досмотр, пломбы
    "procedure": 0.6,        # документооборот
    "currency_control": 0.6,
    "court_practice": 0.5,
    "rate_info": 0.4,
}

MONEY = ("пошлин", "ставк", "платеж", "акциз", "ндс", "сбор", "стоимост",
         "преференц", "льгот")
RISK = ("запрет", "ограничен", "приостанов", "отслежива", "пломб",
        "контрол", "досмотр", "маркиров")
PAPER = ("деклар", "сертифик", "документ", "разрешен", "уведомлен", "реестр")


def effect_index(change: dict) -> float:
    """Индекс практического эффекта 0..1."""
    base = EFFECT_WEIGHT.get(change.get("change_type") or "", 0.35)
    hay = " ".join([
        change.get("what") or "", change.get("scope") or "",
        change.get("impact_note") or "", change.get("goods") or "",
    ]).lower()

    score = 0.45 * base
    if change.get("impact") == "money":
        score += 0.20
    elif change.get("impact") in ("risk", "deadline"):
        score += 0.15

    if any(w in hay for w in MONEY):
        score += 0.12
    if any(w in hay for w in RISK):
        score += 0.10
    if any(w in hay for w in PAPER):
        score += 0.05

    if (change.get("value_new") or "").strip():
        score += 0.08
    if change.get("tnved_codes"):
        score += 0.05
    if change.get("date_status") == "exact":
        score += 0.05
    return round(min(1.0, score), 2)
