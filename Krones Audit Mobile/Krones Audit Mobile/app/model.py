# app/model.py
from dataclasses import dataclass
from typing import List, Dict, Any
import json
from pathlib import Path

@dataclass
class Question:
    id: str
    weight: float
    title: Dict[str, str]

@dataclass
class Group:
    id: str
    weight: float  # no Excel: 1
    title: Dict[str, str]
    questions: List[Question]

@dataclass
class Topic:
    id: str
    weight: float
    title: Dict[str, str]
    groups: List[Group]

@dataclass
class Schema:
    languages: List[str]
    topics: List[Topic]

def load_schema(path: Path) -> Schema:
    data = json.loads(path.read_text(encoding="utf-8"))
    topics: List[Topic] = []
    for t in data["topics"]:
        groups: List[Group] = []
        for g in t["groups"]:
            questions = [
                Question(id=q["id"], weight=float(q["weight"]), title=q["title"])
                for q in g.get("questions", [])
            ]
            groups.append(Group(
                id=g["id"],
                weight=float(g.get("weight", 1)),
                title=g["title"],
                questions=questions
            ))
        topics.append(Topic(
            id=t["id"],
            weight=float(t["weight"]),
            title=t["title"],
            groups=groups
        ))
    return Schema(languages=data.get("languages", []), topics=topics)