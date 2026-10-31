"""
Summaries of the projected warming

Everything here starts from the assessed GSAT of each ensemble member
(i.e. MAGICC's GSAT, in line with the IPCC AR6 assessment of historical warming,
relative to 1850-1900), over the full run to 2500.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from local.cmip7_scenariomip_scm_projections.magicc_runs import (
    ASSESSED_GSAT_TIMESERIES_FILE,
)
from local.feather_io import load_feather_df, save_feather

QUANTILES = (0.05, 0.17, 0.33, 0.5, 0.67, 0.83, 0.95)
"""Quantiles we report"""

PEAK = "peak"
"""Name of the peak warming metric"""

METRIC_YEARS = (2100, 2500)
"""Years in which we report warming"""

METRICS = (PEAK, *(str(y) for y in METRIC_YEARS))
"""Metrics we report (peak warming over the full run and warming in given years)"""

TIMESERIES_QUANTILES = (0.05, 0.5, 0.95)
"""Quantiles of the timeseries we report"""

TIMESERIES_FIRST_YEAR = 1850
"""First year of the timeseries we report"""

GROUP_LEVELS = ["climate_model", "model", "scenario", "region", "variable", "unit"]
"""Index levels which identify a timeseries (i.e. everything except the ensemble)"""


def load_assessed_gsat(run_dirs: Iterable[Path]) -> pd.DataFrame:
    """
    Load the assessed GSAT of each ensemble member for each scenario

    Parameters
    ----------
    run_dirs
        Directories of the runs

    Returns
    -------
    :
        Assessed GSAT (one row per ensemble member per scenario)
    """
    return pd.concat(
        [load_feather_df(rd / ASSESSED_GSAT_TIMESERIES_FILE) for rd in run_dirs]
    )


def get_metrics_run_id(assessed_gsat: pd.DataFrame) -> pd.DataFrame:
    """
    Get the warming metrics for each ensemble member

    Parameters
    ----------
    assessed_gsat
        Assessed GSAT for each ensemble member

    Returns
    -------
    :
        Warming metrics (columns are [METRICS][(m).])
    """
    res = pd.concat(
        [
            assessed_gsat.max(axis="columns").rename(PEAK),
            *(assessed_gsat[y].rename(str(y)) for y in METRIC_YEARS),
        ],
        axis="columns",
    )
    res.columns.name = "metric"

    return res


def get_metrics_quantiles(metrics_run_id: pd.DataFrame) -> pd.DataFrame:
    """
    Get the quantiles of the warming metrics over the ensemble

    Parameters
    ----------
    metrics_run_id
        Warming metrics for each ensemble member

    Returns
    -------
    :
        Quantiles (rows are scenarios and metrics, columns are [QUANTILES][(m).])
    """
    group_levels = [lvl for lvl in GROUP_LEVELS if lvl in metrics_run_id.index.names]
    res = (
        metrics_run_id.stack()
        .groupby([*group_levels, "metric"])
        .quantile(list(QUANTILES))
        .unstack()
    )
    res.columns.name = "quantile"

    return res


def get_timeseries_quantiles(assessed_gsat: pd.DataFrame) -> pd.DataFrame:
    """
    Get the quantiles of the assessed GSAT over the ensemble

    Parameters
    ----------
    assessed_gsat
        Assessed GSAT for each ensemble member

    Returns
    -------
    :
        Quantiles of assessed GSAT, from [TIMESERIES_FIRST_YEAR][(m).]
        (the quantile is the last index level)
    """
    group_levels = [lvl for lvl in GROUP_LEVELS if lvl in assessed_gsat.index.names]
    res = (
        assessed_gsat.loc[:, TIMESERIES_FIRST_YEAR:]
        .groupby(group_levels)
        .quantile(list(TIMESERIES_QUANTILES))
    )
    res.index = res.index.set_names("quantile", level=-1)

    return res


def get_peak_year_quantiles(assessed_gsat: pd.DataFrame) -> pd.DataFrame:
    """
    Get the quantiles over the ensemble of the year of peak warming

    The peak is taken over the full run (to 2500),
    so for scenarios which are still warming in 2500, the peak year is 2500.

    Parameters
    ----------
    assessed_gsat
        Assessed GSAT for each ensemble member

    Returns
    -------
    :
        Quantiles (rows are scenarios, columns are [QUANTILES][(m).])
    """
    group_levels = [
        lvl
        for lvl in GROUP_LEVELS
        if lvl in assessed_gsat.index.names and lvl != "unit"
    ]
    peak_year = assessed_gsat.idxmax(axis="columns").astype(float)
    res = peak_year.groupby(group_levels).quantile(list(QUANTILES)).unstack()
    res.columns.name = "quantile"
    res = pd.concat({"yr": res}, names=["unit"])

    return res


def summarise_warming(
    run_dirs: Iterable[Path],
    metrics_quantiles_file: Path,
    timeseries_quantiles_file: Path,
    peak_year_quantiles_file: Path,
) -> None:
    """
    Summarise the projected warming of all scenarios

    Parameters
    ----------
    run_dirs
        Directories of the runs

    metrics_quantiles_file
        File in which to save the quantiles of the warming metrics

    timeseries_quantiles_file
        File in which to save the quantiles of the assessed GSAT timeseries

    peak_year_quantiles_file
        File in which to save the quantiles of the year of peak warming
    """
    assessed_gsat = load_assessed_gsat(run_dirs)

    save_feather(
        get_metrics_quantiles(get_metrics_run_id(assessed_gsat)),
        metrics_quantiles_file,
    )
    save_feather(get_timeseries_quantiles(assessed_gsat), timeseries_quantiles_file)
    save_feather(get_peak_year_quantiles(assessed_gsat), peak_year_quantiles_file)
