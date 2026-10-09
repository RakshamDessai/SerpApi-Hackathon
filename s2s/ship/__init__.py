"""Stage 6: turn a selected opportunity into something shippable.

Generated lazily, per card, when the student expands it - producing a bridge and
blueprint for every result would waste tokens on cards nobody opens.
"""

from __future__ import annotations

from s2s.models import Opportunity
from s2s.ship import blueprint as blueprint_module
from s2s.ship import bridge as bridge_module
from s2s.ship import export as export_module


def prepare(
    opportunity: Opportunity,
    api_key: str | None = None,
    syllabus_text: str = "",
) -> Opportunity:
    """Fill in `bridge`, `blueprint` and `star_bullet` in place.

    Named `prepare` rather than `ship` so `from s2s.ship import prepare` cannot
    be confused with the package itself.
    """
    if opportunity.blueprint is None:
        opportunity.blueprint = blueprint_module.build(opportunity)

    if opportunity.bridge is None:
        result = bridge_module.build(
            opportunity, api_key=api_key, syllabus_text=syllabus_text
        )
        opportunity.bridge = result.text

    if opportunity.star_bullet is None:
        opportunity.star_bullet = export_module.star_bullet(opportunity)

    return opportunity


__all__ = ["prepare", "bridge_module", "blueprint_module", "export_module"]
