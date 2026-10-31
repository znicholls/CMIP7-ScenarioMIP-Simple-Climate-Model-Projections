"""
Running the CMIP7 ScenarioMIP workflow, including MAGICC, for one scenario

We run the entire workflow (pre-processing, harmonisation, infilling,
extension to 2500, MAGICC and post-processing) with gcages
(at the commit in `pyproject.toml`).
Every step's output is saved to disk as feather files,
so other tasks can use whatever they need.

As part of each run, we check that we reproduce v0.2
of the published harmonised and infilled emissions and climate assessment
(https://zenodo.org/records/19825038),
exactly as gcages' test of the workflow does
(`tests/workflows/cmip7-scenariomip/test_workflow_cmip7_scenariomip.py`).
The result of the check is written to a JSON file
and the run fails if the check fails.
"""

from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
from typing import Any

import attrs
import numpy as np
import pandas as pd
import pandas_indexing as pix
from gcages.post_processing import PostProcessingResult
from gcages.testing import assert_frame_equal
from gcages.workflows.cmip7_scenariomip import (
    CMIP7ScenarioMIPWorkflowPostProcessor,
    CMIP7ScenarioMIPWorkflowResult,
    CMIP7ScenarioMIPWorkflowRunner,
    PoochDownloader,
    PublishedClimateAssessment,
    load_published_climate_assessment,
    load_published_emissions,
)
from gcages.workflows.cmip7_scenariomip.inputs import (
    GLOBAL_HISTORY_FILE,
    INFILLING_DB_FILE,
    REGION_SECTOR_HISTORY_FILE,
    get_file,
)
from gcages.workflows.cmip7_scenariomip.markers import PUBLISHED_EMISSIONS_FILE
from loguru import logger

from local.cmip7_scenariomip_scm_projections.raw_data import load_raw_data
from local.cmip7_scenariomip_scm_projections.scenarios import Scenario
from local.feather_io import save_feather
from local.paths import DATA_RAW_DIR

MAGICC_EXECUTABLE_ENV_VAR = "MAGICC_EXECUTABLE_7"
"""Environment variable which gives the path to the MAGICC v7.6.0a3 executable"""

MAGICC_PROB_DISTRIBUTION_ENV_VAR = "MAGICC_PROB_DISTRIBUTION_PATH"
"""
Environment variable which gives the path to MAGICC's probabilistic distribution

This should be the CMIP7 ScenarioMIP distribution
(`magicc-ar7-fast-track-drawnset-v0-3-0.json`).
"""

N_PROCESSES_ENV_VAR = "MAGICC_N_PROCESSES"
"""
Environment variable which sets the number of processes to use

Used for harmonisation and running MAGICC.
Defaults to the number of CPUs.
"""

ZENODO_CACHE_DIR = DATA_RAW_DIR / "zenodo"
"""Directory in which we save the files we download from Zenodo"""

ZENODO_FILES = (
    GLOBAL_HISTORY_FILE,
    REGION_SECTOR_HISTORY_FILE,
    INFILLING_DB_FILE,
    PUBLISHED_EMISSIONS_FILE,
)
"""
Files we need from Zenodo

The history and infilling database used by the workflow
and the published results we check against.
"""

ZENODO_FILE_PATHS = tuple(ZENODO_CACHE_DIR / f.filename for f in ZENODO_FILES)
"""Where each of [ZENODO_FILES][(m).] is saved"""

DOWNLOADER = PoochDownloader(cache_dir=ZENODO_CACHE_DIR)
"""Downloader to use to get files from Zenodo"""

# Tolerances, exactly as in gcages' test of the workflow
CLIMATE_ATOL = 1e-5
"""
Absolute tolerance to use when comparing the exceedance probabilities

The published values differ from ours at the level of ~1e-6,
presumably because the published results were created on a different platform.
"""

TIMESERIES_ATOL = 5e-3
"""
Absolute tolerance to use when comparing the climate assessment timeseries

The published results match a MAGICC run with emissions that end in 2100.
We run MAGICC with the emissions extended to 2500,
which changes the values in 2100
by up to ~2e-4 K for temperatures and ~2e-3 W/m^2 for effective radiative forcing
(MAGICC's value in a given year depends on the next year's emissions).
Before 2100, the differences are at the level of ~1e-5.
"""

METADATA_QUANTILE_ATOL = 5e-4
"""
Absolute tolerance (K) to use when comparing peak warming and warming in 2100

See [TIMESERIES_ATOL][(m).] for why this isn't smaller.
"""

# Output files
REPRODUCTION_CHECK_FILE = "reproduction-check.json"
"""Name of the file which holds the result of the reproduction check"""

POST_PROCESSED_FULL_PREFIX = "post_processed_to_2500"
"""
Prefix of the files which hold the post-processing over the full run (to 2500)

The workflow's own post-processing (`post_processed__*`) only considers years
up to 2100 (as in CMIP7 ScenarioMIP), so it can be compared to the published results.
"""

ASSESSED_GSAT_TIMESERIES_FILE = (
    f"{POST_PROCESSED_FULL_PREFIX}__timeseries_run_id.feather"
)
"""File which holds the assessed GSAT for each ensemble member, to 2500"""


def get_run_dir(base_dir: Path, scenario: Scenario) -> Path:
    """
    Get the directory in which a scenario's outputs are saved

    Parameters
    ----------
    base_dir
        Base directory for all the runs

    scenario
        Scenario

    Returns
    -------
    :
        Directory for the scenario's outputs
    """
    return base_dir / scenario.slug


def get_run_output_files(run_dir: Path) -> list[Path]:
    """
    Get the files a run writes which other tasks depend on

    The run writes more files than these
    (every DataFrame in every step's output),
    but these are the ones we declare as products.

    Parameters
    ----------
    run_dir
        Directory of the run (see [get_run_dir][(m).])

    Returns
    -------
    :
        Files
    """
    return [
        run_dir / "infilled.feather",
        run_dir / "extended.feather",
        run_dir / "scm_results.feather",
        run_dir / "post_processed__timeseries_quantile.feather",
        run_dir / "post_processed__metadata_quantile.feather",
        run_dir / ASSESSED_GSAT_TIMESERIES_FILE,
        run_dir / f"{POST_PROCESSED_FULL_PREFIX}__metadata_quantile.feather",
        run_dir / REPRODUCTION_CHECK_FILE,
    ]


def get_magicc_paths() -> tuple[Path, Path]:
    """
    Get the paths to MAGICC and its probabilistic distribution

    Returns
    -------
    :
        Path to the MAGICC executable and to the probabilistic distribution

    Raises
    ------
    KeyError
        The environment variables which set the paths are not set
    """
    missing = [
        v
        for v in (MAGICC_EXECUTABLE_ENV_VAR, MAGICC_PROB_DISTRIBUTION_ENV_VAR)
        if not os.environ.get(v)
    ]
    if missing:
        msg = (
            f"Please set the environment variable(s) {missing}. "
            f"{MAGICC_EXECUTABLE_ENV_VAR} should point to "
            "a MAGICC v7.6.0a3 executable, "
            f"{MAGICC_PROB_DISTRIBUTION_ENV_VAR} to "
            "`magicc-ar7-fast-track-drawnset-v0-3-0.json`. "
            "See the README."
        )
        raise KeyError(msg)

    return (
        Path(os.environ[MAGICC_EXECUTABLE_ENV_VAR]),
        Path(os.environ[MAGICC_PROB_DISTRIBUTION_ENV_VAR]),
    )


def get_magicc_dependencies() -> list[Path]:
    """
    Get the MAGICC files the runs depend on, if they are set

    Used so that the runs are re-done if MAGICC or its distribution changes.
    If the environment variables aren't set, this is empty
    (and the runs fail with a clear message when they start).

    Returns
    -------
    :
        MAGICC executable and probabilistic distribution (if set)
    """
    try:
        return list(get_magicc_paths())
    except KeyError:
        return []


def get_n_processes() -> int:
    """
    Get the number of processes to use

    Returns
    -------
    :
        Number of processes (see [N_PROCESSES_ENV_VAR][(m).])
    """
    return int(os.environ.get(N_PROCESSES_ENV_VAR, multiprocessing.cpu_count()))


def download_zenodo_files() -> tuple[Path, ...]:
    """
    Download the files we need from Zenodo (checking their hashes)

    Returns
    -------
    :
        Paths to the downloaded files
    """
    return tuple(get_file(f, downloader=DOWNLOADER) for f in ZENODO_FILES)


def save_attrs_result(obj: Any, out_dir: Path, prefix: str) -> list[Path]:
    """
    Save every DataFrame and Series in an attrs result object

    Each is saved as `{prefix}__{field_name}.feather`.
    Fields which are `None` are skipped.

    Parameters
    ----------
    obj
        attrs object to save

    out_dir
        Directory in which to save

    prefix
        Prefix of the file names

    Returns
    -------
    :
        Files written
    """
    res = []
    for field in attrs.fields(type(obj)):
        value = getattr(obj, field.name)
        if value is None:
            continue

        if not isinstance(value, pd.DataFrame | pd.Series):
            msg = f"Don't know how to save {prefix}.{field.name} ({type(value)})"
            raise TypeError(msg)

        res.append(save_feather(value, out_dir / f"{prefix}__{field.name}.feather"))

    return res


def save_workflow_result(
    result: CMIP7ScenarioMIPWorkflowResult, out_dir: Path
) -> list[Path]:
    """
    Save every step of the workflow's output

    Parameters
    ----------
    result
        Result of running the workflow

    out_dir
        Directory in which to save

    Returns
    -------
    :
        Files written
    """
    res = []
    for name in ("raw", "infilled", "extended", "scm_results"):
        value = getattr(result, name)
        if value is None:
            msg = f"Expected the workflow to produce {name}"
            raise AssertionError(msg)

        res.append(save_feather(value, out_dir / f"{name}.feather"))

    res.extend(save_attrs_result(result.pre_processed, out_dir, "pre_processed"))
    res.extend(save_attrs_result(result.harmonised, out_dir, "harmonised"))
    if result.post_processed is None:
        msg = "Expected the workflow to post-process"
        raise AssertionError(msg)

    res.extend(save_attrs_result(result.post_processed, out_dir, "post_processed"))

    return res


def get_max_abs_diff(
    res: pd.DataFrame | pd.Series, exp: pd.DataFrame | pd.Series
) -> float:  # type: ignore[type-arg]
    """
    Get the maximum absolute difference between two aligned objects

    Parameters
    ----------
    res
        Our result

    exp
        Expected (published) result, with the same index and columns as `res`

    Returns
    -------
    :
        Maximum absolute difference (NaNs ignored)
    """
    return float(np.nanmax(np.abs(res.to_numpy() - exp.to_numpy())))


def check_reproduction(
    result: CMIP7ScenarioMIPWorkflowResult,
    scenario: Scenario,
    published_emissions: pd.DataFrame,
    published_climate_assessment: PublishedClimateAssessment,
) -> dict[str, Any]:
    """
    Check that we reproduce the published emissions and climate assessment

    This follows `test_workflow_cmip7_scenariomip` in gcages exactly,
    except that rather than stopping at the first failure,
    we record the result of every comparison.

    Parameters
    ----------
    result
        Result of running the workflow

    scenario
        Scenario which was run

    published_emissions
        Published harmonised and infilled emissions

    published_climate_assessment
        Published climate assessment

    Returns
    -------
    :
        Result of the check, ready to be written to JSON
    """
    if result.post_processed is None:
        msg = "Expected the workflow to post-process"
        raise AssertionError(msg)

    locator = pix.isin(model=scenario.model, scenario=scenario.scenario)
    comparisons: list[dict[str, Any]] = []

    def compare(
        name: str, atol: float | None, do_compare: Any, max_abs_diff: float
    ) -> None:
        try:
            do_compare()
            passed, problem = True, None
        except AssertionError as exc:
            passed, problem = False, str(exc)

        comparisons.append(
            {
                "name": name,
                "atol": atol,
                "max_abs_diff": max_abs_diff,
                "passed": passed,
                "problem": problem,
            }
        )

    # Infilled emissions
    exp_emms = published_emissions.loc[locator]
    if exp_emms.empty:
        raise AssertionError(scenario)

    res_emms = result.infilled.loc[:, exp_emms.columns].reorder_levels(
        exp_emms.index.names
    )
    compare(
        "infilled-emissions",
        None,
        lambda: assert_frame_equal(res_emms, exp_emms),
        get_max_abs_diff(res_emms.loc[exp_emms.index], exp_emms),
    )

    # Climate assessment timeseries (only up to 2100)
    published = published_climate_assessment
    res_pp = result.post_processed
    exp_ts = published.timeseries_quantile.loc[locator]
    if exp_ts.empty:
        raise AssertionError(scenario)

    res_ts = res_pp.timeseries_quantile.reorder_levels(exp_ts.index.names).loc[
        exp_ts.index, exp_ts.columns
    ]
    res_ts.columns.name = exp_ts.columns.name
    compare(
        "climate-assessment-timeseries",
        TIMESERIES_ATOL,
        lambda: assert_frame_equal(res_ts, exp_ts, atol=TIMESERIES_ATOL),
        get_max_abs_diff(res_ts, exp_ts),
    )

    # Climate assessment metadata
    for name, res_metadata, exp_metadata, atol in (
        (
            "peak-and-2100-warming",
            res_pp.metadata_quantile,
            published.metadata_quantile,
            METADATA_QUANTILE_ATOL,
        ),
        (
            "exceedance-probabilities",
            res_pp.metadata_exceedance_probabilities,
            published.metadata_exceedance_probabilities,
            CLIMATE_ATOL,
        ),
    ):
        exp_ms = exp_metadata.loc[locator]
        if exp_ms.empty:
            raise AssertionError(scenario)

        res_ms = res_metadata.reorder_levels(exp_ms.index.names).loc[exp_ms.index]
        compare(
            name,
            atol,
            lambda res_ms=res_ms, exp_ms=exp_ms, atol=atol: (
                pd.testing.assert_series_equal(
                    res_ms, exp_ms, check_names=False, atol=atol
                )
            ),
            get_max_abs_diff(res_ms, exp_ms),
        )

    return {
        "model": scenario.model,
        "scenario": scenario.scenario,
        "label": scenario.label,
        "published_record": "https://zenodo.org/records/19825038",
        "passed": all(c["passed"] for c in comparisons),
        "comparisons": comparisons,
    }


def post_process_to_2500(scm_results: pd.DataFrame) -> PostProcessingResult:
    """
    Post-process the MAGICC results over the full run (to 2500)

    Parameters
    ----------
    scm_results
        Raw MAGICC results

    Returns
    -------
    :
        Post-processed results, considering all years
        (e.g. peak warming is the peak up to 2500)
    """
    return CMIP7ScenarioMIPWorkflowPostProcessor(last_year=None)(scm_results)


def run_scenario(scenario: Scenario, raw_file: Path, run_dir: Path) -> Path:
    """
    Run the workflow for a scenario, save the results and check them

    Parameters
    ----------
    scenario
        Scenario to run

    raw_file
        File which holds the scenario's raw data

    run_dir
        Directory in which to save the results

    Returns
    -------
    :
        Path to the reproduction check file

    Raises
    ------
    AssertionError
        We don't reproduce the published results
        (the results and the check's result are saved before raising)
    """
    magicc_exe, magicc_prob_distribution = get_magicc_paths()
    n_processes = get_n_processes()

    raw = load_raw_data(scenario.marker, raw_file)

    runner = CMIP7ScenarioMIPWorkflowRunner.from_cmip7_scenariomip_config(
        downloader=DOWNLOADER,
        magicc_exe_path=magicc_exe,
        magicc_prob_distribution_path=magicc_prob_distribution,
        progress=False,
        n_processes=n_processes,
    )

    logger.info(f"Running the workflow for {scenario.label} ({n_processes=})")
    result = runner(raw)
    if result.scm_results is None:
        msg = "Expected the workflow to run MAGICC"
        raise AssertionError(msg)

    run_dir.mkdir(parents=True, exist_ok=True)
    save_workflow_result(result, run_dir)

    logger.info(f"Post-processing {scenario.label} to 2500")
    post_processed_full = post_process_to_2500(result.scm_results)
    save_attrs_result(post_processed_full, run_dir, POST_PROCESSED_FULL_PREFIX)

    logger.info(f"Checking {scenario.label} against the published results")
    check = check_reproduction(
        result,
        scenario=scenario,
        published_emissions=load_published_emissions(downloader=DOWNLOADER),
        published_climate_assessment=load_published_climate_assessment(
            downloader=DOWNLOADER
        ),
    )
    check_file = run_dir / REPRODUCTION_CHECK_FILE
    check_file.write_text(json.dumps(check, indent=2) + "\n")

    if not check["passed"]:
        failed = [c for c in check["comparisons"] if not c["passed"]]
        msg = (
            f"{scenario.label} does not reproduce the published results "
            f"(see {check_file}). Failed comparisons:\n"
            + "\n".join(f"- {c['name']}: {c['problem']}" for c in failed)
        )
        raise AssertionError(msg)

    return check_file
