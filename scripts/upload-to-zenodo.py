"""
Upload information to Zenodo

This also deletes existing files on the record's draft:
what you ask to upload is what ends up there.
We never publish the record: do that in Zenodo's web interface once you're happy.

Before writing the MAGICC output, we check that it reproduces
v0.2 of the published climate assessment (https://zenodo.org/records/19825038)
up to 2100.

You need a Zenodo token in the `ZENODO_TOKEN` environment variable
(or in a `.env` file, see `.env.sample`).

Usage:

```sh
# Build everything, check it and show what would be uploaded
uv run python scripts/upload-to-zenodo.py --dry-run
# Build everything, check it and upload it
uv run python scripts/upload-to-zenodo.py
```
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Annotated

import numpy as np
import pandas as pd
import pandas_indexing as pix
import typer
from gcages.workflows.cmip7_scenariomip import (
    PublishedClimateAssessment,
    load_published_climate_assessment,
)
from loguru import logger
from openscm_zenodo import (
    Affiliation,
    Creator,
    Identifier,
    Metadata,
    Person,
    RelatedIdentifier,
    Right,
    Subject,
    ZenodoClient,
    load_env_file,
)

from local.cmip7_scenariomip_scm_projections.config import (
    METADATA,
    OUTPUT_PDF,
    RUN_DIRS,
)
from local.cmip7_scenariomip_scm_projections.magicc_runs import (
    ASSESSED_GSAT_TIMESERIES_FILE,
    DOWNLOADER,
    METADATA_QUANTILE_ATOL,
    REPRODUCTION_CHECK_FILE,
    TIMESERIES_ATOL,
)
from local.cmip7_scenariomip_scm_projections.scenarios import SCENARIOS
from local.feather_io import load_feather_df
from local.paths import REPO_ROOT

RECORD_ID = "23875147"
"""ID of the Zenodo record (draft) to upload to"""

COMMUNITY = "scenariomip-cmip7"
"""
Zenodo community the record should go in

We don't add the record to it here, see the module's docstring.
"""

REPO_NAME = "CMIP7-ScenarioMIP-Simple-Climate-Model-Projections"
"""Name of this repository, used for the source archive"""

REPO_URL = f"https://github.com/znicholls/{REPO_NAME}"
"""Where this repository lives"""

PUBLISHED_RECORD_DOI = "10.5281/zenodo.19825038"
"""DOI of v0.2 of the published CMIP7 ScenarioMIP emissions and climate assessment"""

OUT_DIR = REPO_ROOT / "build" / "zenodo"
"""Directory in which we write the files to upload"""

SOURCE_ARCHIVE = OUT_DIR / f"{REPO_NAME}-source.zip"
"""Archive of the repository's source"""

GSAT_CSV = OUT_DIR / "magicc-v7-6-0a3_cmip7-scenariomip_assessed-gsat_1750-2500.csv.gz"
"""Assessed GSAT of every ensemble member for every scenario, to 2500 (gzipped CSV)"""

GSAT_CSV_DECIMALS = 6
"""
Number of decimal places to which we round the GSAT values (K) in the CSV

Much smaller than the tolerances of the comparison to the published results
and it more than halves the size of the (compressed) file.
"""

GSAT_CSV_COMPRESSION = {"method": "gzip", "compresslevel": 9, "mtime": 0}
"""
How we compress the GSAT CSV

The time stamp is fixed so the same data always gives the same file
(so re-running doesn't re-upload it).
"""

GSAT_VARIABLE = "Surface Temperature (GSAT)"
"""Name of the assessed GSAT variable"""

GSAT_CSV_INDEX_ORDER = [
    "climate_model",
    "model",
    "scenario",
    "region",
    "variable",
    "unit",
    "run_id",
]
"""Order of the index columns in the CSV"""

N_ENSEMBLE_MEMBERS = 600
"""Number of MAGICC ensemble members we expect for each scenario"""

GSAT_YEARS = range(1750, 2500 + 1)
"""Years we expect in the GSAT output"""

PUBLISHED_LAST_YEAR = 2100
"""Last year considered in the published climate assessment"""

app = typer.Typer()


def run(*args: str, env: dict[str, str] | None = None) -> str:
    """
    Run a command from the root of the repository

    Parameters
    ----------
    *args
        Command and its arguments

    env
        Environment to run in (if not supplied, the current environment)

    Returns
    -------
    :
        The command's stdout, stripped
    """
    res = subprocess.run(
        args, cwd=REPO_ROOT, check=True, capture_output=True, text=True, env=env
    )
    return res.stdout.strip()


def get_git_state(*, allow_dirty: bool) -> tuple[str, bool]:
    """
    Get the current commit and whether there are uncommitted changes

    Parameters
    ----------
    allow_dirty
        Are uncommitted changes allowed?

    Returns
    -------
    :
        Current commit and whether there are uncommitted changes

    Raises
    ------
    RuntimeError
        There are uncommitted changes and `allow_dirty` is `False`
    """
    commit = run("git", "rev-parse", "HEAD")
    status = run("git", "status", "--porcelain")
    dirty = bool(status)
    if dirty and not allow_dirty:
        msg = (
            "There are uncommitted changes, "
            "so the source archive wouldn't match what made the outputs. "
            "Commit them or use `--allow-dirty`. Changes:\n" + status
        )
        raise RuntimeError(msg)

    return commit, dirty


def build_manuscript() -> None:
    """
    Build the manuscript and everything it depends on (incl. the MAGICC runs)

    This is incremental, so it is quick if everything is up to date.
    """
    logger.info("Building the manuscript (and everything it depends on)")
    subprocess.run(
        ["bash", "scripts/create-cmip7-scenariomip-scm-projections-manuscript.sh"],
        cwd=REPO_ROOT,
        check=True,
    )


def create_source_archive(out_file: Path, commit: str, *, dirty: bool) -> Path:
    """
    Create an archive of the repository's source with `git archive`

    Parameters
    ----------
    out_file
        File in which to write the archive

    commit
        Current commit

    dirty
        Are there uncommitted changes?

        If so, we archive the working tree as it is
        (everything git would add with `git add --all`, i.e. respecting `.gitignore`)
        using a temporary index, so the repository's own index isn't touched.
        Otherwise, we archive `commit`.

    Returns
    -------
    :
        `out_file`
    """
    if dirty:
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
            run("git", "read-tree", "HEAD", env=env)
            run("git", "add", "--all", env=env)
            to_archive = run("git", "write-tree", env=env)

    else:
        to_archive = commit

    archived_files = run("git", "ls-tree", "-r", "--name-only", to_archive).split("\n")
    secrets = [f for f in archived_files if Path(f).name == ".env"]
    if secrets:
        msg = f"Refusing to archive files which may hold secrets: {secrets}"
        raise AssertionError(msg)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    # Fix the time stamps so the same source always gives the same archive
    # (git only does this itself when archiving a commit, not a tree)
    commit_time = run("git", "show", "-s", "--format=%cI", commit)
    run(
        "git",
        "archive",
        "--format=zip",
        f"--prefix={REPO_NAME}/",
        f"--mtime={commit_time}",
        f"--output={out_file}",
        to_archive,
    )
    logger.info(f"Archived {len(archived_files)} files to {out_file}")

    return out_file


def load_gsat() -> pd.DataFrame:
    """
    Load the assessed GSAT of every ensemble member for every scenario

    Returns
    -------
    :
        Assessed GSAT, scenarios in the order of
        [SCENARIOS][local.cmip7_scenariomip_scm_projections.scenarios.SCENARIOS]

    Raises
    ------
    AssertionError
        A run didn't pass its reproduction check
    """
    res_l = []
    for scenario, run_dir in zip(SCENARIOS, RUN_DIRS, strict=True):
        check = json.loads((run_dir / REPRODUCTION_CHECK_FILE).read_text())
        if not check["passed"]:
            msg = f"{scenario.label}'s run didn't pass its reproduction check"
            raise AssertionError(msg)

        gsat = load_feather_df(run_dir / ASSESSED_GSAT_TIMESERIES_FILE)
        res_l.append(
            gsat.reorder_levels(GSAT_CSV_INDEX_ORDER).sort_index(level="run_id")
        )

    return pd.concat(res_l)


def check_gsat_shape(gsat: pd.DataFrame) -> None:
    """
    Check that the GSAT output has every scenario, member and year

    Parameters
    ----------
    gsat
        Assessed GSAT

    Raises
    ------
    AssertionError
        Something is missing or duplicated
    """
    if not gsat.index.is_unique:
        msg = "Duplicate timeseries"
        raise AssertionError(msg)

    if gsat.isna().any().any():
        msg = "NaNs in the output"
        raise AssertionError(msg)

    if list(gsat.columns) != list(GSAT_YEARS):
        msg = f"Unexpected years: {gsat.columns}"
        raise AssertionError(msg)

    if set(gsat.index.get_level_values("variable")) != {GSAT_VARIABLE}:
        msg = "Unexpected variables"
        raise AssertionError(msg)

    if set(gsat.index.get_level_values("unit")) != {"K"}:
        msg = "Unexpected units"
        raise AssertionError(msg)

    n_members = gsat.groupby(["model", "scenario"]).size()
    exp_members = pd.Series(
        N_ENSEMBLE_MEMBERS,
        index=pd.MultiIndex.from_tuples(
            [(s.model, s.scenario) for s in SCENARIOS], names=["model", "scenario"]
        ),
    )
    pd.testing.assert_series_equal(
        n_members.sort_index(), exp_members.sort_index(), check_names=False
    )


def assert_close(name: str, res: pd.DataFrame, exp: pd.DataFrame, atol: float) -> None:
    """
    Assert that our values are close to the published ones

    Parameters
    ----------
    name
        Name of the comparison (for messages)

    res
        Our values

    exp
        Published values

    atol
        Absolute tolerance

    Raises
    ------
    AssertionError
        The values aren't close (or don't line up)
    """
    res_aligned = res.loc[exp.index, exp.columns]
    if res_aligned.isna().any().any() or exp.isna().any().any():
        msg = f"{name}: NaNs in the comparison"
        raise AssertionError(msg)

    abs_diff = (res_aligned - exp).abs()
    max_abs_diff = float(np.max(abs_diff.to_numpy()))
    if max_abs_diff > atol:
        worst = abs_diff.max(axis="columns").sort_values(ascending=False).head(5)
        msg = (
            f"{name}: max absolute difference to the published values "
            f"is {max_abs_diff:.2e} ({atol=:.0e}). Worst rows:\n{worst}"
        )
        raise AssertionError(msg)

    logger.info(f"{name}: matches ({max_abs_diff=:.2e}, {atol=:.0e})")


def check_against_published(
    gsat: pd.DataFrame, published: PublishedClimateAssessment
) -> None:
    """
    Check that the GSAT output reproduces the published climate assessment

    We compare up to 2100, the last year of the published assessment.
    The tolerances are the same as in the reproduction check in the MAGICC runs
    (see `local.cmip7_scenariomip_scm_projections.magicc_runs`).

    Parameters
    ----------
    gsat
        Assessed GSAT of each ensemble member

    published
        Published climate assessment

    Raises
    ------
    AssertionError
        We don't reproduce the published results
    """
    group_levels = [lvl for lvl in gsat.index.names if lvl != "run_id"]

    def get_quantiles(df: pd.DataFrame, quantiles: list[float]) -> pd.DataFrame:
        return (
            df.groupby(group_levels)
            .quantile(quantiles)
            .rename_axis(index={None: "quantile"})
        )

    # Every scenario we have is in the published results and vice versa
    pub_scenarios = set(
        published.timeseries_quantile.index.droplevel(
            [
                lvl
                for lvl in published.timeseries_quantile.index.names
                if lvl not in ("model", "scenario")
            ]
        )
    )
    res_scenarios = set(
        gsat.index.droplevel(
            [lvl for lvl in gsat.index.names if lvl not in ("model", "scenario")]
        )
    )
    if pub_scenarios != res_scenarios:
        msg = f"Scenarios differ: {pub_scenarios ^ res_scenarios}"
        raise AssertionError(msg)

    # Timeseries quantiles
    exp_ts = published.timeseries_quantile.loc[pix.isin(variable=GSAT_VARIABLE)]
    quantiles = sorted(exp_ts.index.get_level_values("quantile").unique())
    res_ts = get_quantiles(gsat.loc[:, exp_ts.columns], quantiles).reorder_levels(
        exp_ts.index.names
    )
    assert_close("GSAT timeseries quantiles", res_ts, exp_ts, atol=TIMESERIES_ATOL)

    # Peak warming and warming in 2100 (the published values only consider to 2100)
    exp_metadata = published.metadata_quantile.loc[
        pix.isin(variable=GSAT_VARIABLE)
    ].to_frame("value")
    metadata_quantiles = sorted(
        exp_metadata.index.get_level_values("quantile").unique()
    )
    to_last_year = gsat.loc[:, :PUBLISHED_LAST_YEAR]
    res_metadata = pd.concat(
        [
            pix.assignlevel(
                get_quantiles(
                    to_last_year.max(axis="columns").to_frame("value"),
                    metadata_quantiles,
                ),
                metric="max",
            ),
            pix.assignlevel(
                get_quantiles(
                    to_last_year[[PUBLISHED_LAST_YEAR]].rename(
                        columns={PUBLISHED_LAST_YEAR: "value"}
                    ),
                    metadata_quantiles,
                ),
                metric=PUBLISHED_LAST_YEAR,
            ),
        ]
    ).reorder_levels(exp_metadata.index.names)
    assert_close(
        "Peak warming and warming in 2100 quantiles",
        res_metadata,
        exp_metadata,
        atol=METADATA_QUANTILE_ATOL,
    )


def write_gsat_csv(gsat: pd.DataFrame, out_file: Path) -> Path:
    """
    Write the GSAT output to a gzipped CSV and check that it reads back exactly

    Parameters
    ----------
    gsat
        Assessed GSAT

    out_file
        File in which to write

    Returns
    -------
    :
        `out_file`
    """
    out_file.parent.mkdir(parents=True, exist_ok=True)
    gsat.to_csv(out_file, compression=GSAT_CSV_COMPRESSION)

    read_back = pd.read_csv(
        out_file,
        index_col=list(range(gsat.index.nlevels)),
        float_precision="round_trip",
    )
    np.testing.assert_array_equal(read_back.to_numpy(), gsat.to_numpy())
    if [int(c) for c in read_back.columns] != list(gsat.columns):
        msg = "Columns don't read back"
        raise AssertionError(msg)

    logger.info(f"Wrote {gsat.shape[0]} timeseries to {out_file}")

    return out_file


def get_metadata(commit: str, *, dirty: bool) -> Metadata:
    """
    Get the record's metadata

    Parameters
    ----------
    commit
        Commit the source archive was made from

    dirty
        Did the source archive include uncommitted changes?

    Returns
    -------
    :
        Metadata
    """
    manuscript_metadata = tomllib.loads(METADATA.read_text())
    title_info = manuscript_metadata["title_info"]
    version = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"][
        "version"
    ]

    commit_link = f'<a href="{REPO_URL}/tree/{commit}">{commit[:7]}</a>'
    source_description = f"commit {commit_link}"
    if dirty:
        source_description += " plus uncommitted changes"

    scenarios = ", ".join(s.label for s in SCENARIOS)
    description = f"""
<p>
Pre-print (really, pre-pre-print) of the forthcoming article.
This has not been reviewed by the core author team or a scientific journal yet
so use with caution.
</p>
<p>This record contains:</p>
<ul>
<li>
<code>{OUTPUT_PDF.name}</code>: the manuscript.
</li>
<li>
<code>{SOURCE_ARCHIVE.name}</code>: the source code used to produce the manuscript
and data ({source_description} of <a href="{REPO_URL}">{REPO_URL}</a>).
</li>
<li>
<code>{GSAT_CSV.name}</code> (gzipped CSV):
the global-mean surface air temperature (GSAT) change relative to 1850-1900
(in line with the IPCC AR6 assessment of historical warming)
of each of the {N_ENSEMBLE_MEMBERS} ensemble members
of MAGICC v7.6.0a3 (CMIP7 ScenarioMIP probabilistic distribution)
for each of the seven CMIP7 ScenarioMIP marker scenarios ({scenarios}),
from {GSAT_YEARS[0]} to {GSAT_YEARS[-1]}
(K, rounded to {GSAT_CSV_DECIMALS} decimal places).
Up to {PUBLISHED_LAST_YEAR}, this reproduces v0.2 of the published
CMIP7 ScenarioMIP climate assessment
(<a href="https://doi.org/{PUBLISHED_RECORD_DOI}">{PUBLISHED_RECORD_DOI}</a>).
</li>
</ul>
""".strip()

    return Metadata(
        title=f"Pre-print: {title_info['title']}",
        resource_type="publication-preprint",
        creators=(
            Creator(
                entity=Person(
                    family_name="Nicholls",
                    given_name="Zebedee",
                    identifiers=(
                        Identifier(scheme="orcid", identifier="0000-0002-4767-2723"),
                    ),
                ),
                affiliations=(
                    Affiliation(name="Climate Resource S GmbH"),
                    Affiliation(
                        name="International Institute for Applied Systems Analysis"
                    ),
                    # Climate Resource (Australia)
                    Affiliation(id="01kk86953"),
                ),
            ),
        ),
        publication_date=dt.date.today().isoformat(),
        publisher="Zenodo",
        description=description,
        version=f"v{version}",
        rights=(Right(id="cc-by-4.0"),),
        subjects=tuple(Subject(subject=k) for k in title_info["keywords"]),
        related_identifiers=(
            RelatedIdentifier(
                identifier=REPO_URL,
                scheme="url",
                relation_type="issupplementedby",
                resource_type="software",
            ),
            RelatedIdentifier(
                identifier=PUBLISHED_RECORD_DOI,
                scheme="doi",
                relation_type="references",
                resource_type="dataset",
            ),
        ),
        languages=("eng",),
    )


@app.command()
def main(
    dry_run: Annotated[
        bool,
        typer.Option(help="Create and check the files, but don't touch Zenodo"),
    ] = False,
    allow_dirty: Annotated[
        bool,
        typer.Option(
            help="Allow uncommitted changes (the working tree is archived as is)"
        ),
    ] = False,
    skip_build: Annotated[
        bool,
        typer.Option(help="Don't (re-)build the manuscript before uploading"),
    ] = False,
    record_id: Annotated[str, typer.Option(help="Zenodo record to upload to")] = (
        RECORD_ID
    ),
) -> None:
    """Upload the manuscript, its source and the GSAT projections to Zenodo"""
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.enable("openscm_zenodo")

    commit, dirty = get_git_state(allow_dirty=allow_dirty)
    if not skip_build:
        build_manuscript()
        # The build shouldn't change any tracked files, but check
        commit_after, dirty_after = get_git_state(allow_dirty=True)
        if (commit_after, dirty_after) != (commit, dirty):
            msg = "The build changed the repository"
            raise AssertionError(msg)

    source_archive = create_source_archive(SOURCE_ARCHIVE, commit, dirty=dirty)

    gsat = load_gsat()
    check_gsat_shape(gsat)
    gsat = gsat.round(GSAT_CSV_DECIMALS)
    # Check what we write (i.e. after rounding), just before writing
    check_against_published(
        gsat, load_published_climate_assessment(downloader=DOWNLOADER)
    )
    gsat_csv = write_gsat_csv(gsat, GSAT_CSV)

    to_upload = [OUTPUT_PDF, source_archive, gsat_csv]
    metadata = get_metadata(commit, dirty=dirty)
    problems = metadata.find_problems()
    if problems:
        msg = f"Problems with the metadata: {problems}"
        raise AssertionError(msg)

    if dry_run:
        logger.info(
            "Dry run, not touching Zenodo. Would upload:\n"
            + "\n".join(f"- {p} ({p.stat().st_size / 1e6:.1f} MB)" for p in to_upload)
        )
        logger.info(f"Metadata:\n{json.dumps(metadata.to_json(), indent=2)}")
        return

    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        load_env_file(env_file)

    with ZenodoClient() as client:
        logger.info(f"Using {client.token_source}")
        if not client.is_draft(record_id):
            msg = f"{record_id} isn't a draft, we only upload to drafts"
            raise AssertionError(msg)

        client.update_metadata(record_id, metadata)
        client.mirror_files(record_id, to_upload, progress=True)

        draft = client.get_draft(record_id)
        logger.info(
            f"Done. Reserved DOI: {draft.doi}. "
            f"Review and publish at {client.zenodo_domain_url}/uploads/{record_id}. "
            f"After publishing, request inclusion in the {COMMUNITY!r} community "
            "(see this script's docstring)."
        )


if __name__ == "__main__":
    app()
