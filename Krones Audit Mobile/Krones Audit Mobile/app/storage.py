# app/storage.py
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from .model import Topic
from .calculator import topic_score, final_score

def _fmt_pct(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x * 100.0, 1)

def build_result(topics: List[Topic],
                 answers: Dict[str, str],
                 comments: Dict[str, str],
                 language: str,
                 auditor: Optional[str] = None) -> Dict[str, Any]:

    topic_entries: List[Dict[str, Any]] = []
    for t in topics:
        ts = topic_score(t, answers)
        topic_entries.append({
            "id": t.id,
            "weight": t.weight,
            "score": _fmt_pct(ts)
        })
    final = final_score(topics, answers)

    responses = []
    for qid, val in answers.items():
        responses.append({
            "id": qid,
            "value": val,
            "comment": comments.get(qid)
        })

    out = {
        "metadata": {
            "schema_version": "1.0",
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "auditor": auditor or "",
            "language": language
        },
        "responses": responses,
        "scores": {
            "topics": topic_entries,
            "final": _fmt_pct(final)
        }
    }
    return out

def save_json(user_data_dir: str, payload: Dict[str, Any]) -> Path:
    dst_dir = Path(user_data_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = dst_dir / f"auditoria_{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def share_file(path: Path) -> bool:
    """Tenta compartilhar o arquivo no Android. Retorna True/False."""
    try:
        from plyer import share
    except Exception:
        return False
    try:
        share.share(title="Resultado da Auditoria",
                    text="Segue o resultado da auditoria em JSON.",
                    filepath=str(path))
        return True
    except Exception:
        return False
