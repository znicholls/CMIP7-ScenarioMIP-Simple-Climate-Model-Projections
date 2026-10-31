"""
Tasks which generate the figures, tables and other tex inputs
"""

from pathlib import Path
from typing import Annotated

from pytask import Product

import local.author_contributions
import local.cmip7_scenariomip_scm_projections.figures
import local.cmip7_scenariomip_scm_projections.scenarios
import local.cmip7_scenariomip_scm_projections.tables
import local.cmip7_scenariomip_scm_projections.warming
from local.author_contributions import generate_author_contributions
from local.cmip7_scenariomip_scm_projections.config import (
    AUTHOR_CONTRIBUTIONS,
    METADATA,
    PEAK_WARMING_TABLE,
    PEAK_YEAR_QUANTILES,
    RUN_DIRS,
    WARMING_FIGURE,
    WARMING_METRICS_QUANTILES,
    WARMING_TIMESERIES_QUANTILES,
)
from local.cmip7_scenariomip_scm_projections.figures import generate_warming_figure
from local.cmip7_scenariomip_scm_projections.magicc_runs import (
    ASSESSED_GSAT_TIMESERIES_FILE,
)
from local.cmip7_scenariomip_scm_projections.tables import (
    generate_peak_warming_table,
)
from local.cmip7_scenariomip_scm_projections.warming import summarise_warming

SCENARIOS_SOURCE = Path(local.cmip7_scenariomip_scm_projections.scenarios.__file__)
"""The scenarios' labels and colours"""


def task_summarise_warming(
    assessed_gsat_files: list[Path] = [
        rd / ASSESSED_GSAT_TIMESERIES_FILE for rd in RUN_DIRS
    ],
    warming_source: Path = Path(
        local.cmip7_scenariomip_scm_projections.warming.__file__
    ),
    metrics_quantiles_file: Annotated[Path, Product] = WARMING_METRICS_QUANTILES,
    timeseries_quantiles_file: Annotated[Path, Product] = WARMING_TIMESERIES_QUANTILES,
    peak_year_quantiles_file: Annotated[Path, Product] = PEAK_YEAR_QUANTILES,
) -> None:
    """Summarise the projected warming (quantiles of metrics, timeseries, peak year)"""
    summarise_warming(
        run_dirs=RUN_DIRS,
        metrics_quantiles_file=metrics_quantiles_file,
        timeseries_quantiles_file=timeseries_quantiles_file,
        peak_year_quantiles_file=peak_year_quantiles_file,
    )


def task_warming_figure(
    metrics_quantiles_file: Path = WARMING_METRICS_QUANTILES,
    timeseries_quantiles_file: Path = WARMING_TIMESERIES_QUANTILES,
    peak_year_quantiles_file: Path = PEAK_YEAR_QUANTILES,
    figures_sources: list[Path] = [
        Path(local.cmip7_scenariomip_scm_projections.figures.__file__),
        SCENARIOS_SOURCE,
    ],
    out_file: Annotated[Path, Product] = WARMING_FIGURE,
) -> None:
    """Generate the figure of projected warming"""
    generate_warming_figure(
        out_file,
        metrics_quantiles_file=metrics_quantiles_file,
        timeseries_quantiles_file=timeseries_quantiles_file,
        peak_year_quantiles_file=peak_year_quantiles_file,
    )


TABLES_SOURCES = [
    Path(local.cmip7_scenariomip_scm_projections.tables.__file__),
    SCENARIOS_SOURCE,
]
"""The modules which make the tables (they are re-made if these change)"""


def task_peak_warming_table(
    metrics_quantiles_file: Path = WARMING_METRICS_QUANTILES,
    tables_sources: list[Path] = TABLES_SOURCES,
    out_file: Annotated[Path, Product] = PEAK_WARMING_TABLE,
) -> None:
    """Generate the table of peak warming"""
    generate_peak_warming_table(out_file, metrics_quantiles_file)


def task_author_contributions(
    metadata: Path = METADATA,
    author_contributions_source: Path = Path(local.author_contributions.__file__),
    outfile: Annotated[Path, Product] = AUTHOR_CONTRIBUTIONS,
) -> None:
    """Generate the author contributions statement from the metadata file"""
    generate_author_contributions(outfile=outfile, metadata_file=metadata)
