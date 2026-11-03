"""
Checks of the values behind the manuscript's statements

See [local.value_checks][] for how these are used.
To add a check, write a function which calculates the value
and add a [ValueCheck][local.value_checks.ValueCheck] to [get_value_checks][(m).].
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import openscm_units

from local.cmip7_scenariomip_scm_projections.scenarios import SCENARIOS
from local.cmip7_scenariomip_scm_projections.warming import PEAK
from local.feather_io import load_feather_df
from local.value_checks import CheckValue, ValueCheck

Q = openscm_units.unit_registry.Quantity


def get_metric_quantile_range(
    metrics_quantiles_file: Path, metric: str, quantile: float
) -> CheckValue:
    """
    Get the range across scenarios of a quantile of a warming metric

    Returns a quantity with the lowest and highest values,
    so the check passes only if both are within the statement's bounds.
    """
    metrics_quantiles = load_feather_df(metrics_quantiles_file)
    values = metrics_quantiles.loc[
        metrics_quantiles.index.get_level_values("metric") == metric, quantile
    ]
    if values.shape[0] != len(SCENARIOS):
        msg = f"Expected one value per scenario, found {values.shape[0]}"
        raise AssertionError(msg)

    return Q(np.array([values.min(), values.max()]), "K")


def get_all_reproduce_published(check_files: Iterable[Path]) -> CheckValue:
    """Get whether every scenario reproduces the published results"""
    return all(json.loads(fp.read_text())["passed"] for fp in check_files)


def get_value_checks(
    metrics_quantiles_file: Path, reproduction_check_files: Iterable[Path]
) -> list[ValueCheck]:
    """
    Get the checks of the values behind the manuscript's statements

    Parameters
    ----------
    metrics_quantiles_file
        File which holds the quantiles of the warming metrics

    reproduction_check_files
        Each run's check that it reproduces the published results

    Returns
    -------
    :
        Value checks
    """
    reproduction_check_files = tuple(reproduction_check_files)

    return [
        ValueCheck(
            tag="n-scenarios",
            calculate=lambda: Q(len(SCENARIOS), "dimensionless"),
            description="Number of scenarios we run",
        ),
        ValueCheck(
            tag="peak-warming-median-range",
            calculate=lambda: get_metric_quantile_range(
                metrics_quantiles_file, metric=PEAK, quantile=0.5
            ),
            description="Range across scenarios of median peak warming",
        ),
        ValueCheck(
            tag="all-scenarios-reproduce-published",
            calculate=lambda: get_all_reproduce_published(reproduction_check_files),
            description="Whether every scenario reproduces the published results",
        ),
    ]
