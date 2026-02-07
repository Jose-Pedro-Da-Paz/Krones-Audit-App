# app/calculator.py
from typing import Dict, List, Optional, Tuple
from .model import Topic, Group, Question

SCORE_MAP = {100: 1.0, 75: 0.75, 50: 0.5, 25: 0.25, 0: 0.0}
NA_TOKENS = {"NA", "N.A.", "N.A", "N/A"}

def _weighted_avg(pairs: List[Tuple[float, float]]) -> Optional[float]:
    num = sum(v * w for v, w in pairs)
    den = sum(w for _, w in pairs)
    return (num / den) if den > 0 else None

def group_score(group: Group, answers: Dict[str, str]) -> Optional[float]:
    pairs = []
    for q in group.questions:
        raw = answers.get(q.id)
        if raw is None or str(raw).upper() in NA_TOKENS:
            continue
        val = int(raw)
        if val not in SCORE_MAP:
            continue
        pairs.append((SCORE_MAP[val], q.weight))
    return _weighted_avg(pairs)

def topic_score(topic: Topic, answers: Dict[str, str]) -> Optional[float]:
    pairs = []
    for g in topic.groups:
        gs = group_score(g, answers)
        if gs is not None:
            pairs.append((gs, g.weight))
    return _weighted_avg(pairs)

def final_score(topics: List[Topic], answers: Dict[str, str]) -> Optional[float]:
    pairs = []
    for t in topics:
        ts = topic_score(t, answers)
        if ts is not None:
            pairs.append((ts, t.weight))
    return _weighted_avg(pairs)