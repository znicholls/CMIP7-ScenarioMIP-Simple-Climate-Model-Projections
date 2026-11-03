"""
Raw scenario data: downloading it from the ssp_submission database

The data comes from the ssp_submission database
(an IIASA Scenario Explorer database, accessed via pyam's legacy connection).
Access to this database requires an IIASA login with the right permissions.
If you haven't logged in yet, run

```sh
uv run ixmp4 login <your-username>
```

This follows `scripts/cmip7-scenariomip-downloading.py` in gcages
(at the commit we use, see `pyproject.toml`).
We only download the timeseries that are used in the workflow,
to keep the load on the database as low as possible.
The downloaded data is checked against the checksum
recorded in gcages' definition of each marker,
so we know we have exactly the data that was used in CMIP7 ScenarioMIP.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from gcages.cmip7_scenariomip.pre_processing.reaggregation.basic import (
    get_complete_timeseries_index,
    get_internal_consistency_checking_index,
)
from gcages.hashing import get_data_checksum
from gcages.workflows.cmip7_scenariomip import CMIP7ScenarioMIPMarker
from gcages.workflows.cmip7_scenariomip.inputs import load_harmonisation_methods
from gcages.workflows.cmip7_scenariomip.pre_processing import (
    CO2_AFOLU_RAW_NAME,
    get_model_prefix,
    get_used_locator,
)
from loguru import logger

from local.feather_io import load_feather_df, save_feather

if TYPE_CHECKING:
    import pyam

SSP_SUBMISSION_CONNECTION = "ssp_submission"
"""pyam connection to the database to which the scenarios were submitted"""

INDEX_LEVELS = ("model", "scenario", "region", "variable", "unit")
"""Index levels of the raw emissions"""


def get_raw_filename(marker: CMIP7ScenarioMIPMarker) -> str:
    """
    Get the name of the file in which to save a marker's raw data

    Parameters
    ----------
    marker
        Marker

    Returns
    -------
    :
        Filename
    """
    res = f"{marker.model}__{marker.scenario}__v{marker.ssp_submission_version}"
    res = res.replace("/", "_").replace(" ", "_")

    return f"{res}.feather"


@functools.cache
def get_used_variables() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """
    Get the variables which are used in the workflow

    These are:

    - the variables used to create the region-sector (i.e. gridding) emissions
      during pre-processing
      (including the variables used to check internal consistency)
    - the globally reported CO2 AFOLU emissions
    - the globally reported emissions of species which aren't in the
      region-sector emissions (e.g. F-gases)
      for which there is a harmonisation method.

    Returns
    -------
    :
        Variables used at the World level and variables used at the model region level
    """
    placeholder_region = "__model_region__"
    used = get_complete_timeseries_index((placeholder_region,)).append(
        get_internal_consistency_checking_index((placeholder_region,))
    )
    regions = used.get_level_values("region")
    variables = used.get_level_values("variable")

    model_region_variables = tuple(
        sorted(set(variables[regions == placeholder_region]))
    )
    region_sector_species = {v.split("|")[1] for v in model_region_variables}

    global_methods = load_harmonisation_methods("harmonisation-methods_global.csv")
    global_only_species_variables = {
        v
        for v in global_methods.index.get_level_values("variable").unique()
        if v.split("|")[1] not in region_sector_species
    }

    world_variables = tuple(
        sorted(
            {
                *variables[regions == "World"],
                CO2_AFOLU_RAW_NAME,
                *global_only_species_variables,
            }
        )
    )

    return world_variables, model_region_variables


@functools.cache
def get_ssp_submission_connection() -> pyam.iiasa.Connection:
    """
    Get the connection to the ssp_submission database

    Cached so that we only connect (and authenticate) once.

    Returns
    -------
    :
        Connection to the database
    """
    import pyam

    return pyam.iiasa.Connection(SSP_SUBMISSION_CONNECTION)


def to_wide(res_long: pd.DataFrame) -> pd.DataFrame:
    """
    Convert data from long format (one row per year) to wide (years as columns)

    Parameters
    ----------
    res_long
        Data in long format

    Returns
    -------
    :
        Data in wide format
    """
    res = res_long.set_index([*INDEX_LEVELS, "year"])["value"].unstack("year")
    res.columns = res.columns.astype(int)
    res.columns.name = "year"

    return res


def download_from_ssp_submission(marker: CMIP7ScenarioMIPMarker) -> pd.DataFrame:
    """
    Download a marker's data from the ssp_submission database

    Parameters
    ----------
    marker
        Marker to download

    Returns
    -------
    :
        Emissions in wide format (years as columns),
        only the timeseries which are used in the workflow
    """
    import requests

    conn = get_ssp_submission_connection()
    runs = conn.properties(default_only=False).reset_index()
    run = runs[
        (runs["model"] == marker.model)
        & (runs["scenario"] == marker.scenario)
        & (runs["version"] == marker.ssp_submission_version)
    ]
    if run.shape[0] != 1:
        msg = f"Expected exactly one run for {marker=}, found {run.shape[0]}"
        raise ValueError(msg)

    model_prefix = get_model_prefix(marker.model)
    model_regions = [r for r in conn.regions() if r.startswith(model_prefix)]
    world_variables, model_region_variables = get_used_variables()

    # `pyam.iiasa.Connection.query` can only get the default version
    # or all versions of a model-scenario (which can be dozens),
    # so we query the API directly with the run ID instead
    # (this is the same request `pyam.iiasa.Connection.query` makes).
    res_l = []
    for regions, variables in (
        (["World"], world_variables),
        (model_regions, model_region_variables),
    ):
        response = requests.post(
            f"{conn._base_url}/runs/bulk/ts",
            headers={**conn.auth(), "Content-Type": "application/json"},
            json={
                "filters": {
                    "regions": list(regions),
                    "variables": list(variables),
                    "runs": [int(run["run_id"].iloc[0])],
                    "years": [],
                    "units": [],
                    "timeslices": [],
                }
            },
            timeout=600,
        )
        response.raise_for_status()
        res_l.append(pd.DataFrame(response.json()))

    res_long = pd.concat(res_l)
    if res_long.empty:
        msg = f"No data found for {marker=}"
        raise ValueError(msg)

    if set(res_long["version"].unique()) != {marker.ssp_submission_version}:
        msg = f"Got data for other versions: {res_long['version'].unique()}"
        raise AssertionError(msg)

    if "subannual" in res_long and not res_long["subannual"].isin([-1, "Year"]).all():
        msg = "Got sub-annual data, which we don't support"
        raise AssertionError(msg)

    res = to_wide(res_long)

    return res.loc[get_used_locator(res)]


def check_raw_data(raw: pd.DataFrame, marker: CMIP7ScenarioMIPMarker) -> None:
    """
    Check raw data is exactly the data that was used in CMIP7 ScenarioMIP

    Parameters
    ----------
    raw
        Raw data

    marker
        Marker the data is for

    Raises
    ------
    AssertionError
        The checksum of the data doesn't match the one recorded in gcages
    """
    checksum = get_data_checksum(raw)
    if checksum != marker.ssp_submission_data_checksum:
        msg = (
            f"Checksum of the raw data for {marker.model=}, {marker.scenario=}, "
            f"{marker.ssp_submission_version=} does not match the expected value. "
            f"{checksum=} expected={marker.ssp_submission_data_checksum!r}"
        )
        raise AssertionError(msg)


def download_raw_data(marker: CMIP7ScenarioMIPMarker, out_file: Path) -> Path:
    """
    Download a marker's raw data, check it and save it

    Parameters
    ----------
    marker
        Marker to download

    out_file
        File in which to save the data

    Returns
    -------
    :
        `out_file`
    """
    logger.info(
        f"Downloading {marker.model} {marker.scenario} "
        f"v{marker.ssp_submission_version} from {SSP_SUBMISSION_CONNECTION}"
    )
    res = download_from_ssp_submission(marker)
    check_raw_data(res, marker)

    return save_feather(res, out_file)


def load_raw_data(marker: CMIP7ScenarioMIPMarker, fp: Path) -> pd.DataFrame:
    """
    Load a marker's raw data (and check it)

    Parameters
    ----------
    marker
        Marker the data is for

    fp
        File in which the data was saved by [download_raw_data][(m).]

    Returns
    -------
    :
        Raw data
    """
    res = load_feather_df(fp)
    check_raw_data(res, marker)

    return res
