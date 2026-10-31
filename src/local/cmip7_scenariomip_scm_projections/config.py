"""
Paths used by the manuscript's build

The build is driven by pytask (see `tasks/cmip7_scenariomip_scm_projections`).
These live here, rather than next to the tasks,
because pytask doesn't put the task modules' directories on the import path,
so the task modules can't import a module which sits next to them.
"""

from __future__ import annotations

from pathlib import Path

from local.cmip7_scenariomip_scm_projections.magicc_runs import (
    REPRODUCTION_CHECK_FILE,
    get_run_dir,
)
from local.cmip7_scenariomip_scm_projections.raw_data import get_raw_filename
from local.cmip7_scenariomip_scm_projections.scenarios import SCENARIOS, Scenario
from local.paths import (
    DATA_PROCESSED_DIR,
    DATA_RAW_DIR,
    FIGURES_DIR,
    REPO_ROOT,
    TABLES_DIR,
)

MANUSCRIPT_NAME = "cmip7-scenariomip-scm-projections"
"""Name of the manuscript, used for its directories and the output PDF"""

# Data
RAW_DATA_DIR = DATA_RAW_DIR / "ssp-submission"
"""Directory in which we save the raw scenario data"""


def get_raw_file(scenario: Scenario) -> Path:
    """Get the file which holds a scenario's raw data"""
    return RAW_DATA_DIR / get_raw_filename(scenario.marker)


RUNS_DIR = DATA_PROCESSED_DIR / "magicc-runs"
"""Directory in which each scenario's run is saved (one sub-directory each)"""

RUN_DIRS = tuple(get_run_dir(RUNS_DIR, s) for s in SCENARIOS)
"""Directory of each scenario's run"""

REPRODUCTION_CHECK_FILES = tuple(rd / REPRODUCTION_CHECK_FILE for rd in RUN_DIRS)
"""Each run's check that it reproduces the published results"""

SUMMARY_DIR = DATA_PROCESSED_DIR / "summary"
"""Directory in which we save summaries of the runs"""

WARMING_METRICS_QUANTILES = SUMMARY_DIR / "warming-metrics-quantiles.feather"
"""Quantiles of peak warming, warming in 2100 and warming in 2500"""

WARMING_TIMESERIES_QUANTILES = SUMMARY_DIR / "warming-timeseries-quantiles.feather"
"""Quantiles of the assessed GSAT timeseries"""

PEAK_YEAR_QUANTILES = SUMMARY_DIR / "peak-year-quantiles.feather"
"""Quantiles of the year of peak warming"""

# Manuscript sources
MANUSCRIPT_DIR = REPO_ROOT / "manuscripts" / MANUSCRIPT_NAME
"""Directory which holds the manuscript's source"""

ABSTRACT = MANUSCRIPT_DIR / "abstract.tex"
INTRODUCTION = MANUSCRIPT_DIR / "introduction.tex"
SECTIONS = (
    MANUSCRIPT_DIR / "methods.tex",
    MANUSCRIPT_DIR / "results.tex",
    MANUSCRIPT_DIR / "discussion.tex",
)
"""Body sections, in the order they appear"""

APPENDICES = (MANUSCRIPT_DIR / "appendices.tex",)
"""Appendices, in the order they appear"""

CONCLUSION = MANUSCRIPT_DIR / "conclusion.tex"
ACKNOWLEDGEMENTS = MANUSCRIPT_DIR / "acknowledgements.tex"
FUNDING = MANUSCRIPT_DIR / "funding.tex"
DATA_AVAILABILITY = MANUSCRIPT_DIR / "data-availability.tex"
METADATA = MANUSCRIPT_DIR / "metadata.toml"
REPLACEMENTS = MANUSCRIPT_DIR / "replacements.yaml"

REFERENCES_BIB = REPO_ROOT / "references" / "references.bib"

IOP_TEMPLATE_DIR = REPO_ROOT / "iop-latex-template"
CLEAN_IOP_TEMPLATE_FILENAME = "template_clean.tex"

# Generated tex inputs
FIGURES_OUT_DIR = FIGURES_DIR / MANUSCRIPT_NAME
TABLES_OUT_DIR = TABLES_DIR / MANUSCRIPT_NAME
BUILD_DIR = REPO_ROOT / "build" / MANUSCRIPT_NAME

AUTHOR_CONTRIBUTIONS = BUILD_DIR / "author-contributions.tex"
"""The author contributions statement, generated from the metadata file"""

WARMING_FIGURE = FIGURES_OUT_DIR / "warming.pdf"
"""Figure of the projected warming"""

PEAK_WARMING_TABLE = TABLES_OUT_DIR / "peak-warming.tex"
"""Table of peak warming"""

FIGURE_FILES = {
    "@warming-figure@": WARMING_FIGURE,
}
"""Figures, by the tag which is replaced with their path in the latex"""

FILES_TO_INLINE = {
    "@peak-warming-table@": PEAK_WARMING_TABLE,
}
"""Files whose content replaces their tag in the latex (e.g. tables)"""

# Outputs
LATEX_DIR = BUILD_DIR / "latex"
LATEX_MAIN = LATEX_DIR / "main.tex"
OUTPUT_PDF = REPO_ROOT / "compiled-manuscripts" / f"{MANUSCRIPT_NAME}.pdf"
