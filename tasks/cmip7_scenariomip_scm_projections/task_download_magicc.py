"""
Tasks which download MAGICC and its probabilistic distribution

This is in its own module, rather than in `task_download.py`,
because pytask re-runs every task in a module when the module changes
(and the raw data downloads need an IIASA login).

See `local.cmip7_scenariomip_scm_projections.magicc` for where these come from
and how to use a MAGICC binary you built yourself.
"""

from pathlib import Path
from typing import Annotated

from pytask import Product

import local.cmip7_scenariomip_scm_projections.magicc
from local.cmip7_scenariomip_scm_projections.magicc import (
    MAGICC_BUNDLE_FILES,
    PROB_DISTRIBUTION_DOWNLOAD_PATH,
    download_magicc,
    download_prob_distribution,
)

MAGICC_SOURCE = Path(local.cmip7_scenariomip_scm_projections.magicc.__file__)
"""The module which says where to download from (re-downloaded if this changes)"""


def task_download_magicc(
    magicc_source: Path = MAGICC_SOURCE,
    out_files: Annotated[list[Path], Product] = list(MAGICC_BUNDLE_FILES),
) -> None:
    """
    Download MAGICC (checked against its hash)

    Fails if the bundle has no binary for this platform
    and `MAGICC_EXECUTABLE_7` isn't set.
    """
    downloaded = download_magicc()
    if sorted(downloaded) != sorted(out_files):
        msg = f"Expected to download {out_files}, got {downloaded}"
        raise AssertionError(msg)


def task_download_magicc_prob_distribution(
    magicc_source: Path = MAGICC_SOURCE,
    out_file: Annotated[Path, Product] = PROB_DISTRIBUTION_DOWNLOAD_PATH,
) -> None:
    """Download MAGICC's probabilistic distribution (checked against its hash)"""
    downloaded = download_prob_distribution()
    if downloaded != out_file:
        msg = f"Expected to download {out_file}, got {downloaded}"
        raise AssertionError(msg)
