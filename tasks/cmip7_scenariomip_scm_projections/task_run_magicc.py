"""
Expensive tasks: running the workflow, including MAGICC, for each scenario

Kept in their own module on purpose.
pytask considers a task changed if the module it is defined in changes,
so if these sat with the cheap tasks,
editing a cheap task would re-run MAGICC too.

Each run also checks that it reproduces the published results
(https://zenodo.org/records/19825038) and fails if it doesn't.

MAGICC is found via environment variables, see the README.
"""

from pathlib import Path
from typing import Annotated

from pytask import Product, task

import local.cmip7_scenariomip_scm_projections.magicc_runs
import local.cmip7_scenariomip_scm_projections.raw_data
from local.cmip7_scenariomip_scm_projections.config import RUNS_DIR, get_raw_file
from local.cmip7_scenariomip_scm_projections.magicc_runs import (
    ZENODO_FILE_PATHS,
    get_magicc_dependencies,
    get_run_dir,
    get_run_output_files,
    run_scenario,
)
from local.cmip7_scenariomip_scm_projections.scenarios import SCENARIOS, Scenario

RUN_SOURCES = [
    Path(local.cmip7_scenariomip_scm_projections.magicc_runs.__file__),
    Path(local.cmip7_scenariomip_scm_projections.raw_data.__file__),
]
"""The modules which define the runs (they re-run if these change)"""

for _scenario in SCENARIOS:

    @task(id=_scenario.slug)
    def task_run_magicc(  # noqa: PLR0913
        scenario: Scenario = _scenario,
        raw_file: Path = get_raw_file(_scenario),
        zenodo_files: list[Path] = list(ZENODO_FILE_PATHS),
        magicc_files: list[Path] = get_magicc_dependencies(),
        run_sources: list[Path] = RUN_SOURCES,
        out_files: Annotated[list[Path], Product] = get_run_output_files(
            get_run_dir(RUNS_DIR, _scenario)
        ),
    ) -> None:
        """
        Run the workflow for a scenario, save the results and check them

        The check is that we reproduce the published results.
        """
        run_scenario(
            scenario=scenario,
            raw_file=raw_file,
            run_dir=get_run_dir(RUNS_DIR, scenario),
        )
