"""
Task which downloads the Indicators of Global Climate Change (IGCC) data

This is in its own module, rather than in `task_download.py`,
because pytask re-runs every task in a module when the module changes
(and the raw data downloads need an IIASA login).
"""

from pathlib import Path
from typing import Annotated

from pytask import Product

import local.cmip7_scenariomip_scm_projections.igcc
from local.cmip7_scenariomip_scm_projections.igcc import (
    IGCC_FILE_PATHS,
    download_igcc_data,
)


def task_download_igcc_data(
    igcc_source: Path = Path(local.cmip7_scenariomip_scm_projections.igcc.__file__),
    out_files: Annotated[list[Path], Product] = list(IGCC_FILE_PATHS),
) -> None:
    """Download the IGCC data (checked against its md5 hash)"""
    downloaded = download_igcc_data()
    if sorted(downloaded) != sorted(out_files):
        msg = f"Expected to download {out_files}, got {downloaded}"
        raise AssertionError(msg)
