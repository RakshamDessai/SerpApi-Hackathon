"""Stage 1: syllabus -> Competency[].

`extract_competencies` is the only entry point the pipeline uses. It prefers
Claude and silently degrades to the heuristic table-driven path, so a missing or
rate-limited Anthropic key costs quality, never availability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from s2s.extract import heuristic
from s2s.ingest.loader import RawSyllabus
from s2s.ingest.structure import CurriculumNode
from s2s.models import Competency

log = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    competencies: list[Competency]
    mode: str                 # "claude" | "heuristic"
    note: str | None = None   # why we fell back, for the UI


def extract_competencies(
    syllabus: RawSyllabus,
    tree: CurriculumNode,
    api_key: str | None = None,
    semester: int | None = None,
    limit: int = 6,
) -> ExtractionResult:
    if api_key:
        try:
            from s2s.extract import llm

            competencies = llm.extract(
                syllabus, tree, api_key=api_key, semester=semester, limit=limit
            )
            return ExtractionResult(competencies=competencies, mode="claude")
        except Exception as exc:                 # LLMUnavailable or anything else
            log.warning("LLM extraction unavailable, falling back: %s", exc)
            note = f"Claude unavailable ({exc}); used the heuristic extractor."
    else:
        note = "No ANTHROPIC_API_KEY set; used the heuristic extractor."

    competencies = heuristic.extract(syllabus, tree, semester=semester, limit=limit)
    return ExtractionResult(competencies=competencies, mode="heuristic", note=note)
