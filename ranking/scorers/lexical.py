from __future__ import annotations

from dataclasses import dataclass

from ..text_utils import jaccard, overlap_coefficient, tokenize


@dataclass(frozen=True)
class StoryText:
    story_id: int
    title: str

    def tokens(self) -> set[str]:
        return tokenize(self.title)


def _max_similarity(target: set[str], others: list[set[str]]) -> tuple[float, int]:
    best, best_idx = 0.0, -1
    for i, other in enumerate(others):
        sim = max(jaccard(target, other), overlap_coefficient(target, other))
        if sim > best:
            best, best_idx = sim, i
    return best, best_idx


def novelty_score(candidate: StoryText, history: list[StoryText]):
    tokens = candidate.tokens()
    if not tokens:
        return 0.5, None
    rest = [h for h in history if h.story_id != candidate.story_id]
    if not rest:
        return 1.0, None
    sim, idx = _max_similarity(tokens, [h.tokens() for h in rest])
    nearest = rest[idx] if idx >= 0 else None
    return round(1.0 - sim, 4), (nearest.story_id if nearest else None)


def dup_risk_score(candidate: StoryText, published: list[StoryText]):
    if not published:
        return 0.0, None
    tokens = candidate.tokens()
    if not tokens:
        return 0.0, None
    sim, idx = _max_similarity(tokens, [p.tokens() for p in published])
    nearest = published[idx] if idx >= 0 else None
    return round(sim, 4), (nearest.story_id if nearest else None)
