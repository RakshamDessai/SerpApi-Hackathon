"""Features 32, 52, 53, 54: application message, LinkedIn post, faculty
report, daily alert. All deterministic, so every claim is checkable."""

from __future__ import annotations

from datetime import datetime

import pytest

from s2s.analyze import alerts
from s2s.models import Opportunity, ScoreBreakdown
from s2s.score.scorer import WEIGHTS
from s2s.ship import faculty, outreach


def _opportunity(competency, verdict="live", url="https://www.idealist.org/en/x",
                 total=0.8, organization="Health Access"):
    return Opportunity(
        title="Cash flow forecast for a clinic",
        url=url,
        snippet="Build a cash flow forecast in Excel.",
        adapter_key="idealist",
        matched_competency=competency,
        score=ScoreBreakdown(total, total, total, total, WEIGHTS),
        verdict=verdict,
        organization=organization,
        verified_at=datetime(2026, 10, 11, 9, 30),
    )


# ------------------------------------------------------ application message -

def test_application_message_quotes_the_syllabus_verbatim(competency):
    text = outreach.application_message(_opportunity(competency), "Asha Rao")
    assert f'"{competency.source_span}"' in text
    assert competency.source_unit in text
    assert '"Cash flow forecast for a clinic"' in text
    assert text.startswith("Hello Health Access,")
    assert text.rstrip().endswith("Asha Rao")


def test_application_message_has_a_placeholder_name(competency):
    text = outreach.application_message(_opportunity(competency, organization=None))
    assert text.startswith("Hello your team,")
    assert "[Your name]" in text


def test_long_span_is_cut_at_a_word_with_an_ellipsis(competency):
    long = competency.__class__(**{**competency.__dict__,
                                   "source_span": "Working capital analysis. " * 20})
    text = outreach.application_message(_opportunity(long))
    quoted = text.split('The syllabus says: "', 1)[1].split('"', 1)[0]
    assert quoted.endswith("...")
    assert " ".join(long.source_span.split()).startswith(quoted[:-3])


# ----------------------------------------------------------- LinkedIn post -

def test_linkedin_post_is_specific_and_past_tense(competency):
    text = outreach.linkedin_post(_opportunity(competency))
    first = text.splitlines()[0]
    assert len(first) <= outreach.HOOK_LIMIT
    assert "Health Access" in first and "used it" in first
    assert competency.source_unit in text
    assert "#WorkingCapitalManagement" in text


@pytest.mark.parametrize("phrase, tag", [
    ("Indexing, Storage and Query Optimisation", "#IndexingStorageQuery "),
    ("!!!", ""),
])
def test_hashtag_is_clean(phrase, tag):
    assert outreach._hashtag(phrase) == tag


# --------------------------------------------------- faculty credit report -

def test_faculty_report_is_a_pdf(competency):
    data = faculty.report_pdf(
        _opportunity(competency),
        faculty.StudentDetails(name="Asha Rao", roll_number="21BCOM042", semester=3),
    )
    assert data.startswith(b"%PDF")
    assert len(data) > 1000


def test_faculty_report_survives_non_latin1_text(competency):
    odd = competency.__class__(**{**competency.__dict__,
                                  "source_span": "Budget of ₹5 lakh — “quoted” · done…"})
    opportunity = _opportunity(odd)
    opportunity.title = "Résumé review → NGO ✓"
    assert faculty.report_pdf(opportunity, faculty.StudentDetails()).startswith(b"%PDF")


def test_latin1_keeps_meaning():
    assert faculty._latin1("₹500 — “ok”") == 'Rs. 500 - "ok"'


def test_faculty_filename_is_safe(competency):
    name = faculty.filename_for(_opportunity(competency))
    assert name == "credit-request-cash-flow-forecast-for-a-clinic.pdf"


# --------------------------------------------------------------- alerts ---

def test_only_new_live_listings_alert(competency):
    seen_live = _opportunity(competency, url="https://a.example/1")
    new_live = _opportunity(competency, url="https://a.example/2", total=0.9)
    unverified = _opportunity(competency, verdict="unverified", url="https://a.example/3")
    new = alerts.new_live([seen_live, new_live, unverified], seen={"https://a.example/1"})
    assert [o.url for o in new] == ["https://a.example/2"]


def test_alert_message_lists_the_best_first_and_counts_the_rest(competency):
    many = [_opportunity(competency, url=f"https://a.example/{i}", total=i / 10)
            for i in range(1, 6)]
    text = alerts.message(alerts.new_live(many, seen=set()), limit=2)
    assert text.startswith("S2S: 5 new live listings")
    assert text.index("https://a.example/5") < text.index("https://a.example/4")
    assert "https://a.example/3" not in text
    assert "+3 more in the app." in text


def test_no_news_is_an_empty_message():
    assert alerts.message([]) == ""
