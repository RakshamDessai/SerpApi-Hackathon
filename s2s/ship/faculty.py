"""Stage 6e: the faculty credit report (Feature 53).

Many Indian universities give internal marks for practical work. This is a
one-page PDF a student hands a professor to ask for them: what the work was,
which syllabus unit it applies, the verbatim syllabus text, how S2S checked
the listing, and a space for the professor's decision and signature.

Every statement in it comes from data the pipeline holds. The student fills
in only what S2S cannot know (their name, roll number and what they did), and
the report says plainly which fields the student wrote.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from s2s.mesh import adapters as adapter_registry
from s2s.models import VERDICT_LABEL, Opportunity

#: Core PDF fonts are Latin-1 only. These are the characters real listings
#: and syllabi use that it lacks.
_REPLACEMENTS = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", "·": "-",
    "₹": "Rs. ", "•": "-", " ": " ", "→": "->",
}


def _latin1(text: str) -> str:
    for bad, good in _REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", errors="replace").decode("latin-1")


@dataclass
class StudentDetails:
    """What only the student can supply. Blank fields print as blank lines."""

    name: str = ""
    roll_number: str = ""
    institution: str = ""
    course: str = ""
    semester: int | None = None
    work_summary: str = ""
    hours_spent: str = ""


def report_pdf(opportunity: Opportunity, student: StudentDetails) -> bytes:
    """The one-page report as PDF bytes."""
    from fpdf import FPDF

    adapter = adapter_registry.ADAPTERS.get(opportunity.adapter_key)
    platform = adapter.label if adapter else opportunity.adapter_key
    competency = opportunity.matched_competency

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()
    width = pdf.w - 36
    # fpdf2's multi_cell leaves the cursor to the RIGHT of the block by
    # default, which stacks every later block in a narrow right-hand column.
    down = {"new_x": "LMARGIN", "new_y": "NEXT"}

    def heading(text: str) -> None:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.multi_cell(width, 6, _latin1(text), **down)
        pdf.set_font("Helvetica", "", 10)

    def line(label: str, value: str) -> None:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(42, 6, _latin1(label))
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(width - 42, 6, _latin1(value or "_" * 40), **down)

    def para(text: str, italic: bool = False) -> None:
        pdf.set_font("Helvetica", "I" if italic else "", 10)
        pdf.multi_cell(width, 5.5, _latin1(text), **down)
        pdf.set_font("Helvetica", "", 10)

    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(width, 8, "Request for internal practical credit", **down)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(width, 5, _latin1(f"Prepared {date.today():%d %B %Y} with S2S "
                                     "(Syllabus-to-Ship)"), **down)

    heading("1. Student (written by the student)")
    line("Name", student.name)
    line("Roll number", student.roll_number)
    line("Institution", student.institution)
    line("Course", student.course)
    line("Semester", str(student.semester) if student.semester else "")

    heading("2. The work")
    line("Title", opportunity.title)
    line("Platform", platform)
    if opportunity.organization:
        line("Organisation", opportunity.organization)
    line("Link", opportunity.url)
    if opportunity.est_hours:
        line("Expected effort", opportunity.effort_label)
    line("Hours spent", student.hours_spent)

    heading("3. The syllabus unit it applies")
    line("Unit", competency.source_unit)
    line("Skill", competency.canonical)
    para("Verbatim text from the syllabus:")
    para('"' + " ".join(competency.source_span.split()) + '"', italic=True)

    heading("4. How the listing was checked")
    checked = (f" at {opportunity.verified_at:%d %b %Y %H:%M}"
               if opportunity.verified_at else "")
    para(f"Status when found: {VERDICT_LABEL[opportunity.verdict]}{checked}. "
         f"Match score {opportunity.score.total}% (semantic alignment, level fit, "
         "freshness and actionability). S2S checks a listing by its URL, its "
         "search snippet and, where possible, the platform's own status data. "
         "It does not check the quality of the student's work.")

    heading("5. What the student did (written by the student)")
    para(student.work_summary or "\n\n\n")

    heading("6. Faculty decision")
    para("Credit given:   [ ] Yes    [ ] No    Marks: ________ of ________")
    pdf.ln(2)
    para("Remarks: ______________________________________________________________")
    pdf.ln(6)
    para("Faculty name and signature: ______________________   Date: ____________")

    return bytes(pdf.output())


def filename_for(opportunity: Opportunity) -> str:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in opportunity.title)
    slug = "-".join(part for part in slug.split("-") if part)[:50]
    return f"credit-request-{slug or 'work'}.pdf"
