from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import load_config

from .prefilter import prefilter
from .scorers import StoryText, dup_risk_score, novelty_score, relevance_score

log = logging.getLogger("ranking.engine")

CONFIG_PATH = Path(__file__).parent / "weights.yaml"


@dataclass
class Ranked:
    story_id: int
    title: str
    relevance: float = 0.5
    novelty: float = 1.0
    dup_risk: float = 0.0
    final_score: float = 0.0
    decision: str = "hold"
    reason: str = ""
    topic: str = ""
    nearest_story_id: int | None = None
    degraded: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


class RankingEngine:
    def __init__(self, router=None, config_path: Path = CONFIG_PATH):
        cfg = load_config(config_path)
        self.w = cfg["weights"]
        self.t = cfg["thresholds"]
        self.g = cfg["gates"]
        self.router = router
        total = sum(self.w.values())
        if abs(total - 1.0) > 0.001:
            log.warning("сумма весов %.3f вместо 1.0", total)

    def score(self, candidate, history, published, body: str = "") -> Ranked:
        r = Ranked(story_id=candidate.story_id, title=candidate.title)

        # Самое дешёвое — правила по заголовку, до любых вычислений.
        passed, why = prefilter(candidate.title)
        if not passed:
            r.decision, r.reason = "drop", why
            return r

        r.novelty, r.nearest_story_id = novelty_score(candidate, history)
        r.dup_risk, dup_with = dup_risk_score(candidate, published)

        if r.dup_risk >= self.g["dup_risk_block"]:
            r.decision = "drop"
            r.reason = f"дубль опубликованного (story {dup_with}, {r.dup_risk:.2f})"
            return r

        if self.router is not None:
            cls = relevance_score(self.router, candidate.title, body)
            r.relevance = cls["relevance"]
            r.topic = cls["topic"]
            r.degraded = cls["degraded"]
            if self.g["blocklist_enabled"] and cls["blocklisted"]:
                r.decision = "drop"
                r.reason = f"blocklist: {cls['reason']}"
                return r
            r.extra["classify_reason"] = cls["reason"]

        r.final_score = round(
            self.w["relevance"] * r.relevance
            + self.w["novelty"] * r.novelty
            + self.w["dup_risk_inverted"] * (1.0 - r.dup_risk),
            4,
        )

        if r.degraded:
            r.decision, r.reason = "moderate", "скор получен без LLM"
        elif r.final_score >= self.t["auto_publish"]:
            r.decision, r.reason = "publish", f"score {r.final_score:.2f}"
        elif r.final_score < self.t["hold_below"]:
            r.decision, r.reason = "hold", f"score {r.final_score:.2f} ниже порога"
        else:
            r.decision, r.reason = "moderate", f"пограничный score {r.final_score:.2f}"
        return r

    def score_batch(self, candidates, published, bodies=None):
        bodies = bodies or {}
        history = candidates + published
        out = [self.score(c, history, published, bodies.get(c.story_id, "")) for c in candidates]
        out.sort(key=lambda x: x.final_score, reverse=True)
        return out
