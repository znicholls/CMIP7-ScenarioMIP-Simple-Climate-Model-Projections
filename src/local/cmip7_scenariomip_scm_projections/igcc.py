"""
Data from Indicators of Global Climate Change 2025 (IGCC, Forster et al., 2026)

Forster et al. (2026), Indicators of Global Climate Change 2025:
annual update of key indicators of the state of the climate system
and human influence, Earth Syst. Sci. Data, 18, 3889-3933,
https://doi.org/10.5194/essd-18-3889-2026.

The data is the IGCC-2025a release of the ClimateIndicator data repository
(https://doi.org/10.5281/zenodo.21494229).
All temperatures are global mean surface temperature (GMST)
relative to 1850-1900.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pooch

from local.paths import DATA_RAW_DIR

IGCC_VERSION = "IGCC-2025a"
"""Version of the IGCC data we use"""

IGCC_ZIP_URL = (
    "https://zenodo.org/api/records/21494229/files/"
    f"ClimateIndicator/data-{IGCC_VERSION}.zip/content"
)
"""Where to download the IGCC data from"""

IGCC_ZIP_HASH = "md5:0ad608c0adb5aed35136d7f1f318c80a"
"""Hash of the zip file (as given by Zenodo)"""

IGCC_ZIP_DATA_DIR = "ClimateIndicator-data-0f2765d/data/base"
"""Directory in the zip file which holds the data we use"""

IGCC_DIR = DATA_RAW_DIR / "igcc" / IGCC_VERSION
"""Directory in which we save the IGCC data"""

OBSERVED_GMST_FILE = "global_mean_temperatures/annual_averages.csv"
"""Observed GMST (multi-dataset mean, annual)"""

HUMAN_INDUCED_WARMING_FILE = "anthropogenic_warming/multi_method_timeseries.csv"
"""Human-induced warming (mean of the three attribution methods, annual)"""

METHODS = ("Walsh", "Ribes", "Gillett")
"""
Names of the files of the three attribution methods

Global warming index (Walsh), kriging for climate change (Ribes)
and regularised optimal fingerprinting (Gillett).
"""


def get_method_files(method: str) -> tuple[str, str]:
    """Get a method's files of human-induced warming and its rate"""
    prefix = f"anthropogenic_warming/{method}_GMST"
    return f"{prefix}_timeseries.csv", f"{prefix}_rates.csv"


IGCC_FILES = (
    OBSERVED_GMST_FILE,
    HUMAN_INDUCED_WARMING_FILE,
    *(f for m in METHODS for f in get_method_files(m)),
)
"""Files we use from the IGCC data"""

IGCC_FILE_PATHS = tuple(IGCC_DIR / f for f in IGCC_FILES)
"""Where each of [IGCC_FILES][(m).] is saved"""

ASSESSED_RATE_PERIOD = (2016, 2025)
"""
First and last year of the latest period over which IGCC assesses the rate

The rate is the linear trend over the ten years, both years included.
"""

ASSESSED_RATE_BEST = 0.27
"""Assessed rate of human-induced warming (K / decade), best estimate"""

ASSESSED_RATE_RANGE = (0.2, 0.4)
"""
Assessed rate of human-induced warming (K / decade), likely range

From the abstract and section 8.2 of Forster et al. (2026).
These assessed values aren't in the data release,
so we copy them from the paper.
"""

RATE_CHECK_ATOL = 0.005
"""
Tolerance (K / decade) when checking our rate against IGCC's

IGCC's rates are the median over each method's ensemble of the trend.
We can only calculate the trend of the median timeseries,
which isn't quite the same thing.
"""


def download_igcc_data() -> tuple[Path, ...]:
    """
    Download the IGCC data (checking its hash) and extract the files we use

    Returns
    -------
    :
        Paths to the extracted files (i.e. [IGCC_FILE_PATHS][(m).])
    """
    zip_file = pooch.retrieve(
        IGCC_ZIP_URL,
        known_hash=IGCC_ZIP_HASH,
        fname=f"data-{IGCC_VERSION}.zip",
        path=IGCC_DIR.parent,
        progressbar=False,
    )
    with zipfile.ZipFile(zip_file) as zf:
        for file, out_path in zip(IGCC_FILES, IGCC_FILE_PATHS):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(zf.read(f"{IGCC_ZIP_DATA_DIR}/{file}"))

    return IGCC_FILE_PATHS


def load_igcc_csv(fp: Path) -> pd.DataFrame:
    """
    Load one of IGCC's csv files, indexed by year

    Some files start with a byte order mark, hence the encoding.
    """
    res = pd.read_csv(fp, encoding="utf-8-sig")
    # Annual values: the year is the lower bound of the time bounds
    res = res.set_index("timebound_lower").drop(columns=["time", "timebound_upper"])
    res.index.name = "year"

    return res


def load_observed_gmst(igcc_dir: Path = IGCC_DIR) -> pd.Series:  # type: ignore[type-arg]
    """Load the observed GMST (indexed by year)"""
    return load_igcc_csv(igcc_dir / OBSERVED_GMST_FILE)["GMST"]


def load_human_induced_warming(igcc_dir: Path = IGCC_DIR) -> pd.Series:  # type: ignore[type-arg]
    """Load the human-induced warming (indexed by year)"""
    return load_igcc_csv(igcc_dir / HUMAN_INDUCED_WARMING_FILE)["Multi-method mean"]


def get_rate(timeseries: pd.DataFrame, first_year: int, last_year: int) -> pd.Series:  # type: ignore[type-arg]
    """
    Get the rate of warming of each timeseries

    As in IGCC, the rate is the ordinary least-squares linear trend
    of the annual values from `first_year` to `last_year` (both included).

    Parameters
    ----------
    timeseries
        Timeseries (one row each, years as columns)

    first_year
        First year of the period

    last_year
        Last year of the period

    Returns
    -------
    :
        Rate of each timeseries (per decade)
    """
    years = np.arange(first_year, last_year + 1)
    values = timeseries.loc[:, years].to_numpy()
    anomalies = years - years.mean()
    per_year = (values @ anomalies) / (anomalies @ anomalies)

    return pd.Series(10 * per_year, index=timeseries.index)


def check_rate_definition(igcc_dir: Path = IGCC_DIR) -> None:
    """
    Check that [get_rate][(m).] reproduces IGCC's rates for each method

    Parameters
    ----------
    igcc_dir
        Directory which holds the IGCC data

    Raises
    ------
    AssertionError
        Our rate of a method's median human-induced warming differs
        from its published median rate by more than [RATE_CHECK_ATOL][(m).]
    """
    first_year, last_year = ASSESSED_RATE_PERIOD
    for method in METHODS:
        timeseries_file, rates_file = get_method_files(method)
        median_warming = load_igcc_csv(igcc_dir / timeseries_file)["anthropogenic_p50"]
        ours = get_rate(median_warming.to_frame().T, first_year, last_year).squeeze()

        published = load_igcc_csv(igcc_dir / rates_file).loc[
            first_year, "anthropogenic_p50"
        ]
        # IGCC's rates are per year
        published = 10 * published
        if not np.isclose(ours, published, atol=RATE_CHECK_ATOL, rtol=0.0):
            msg = (
                f"Our {first_year}-{last_year} rate for {method} doesn't match IGCC's. "
                f"{ours=} {published=}"
            )
            raise AssertionError(msg)
