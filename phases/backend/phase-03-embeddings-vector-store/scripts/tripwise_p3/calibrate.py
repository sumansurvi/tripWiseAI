"""Suggest TRIPWISE_CHAT_MIN_SCORE from in-corpus vs out-of-corpus retrieve scores."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Sequence

from sqlalchemy.orm import Session

from tripwise_p3.embedding_client import EmbeddingClient
from tripwise_p3.retrieve import retrieve

REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_CASES_PATH = (
    REPO_ROOT
    / "phases"
    / "backend"
    / "phase-10-rag-evaluation"
    / "fixtures"
    / "eval_cases.json"
)


@dataclass
class GateRow:
    case_id: str
    question: str
    kind: str
    best_score: float
    best_title: str


@dataclass
class GateSuggestion:
    suggested: float
    in_floor: Optional[float]
    out_ceil: Optional[float]
    in_count: int
    out_count: int
    rows: List[GateRow]


def suggest_min_score(
    in_scores: Sequence[float],
    out_scores: Sequence[float],
) -> float:
    """Pick a gate between the weakest in-corpus hit and strongest out-of-corpus hit."""
    if not in_scores:
        return 0.50
    in_floor = min(in_scores)
    out_ceil = max(out_scores) if out_scores else max(0.0, in_floor - 0.10)
    if in_floor > out_ceil:
        return round((in_floor + out_ceil) / 2.0, 2)
    return round(min(out_ceil + 0.02, 0.99), 2)


def _load_cases(path: Path) -> List[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


def calibrate_gate(
    session: Session,
    client: EmbeddingClient,
    *,
    cases_path: Optional[Path] = None,
    top_k: int = 5,
) -> GateSuggestion:
    path = cases_path or DEFAULT_CASES_PATH
    cases = _load_cases(path)
    rows: List[GateRow] = []
    in_scores: List[float] = []
    out_scores: List[float] = []

    for raw in cases:
        if raw.get("expect_refuse"):
            continue
        question = (raw.get("question") or "").strip()
        if not question:
            continue
        expect_absent = bool(raw.get("expect_absent"))
        expect_titles = list(raw.get("expect_titles") or [])
        if not expect_absent and not expect_titles:
            continue
        hits = retrieve(session, client, question, top_k=top_k)
        best = hits[0] if hits else None
        score = float(best.score) if best is not None else 0.0
        title = best.title if best is not None else ""
        kind = "out" if expect_absent else "in"
        rows.append(
            GateRow(
                case_id=str(raw.get("id") or ""),
                question=question,
                kind=kind,
                best_score=score,
                best_title=title,
            )
        )
        if expect_absent:
            out_scores.append(score)
        else:
            in_scores.append(score)

    suggested = suggest_min_score(in_scores, out_scores)
    return GateSuggestion(
        suggested=suggested,
        in_floor=min(in_scores) if in_scores else None,
        out_ceil=max(out_scores) if out_scores else None,
        in_count=len(in_scores),
        out_count=len(out_scores),
        rows=rows,
    )


def suggestion_to_jsonable(result: GateSuggestion) -> dict[str, Any]:
    return {
        "suggested_min_score": result.suggested,
        "in_corpus_min": result.in_floor,
        "out_of_corpus_max": result.out_ceil,
        "in_count": result.in_count,
        "out_count": result.out_count,
        "note": (
            "Set TRIPWISE_CHAT_MIN_SCORE to suggested_min_score after a full "
            "re-embed with the active provider. Mixing Gemini and bge vectors "
            "makes these scores meaningless."
        ),
        "rows": [
            {
                "id": r.case_id,
                "kind": r.kind,
                "best_score": round(r.best_score, 4),
                "best_title": r.best_title,
                "question": r.question,
            }
            for r in result.rows
        ],
    }
