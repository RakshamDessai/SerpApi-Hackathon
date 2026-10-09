"""Registry integrity.

A malformed adapter fails silently at runtime - a bad regex drops every result
from that platform and looks like "the platform had no matches". These tests
make that loud.
"""

from __future__ import annotations

import re

import pytest

from s2s.mesh import adapters as registry
from s2s.mesh import affinity
from s2s.models import Discipline

ALL = registry.all_adapters()


@pytest.mark.parametrize("adapter", ALL, ids=lambda a: a.key)
def test_url_pattern_compiles(adapter):
    re.compile(adapter.url_pattern)


@pytest.mark.parametrize("adapter", ALL, ids=lambda a: a.key)
def test_dork_template_has_terms_placeholder(adapter):
    assert "{terms}" in adapter.dork, f"{adapter.key} dork cannot be filled"


@pytest.mark.parametrize("adapter", ALL, ids=lambda a: a.key)
def test_dork_renders_without_stray_braces(adapter):
    query = registry.render_query(adapter, ["cash flow forecast", "budget"])
    assert "{" not in query and "}" not in query
    assert '"cash flow forecast"' in query
    assert " OR " in query


@pytest.mark.parametrize("adapter", ALL, ids=lambda a: a.key)
def test_every_adapter_has_affinity_for_every_discipline(adapter):
    table = affinity.AFFINITY.get(adapter.key)
    assert table is not None, f"{adapter.key} missing from the affinity matrix"
    missing = [d.value for d in Discipline if d not in table]
    assert not missing, f"{adapter.key} missing affinity for {missing}"


@pytest.mark.parametrize("adapter", ALL, ids=lambda a: a.key)
def test_site_adapters_reference_their_own_domain(adapter):
    """A site: dork whose url_pattern points elsewhere drops 100% of results."""
    if adapter.engine != "google" or not adapter.site:
        pytest.skip("not a site: dork")
    root = adapter.site.split(".")[0]
    assert root in adapter.url_pattern, (
        f"{adapter.key}: url_pattern does not mention {adapter.site}"
    )


def test_tier_c_is_opt_in():
    for adapter in ALL:
        if adapter.trust == "C":
            assert not adapter.enabled_by_default, (
                f"{adapter.key} is tier C and must not be on by default"
            )


def test_active_excludes_tier_c_by_default():
    default_keys = {a.key for a in registry.active(include_tier_c=False)}
    tier_c_keys = {a.key for a in ALL if a.trust == "C"}
    assert not (default_keys & tier_c_keys)
    assert tier_c_keys <= {a.key for a in registry.active(include_tier_c=True)}


def test_keys_are_unique():
    keys = [a.key for a in ALL]
    assert len(keys) == len(set(keys))


def test_negatives_only_on_commercial_boards():
    """Negative keywords protect students from senior listings on job boards;
    they make no sense on a volunteering or competition page."""
    for adapter in ALL:
        if "{negatives}" in adapter.dork:
            assert adapter.ecosystem in {"freelance", "internship"}, adapter.key


# ------------------------------- gate-marker safety (2026-10-09) -----------

#: Substring matching over a 600 KB page means a short, common marker will
#: false-positive and wrongly archive live work. Anything this short must be a
#: deliberate, observed, structured token rather than an English word.
MIN_MARKER_CHARS = 12

#: Observed in a real page's embedded JSON rather than its prose, and verified
#: absent on open issues.
OBSERVED_STRUCTURED_MARKERS = {'"state":"closed"'}


@pytest.mark.parametrize("adapter", ALL, ids=lambda a: a.key)
def test_gate_markers_are_specific_enough(adapter):
    for marker in adapter.gate_markers:
        if marker in OBSERVED_STRUCTURED_MARKERS:
            continue
        assert len(marker) >= MIN_MARKER_CHARS, (
            f"{adapter.key}: gate marker {marker!r} is too generic - it will "
            f"match unrelated text and archive live opportunities"
        )


@pytest.mark.parametrize("adapter", ALL, ids=lambda a: a.key)
def test_gate_markers_are_lowercase(adapter):
    """`tier2_probe` lowercases the body, so an upper-case marker never fires."""
    for marker in adapter.gate_markers:
        assert marker == marker.lower(), f"{adapter.key}: {marker!r} must be lowercase"


def test_affinity_matrix_has_no_orphan_rows():
    """A row for a removed adapter is dead config that silently drifts."""
    from s2s.mesh import affinity
    orphans = set(affinity.AFFINITY) - {a.key for a in ALL}
    assert not orphans, f"affinity rows for adapters that no longer exist: {orphans}"
