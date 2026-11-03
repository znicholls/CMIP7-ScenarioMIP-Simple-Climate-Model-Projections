"""
Tasks which download the inputs

- the raw scenario data, from the ssp_submission database
  (needs an IIASA login, see `src/local/cmip7_scenariomip_scm_projections/raw_data.py`)
- the history, infilling database and published results, from Zenodo
"""

from pathlib import Path
from typing import Annotated

from pytask import Product, task

import local.cmip7_scenariomip_scm_projections.raw_data
from local.cmip7_scenariomip_scm_projections.config import get_raw_file
from local.cmip7_scenariomip_scm_projections.magicc_runs import (
    ZENODO_FILE_PATHS,
    download_zenodo_files,
)
from local.cmip7_scenariomip_scm_projections.raw_data import download_raw_data
from local.cmip7_scenariomip_scm_projections.scenarios import SCENARIOS, Scenario

RAW_DATA_SOURCE = Path(local.cmip7_scenariomip_scm_projections.raw_data.__file__)
"""The module which downloads the raw data (it is re-downloaded if this changes)"""

for _scenario in SCENARIOS:

    @task(id=_scenario.slug)
    def task_download_raw_data(
        scenario: Scenario = _scenario,
        raw_data_source: Path = RAW_DATA_SOURCE,
        out_file: Annotated[Path, Product] = get_raw_file(_scenario),
    ) -> None:
        """Download a scenario's raw data (checked against gcages' checksum)"""
        download_raw_data(scenario.marker, out_file)


def task_download_zenodo_files(
    out_files: Annotated[list[Path], Product] = list(ZENODO_FILE_PATHS),
) -> None:
    """Download the files we need from Zenodo (checked against their md5 hashes)"""
    downloaded = download_zenodo_files()
    if sorted(downloaded) != sorted(out_files):
        msg = f"Expected to download {out_files}, got {downloaded}"
        raise AssertionError(msg)
