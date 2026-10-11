"""Feature 08: one semester, several subjects, read together."""

from __future__ import annotations

from datetime import datetime

import pytest

from s2s import pipeline
from s2s.config import FIXTURE_DIR, Settings
from s2s.ingest import loader, structure
from s2s.models import Competency, Discipline, RawResult
from s2s.score import scorer

DBMS = FIXTURE_DIR / "syllabi" / "vtu_cse_sem4_dbms.txt"
STATS = FIXTURE_DIR / "syllabi" / "sppu_bsc_stats_sem5_biostatistics.txt"


@pytest.fixture
def combined():
    return loader.combine([loader.from_fixture(DBMS), loader.from_fixture(STATS)])


def test_one_file_is_returned_unchanged():
    single = loader.from_fixture(DBMS)
    assert loader.combine([single]) is single
    assert structure.subject_count(structure.parse(single.text)) == 0


def test_subjects_become_separate_branches(combined):
    tree = structure.parse(combined.text)
    assert combined.subjects == 2
    assert structure.subject_count(tree) == 2
    units = list(tree.iter_units())
    assert len(units) == 10
    courses = {structure.course_of(tree, u.start) for u in units}
    assert courses == {"vtu cse sem4 dbms", "sppu bsc stats sem5 biostatistics"}


def test_same_unit_number_in_two_subjects_stays_distinct(combined):
    labels = [u.label for u in structure.parse(combined.text).iter_units()]
    assert len(labels) == len(set(labels))
    assert any(l.startswith("vtu cse sem4 dbms · Unit 1") for l in labels)


def test_a_paper_line_inside_a_subject_does_not_split_it():
    a = loader.from_text("Paper: Databases\nUnit 1: SQL\n" + "SQL joins and queries. " * 10,
                         source="dbms.txt")
    b = loader.from_text("Unit 1: Statistics\n" + "Regression and sampling. " * 10,
                         source="stats.txt")
    tree = structure.parse(loader.combine([a, b]).text)
    assert structure.subject_count(tree) == 2
    assert [c.kind for c in tree.children] == ["subject", "subject"]


def test_pipeline_balances_competencies_across_subjects(combined):
    settings = Settings.load()
    settings.demo_mode = True
    result = pipeline.run(combined, settings, semester=4)
    courses = [c.source_course for c in result.competencies]
    assert set(courses) == {"vtu cse sem4 dbms", "sppu bsc stats sem5 biostatistics"}
    # Round-robin: neither subject takes more than half plus one.
    assert max(courses.count(c) for c in set(courses)) <= len(courses) // 2 + 1


def test_single_syllabus_competencies_have_no_course():
    settings = Settings.load()
    settings.demo_mode = True
    result = pipeline.run(loader.from_fixture(DBMS), settings, semester=4)
    assert all(c.source_course == "" for c in result.competencies)


# ------------------------------------------------------- cross-subject card -

def _competency(name, course, aliases):
    return Competency(
        canonical=name, aliases=aliases, tools=[], disciplines=[Discipline.DATA_QUANT],
        bloom=4, band="intermediate", source_unit=f"{course} · Unit 1: {name}",
        source_span=name, source_course=course,
    )


SQL = _competency("SQL", "dbms", ["SQL query", "database"])
REGRESSION = _competency("Regression", "stats", ["regression analysis", "forecasting"])
TYPOGRAPHY = _competency("Typography", "design", ["typeface"])

BOTH = RawResult(
    title="Build a SQL database and a regression analysis for a health NGO",
    url="https://www.idealist.org/en/volunteer-opportunity/x",
    snippet="Write SQL query code and run regression analysis forecasting on clinic data.",
    adapter_key="idealist",
)


def test_listing_using_two_subjects_is_marked():
    [opportunity] = scorer.build_opportunities(
        [(BOTH, "live", None)], [SQL, REGRESSION, TYPOGRAPHY], now=datetime(2026, 10, 11))
    assert opportunity.cross_subject
    assert {opportunity.matched_competency.canonical,
            opportunity.also_competency.canonical} == {"SQL", "Regression"}


def test_weak_second_subject_is_not_claimed():
    only_sql = RawResult(title="SQL query clean-up", url=BOTH.url,
                         snippet="Fix one SQL query in our database.", adapter_key="idealist")
    [opportunity] = scorer.build_opportunities(
        [(only_sql, "live", None)], [SQL, REGRESSION], now=datetime(2026, 10, 11))
    assert not opportunity.cross_subject


def test_same_subject_never_pairs_with_itself():
    other_sql = _competency("Joins", "dbms", ["regression analysis", "forecasting"])
    [opportunity] = scorer.build_opportunities(
        [(BOTH, "live", None)], [SQL, other_sql], now=datetime(2026, 10, 11))
    assert not opportunity.cross_subject


def test_single_syllabus_never_claims_two_subjects():
    plain = [Competency(**{**c.__dict__, "source_course": ""}) for c in (SQL, REGRESSION)]
    [opportunity] = scorer.build_opportunities(
        [(BOTH, "live", None)], plain, now=datetime(2026, 10, 11))
    assert not opportunity.cross_subject
