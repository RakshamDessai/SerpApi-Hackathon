"""Stage 6a: the Ship Blueprint - a 3-phase execution playbook.

Features 28, 30, 31 and 35. Deterministic and template-driven: a student
staring at an unfamiliar brief needs concrete first steps, and a template that
always works beats an LLM call that sometimes does not.

Playbooks are keyed by discipline because "how do I actually start" differs
completely between a cash-flow model and a logo. Within a discipline the steps
are deliberately generic enough to fit any brief in that family.
"""

from __future__ import annotations

from s2s.models import Competency, Discipline, Opportunity, ShipBlueprint

D = Discipline

# discipline -> (setup, execution, delivery, pitfalls)
PLAYBOOKS: dict[Discipline, tuple[list[str], list[str], list[str], list[str]]] = {
    D.COMMERCE_FINANCE: (
        [
            "Open a blank Google Sheet. Create tabs: Inputs, Workings, Output.",
            "Ask the organisation for 2-3 years of financials, or the latest "
            "balance sheet and P&L. If they have none, ask for bank statements.",
            "List every assumption on the Inputs tab with a source next to it.",
        ],
        [
            "Build the workings tab first: never hard-code a number into a formula.",
            "Compute the core metric the brief asks for, then sanity-check it "
            "against a prior period.",
            "Add a one-line sensitivity check: what happens if the main driver "
            "moves plus or minus 10 percent?",
            "Write a 3-bullet summary of what the numbers actually mean.",
        ],
        [
            "Export a 1-page PDF summary plus the live sheet (view access).",
            "Lead with the answer, not the method.",
            "Record a 3-minute Loom walking through the Inputs tab.",
        ],
        [
            "Hard-coded numbers inside formulas - the single most common reason "
            "a model gets rejected as unauditable.",
            "Presenting ratios without a benchmark or prior period to compare against.",
        ],
    ),
    D.DESIGN_VISUAL: (
        [
            "Create a Figma file with pages: Research, Explorations, Final, Handoff.",
            "Collect 10-15 reference images and the organisation's existing assets.",
            "Confirm where the output will be used: print, screen, or both.",
        ],
        [
            "Produce 3 distinct directions, not 3 variations of one idea.",
            "Set a type scale and a 4- or 8-point spacing grid before refining.",
            "Check colour contrast against WCAG AA for any text.",
            "Refine only the direction the client picks.",
        ],
        [
            "Export SVG plus PNG at 1x/2x, and CMYK PDF if it will be printed.",
            "Write a 1-page usage guide: clear space, minimum size, do and do not.",
            "Package everything in one folder with an obvious naming scheme.",
        ],
        [
            "Delivering raster-only files - the client cannot resize a PNG logo.",
            "Showing three near-identical options, which gives the client nothing "
            "real to choose between.",
        ],
    ),
    D.CS_SOFTWARE: (
        [
            "Fork and clone the repository. Read CONTRIBUTING.md before anything else.",
            "Reproduce the issue locally and paste the exact steps into the thread.",
            "Comment on the issue to claim it before you start writing code.",
        ],
        [
            "Write a failing test that captures the bug, then make it pass.",
            "Keep the diff minimal: match the surrounding style, no drive-by refactors.",
            "Run the full test suite and the linter the project actually uses.",
            "Write a commit message that explains why, not what.",
        ],
        [
            "Open a PR linking the issue, with before/after evidence.",
            "Respond to review comments within 48 hours.",
            "The merged PR is your proof of work - it is public and permanent.",
        ],
        [
            "Reformatting files you did not need to touch, which buries the real "
            "change and usually gets the PR closed.",
            "Going silent after review feedback.",
        ],
    ),
    D.DATA_QUANT: (
        [
            "Open a Google Colab notebook; load the dataset and print its shape.",
            "Read the data dictionary and the evaluation metric before modelling.",
            "Split train/validation immediately, before any exploration.",
        ],
        [
            "Do EDA first: missing values, distributions, obvious leakage.",
            "Build a trivial baseline (mean or majority class) and record its score.",
            "Only then try a real model, and compare against that baseline.",
            "Log every experiment: what you changed, and what the score did.",
        ],
        [
            "Publish the notebook with narrative markdown, not bare cells.",
            "State the final metric against the baseline in the first cell.",
            "Push the notebook to GitHub as portfolio evidence.",
        ],
        [
            "Data leakage - fitting any transform before the train/test split is "
            "the classic way to get an impressive score that means nothing.",
            "Reporting accuracy on an imbalanced dataset.",
        ],
    ),
    D.ARTS_HUMANITIES: (
        [
            "Write the research question in one sentence before designing anything.",
            "Draft the instrument (interview guide or questionnaire) in Google Docs.",
            "Check whether consent or ethical clearance is needed.",
        ],
        [
            "Pilot with 2-3 people and revise - this always changes the instrument.",
            "Collect data, keeping identifiers separate from responses.",
            "Code transcripts openly first, then group codes into themes.",
            "Keep a short memo of decisions so the analysis is reproducible.",
        ],
        [
            "Write up: question, method, findings, limitations.",
            "Add a 1-page policy brief for the non-academic reader.",
            "Share anonymised data or the codebook alongside the report.",
        ],
        [
            "Leading or double-barrelled questions, which quietly invalidate "
            "the whole dataset.",
            "Reporting quotes without saying how many participants expressed the view.",
        ],
    ),
    D.LAW_POLICY: (
        [
            "Get the current version of the document under review.",
            "List the specific clauses or obligations in scope.",
            "Identify the governing jurisdiction before reading anything.",
        ],
        [
            "Review clause by clause against a checklist; do not freestyle.",
            "Flag each issue as high, medium or low risk with a reason.",
            "Draft suggested replacement wording, not just objections.",
        ],
        [
            "Deliver a tracked-changes document plus a 1-page risk summary.",
            "State clearly that this is student work and not legal advice.",
        ],
        [
            "Giving an opinion that reads as legal advice - always add the caveat.",
            "Flagging problems without proposing wording the client can actually use.",
        ],
    ),
    D.LIFE_SCIENCES: (
        [
            "Open a Colab notebook and install Biopython.",
            "Download the dataset and verify record counts against the source.",
            "Note the organism, assembly or assay version.",
        ],
        [
            "Parse and validate the input before analysing anything.",
            "Run the analysis on a small subset first to check it behaves.",
            "Record software versions and parameters for reproducibility.",
        ],
        [
            "Publish a notebook with figures and a methods paragraph.",
            "Deposit intermediate files with a README.",
        ],
        [
            "Not recording tool versions, which makes the result irreproducible.",
            "Over-interpreting a correlation in observational data.",
        ],
    ),
    D.MEDIA_COMM: (
        [
            "Clarify the audience and the single message in one sentence.",
            "Gather quotes, figures and images, with sources for each.",
        ],
        [
            "Draft a headline and standfirst before the body.",
            "Write, then cut 20 percent.",
            "Fact-check every number and name against a primary source.",
        ],
        [
            "Deliver the copy plus a short social cut-down.",
            "Supply a sources list alongside the draft.",
        ],
        [
            "Publishing an unverified figure - one wrong number costs the "
            "organisation its credibility.",
        ],
    ),
    D.ENG_MECHANICAL: (
        [
            "Install FreeCAD. Confirm the units and tolerances expected.",
            "Collect existing drawings or reference dimensions.",
        ],
        [
            "Model parametrically so dimensions can be changed later.",
            "Check interferences and constraints before detailing.",
            "Produce a dimensioned 2D drawing from the 3D model.",
        ],
        [
            "Export STEP for the model plus a PDF drawing sheet.",
            "Include a short bill of materials.",
        ],
        [
            "Delivering a non-parametric model that nobody can modify.",
        ],
    ),
}

GENERIC = (
    [
        "Re-read the brief and write down the single deliverable in one sentence.",
        "Message the organisation to confirm scope and deadline before starting.",
        "Set up one folder or document where all the work will live.",
    ],
    [
        "Break the deliverable into three checkable milestones.",
        "Complete a rough version of all three before polishing any one of them.",
        "Share progress at the halfway point rather than going dark.",
    ],
    [
        "Package the output in the format the brief asked for.",
        "Write a short covering note: what you did, what you assumed, what is next.",
    ],
    [
        "Starting work before scope is agreed in writing.",
    ],
)

TOOLKIT_FALLBACK = ["Google Docs", "Google Sheets", "GitHub"]


def _playbook(competency: Competency):
    for discipline in competency.disciplines:
        if discipline in PLAYBOOKS:
            return PLAYBOOKS[discipline]
    return GENERIC


def build(opportunity: Opportunity) -> ShipBlueprint:
    """A 3-phase plan the student can start on today."""
    competency = opportunity.matched_competency
    setup, execution, delivery, pitfalls = _playbook(competency)

    toolkit = list(competency.tools) or list(TOOLKIT_FALLBACK)

    # Lead the setup phase with the tools they already know from the syllabus.
    first = f"Tools you already use for this unit: {', '.join(toolkit)}."
    return ShipBlueprint(
        setup=[first, *setup],
        execution=list(execution),
        delivery=list(delivery),
        toolkit=toolkit,
        pitfalls=list(pitfalls),
    )
