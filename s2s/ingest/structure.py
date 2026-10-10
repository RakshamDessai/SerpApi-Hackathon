"""Stage 0b: decompose raw syllabus text into Course -> Semester -> Unit -> topics.

Tuned for the formats actually used by Indian university syllabi: "Unit I",
"Unit-3", "Module 2", "Paper BCH-301", "Semester III". Character offsets are
preserved on every node so the UI can highlight the exact unit that qualified a
student for an opportunity (Feature 22).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ROMAN = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6,
    "vii": 7, "viii": 8, "ix": 9, "x": 10,
}

UNIT_RE = re.compile(
    r"^\s*(?:unit|module|chapter)\s*[-–:.\s]*\s*"
    r"(?P<num>\d{1,2}|[ivx]{1,4})\b\s*[-–:.)]?\s*(?P<title>.*)$",
    re.IGNORECASE,
)

SEMESTER_RE = re.compile(
    r"^\s*semester\s*[-–:.\s]*\s*(?P<num>\d{1,2}|[ivx]{1,4})\b\s*(?P<title>.*)$",
    re.IGNORECASE,
)

COURSE_RE = re.compile(
    r"^\s*(?:paper|course|subject)\s*[-–:.\s]*\s*(?P<title>.{3,120})$",
    re.IGNORECASE,
)

NOISE_RE = re.compile(
    r"^\s*(?:references?|suggested readings?|text ?books?|reference books?|"
    r"examination|marks|credits?|total|note\s*:|outcomes?|objectives?)\b",
    re.IGNORECASE,
)


def _to_int(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return ROMAN.get(token)


@dataclass
class CurriculumNode:
    kind: str                      # "root" | "course" | "semester" | "unit"
    label: str
    number: int | None = None
    start: int = 0
    end: int = 0
    children: list["CurriculumNode"] = field(default_factory=list)
    body: str = ""

    def iter_units(self):
        if self.kind == "unit":
            yield self
        for child in self.children:
            yield from child.iter_units()

    @property
    def unit_count(self) -> int:
        return sum(1 for _ in self.iter_units())


def parse(text: str) -> CurriculumNode:
    """Build a curriculum tree. Always returns a root, even if nothing matched."""
    root = CurriculumNode(kind="root", label="Syllabus", start=0, end=len(text))

    lines: list[tuple[int, str]] = []
    offset = 0
    for line in text.split("\n"):
        lines.append((offset, line))
        offset += len(line) + 1

    current_course: CurriculumNode | None = None
    current_semester: CurriculumNode | None = None
    current_unit: CurriculumNode | None = None

    def close(node: CurriculumNode | None, end: int) -> None:
        if node is not None and node.end <= node.start:
            node.end = end

    for pos, line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        unit_match = UNIT_RE.match(stripped)
        if unit_match and not NOISE_RE.match(stripped):
            number = _to_int(unit_match.group("num"))
            title = unit_match.group("title").strip(" -:.–")
            label = f"Unit {number}" if number else "Unit"
            if title:
                label = f"{label}: {title}"

            close(current_unit, pos)
            current_unit = CurriculumNode(
                kind="unit", label=label, number=number, start=pos, end=0
            )
            parent = current_semester or current_course or root
            parent.children.append(current_unit)
            continue

        semester_match = SEMESTER_RE.match(stripped)
        if semester_match:
            number = _to_int(semester_match.group("num"))
            close(current_unit, pos)
            current_unit = None
            close(current_semester, pos)
            current_semester = CurriculumNode(
                kind="semester",
                label=f"Semester {number}" if number else stripped[:80],
                number=number,
                start=pos,
                end=0,
            )
            (current_course or root).children.append(current_semester)
            continue

        course_match = COURSE_RE.match(stripped)
        if course_match and current_unit is None:
            close(current_semester, pos)
            close(current_course, pos)
            current_course = CurriculumNode(
                kind="course",
                label=course_match.group("title").strip(),
                start=pos,
                end=0,
            )
            current_semester = None
            root.children.append(current_course)
            continue

        if current_unit is not None:
            current_unit.body += (" " if current_unit.body else "") + stripped

    end = len(text)
    for node in (current_unit, current_semester, current_course):
        close(node, end)

    # Nothing matched: treat the whole document as one unit so the pipeline
    # still has something to work with.
    if root.unit_count == 0:
        root.children.append(
            CurriculumNode(
                kind="unit",
                label="Full syllabus",
                start=0,
                end=len(text),
                body=text[:4000],
            )
        )

    _fill_ends(root, len(text))
    return root


def _fill_ends(node: CurriculumNode, document_end: int) -> None:
    for index, child in enumerate(node.children):
        following = (
            node.children[index + 1].start
            if index + 1 < len(node.children)
            else min(node.end or document_end, document_end)
        )
        if child.end <= child.start:
            child.end = following
        _fill_ends(child, document_end)


def unit_spans(text: str, tree: CurriculumNode) -> list[tuple[str, str, int]]:
    """[(unit label, verbatim unit text, start offset)] for the extract stage."""
    spans = []
    for unit in tree.iter_units():
        span = text[unit.start:unit.end].strip()
        if span:
            spans.append((unit.label, span, unit.start))
    return spans
