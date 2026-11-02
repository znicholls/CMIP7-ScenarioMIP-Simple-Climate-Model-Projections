# CMIP7 ScenarioMIP Simple Climate Model Projections

In this repository, we generate a manuscript describing
simple climate model (MAGICC) projections of the CMIP7 ScenarioMIP scenarios.

## Status

- prototype: the project is just starting up, the manuscript text is all placeholders

## Installation

We do all our environment management using [uv](https://docs.astral.sh/uv/).
To create the virtual environment, run

```sh
uv sync
uv run pre-commit install
```

(or `make virtual-environment`).

You will also need a LaTeX installation with `pdflatex` and `bibtex`.

### Inputs you have to supply

**Raw scenario data.**
The raw scenario data is downloaded from the ssp_submission database
(an IIASA Scenario Explorer database).
This needs an IIASA login with the right permissions.
If you haven't logged in yet, run

```sh
uv run ixmp4 login <your-username>
```

The downloaded data is checked against the checksums recorded in gcages,
so we know it is exactly the data used in CMIP7 ScenarioMIP.

**MAGICC (only if you're not on Linux).**
The build downloads MAGICC v7.6.0a3
(from [the GitLab job which built it](https://gitlab.com/magicc/magicc/-/jobs/8636354904/artifacts/browse))
and the CMIP7 ScenarioMIP probabilistic distribution
(`magicc-ar7-fast-track-drawnset-v0-3-0.json`,
from [Zenodo](https://doi.org/10.5281/zenodo.14678474)).
MAGICC's bundle only has a binary for Linux (x86-64).
On anything else, the build fails and tells you to
[build MAGICC from source](https://gitlab.com/magicc/magicc/-/commits/v7.6.0a3)
and say where your binary is:

```sh
export MAGICC_EXECUTABLE_7=/path/to/magicc-v7.6.0a3/bin/magicc
```

The binary needs MAGICC's `run` directory at `../run` relative to itself
(you can copy it from the downloaded bundle in `data/raw/magicc/magicc-v7.6.0a3/run`).
If `MAGICC_EXECUTABLE_7` isn't set
and `magicc/magicc-v7.6.0a3/bin/magicc-darwin-arm64` exists
(the `magicc/` directory is ignored by git),
`scripts/create-cmip7-scenariomip-scm-projections-manuscript.sh` uses that.

Optional environment variables:

```sh
# Use a different probabilistic distribution file than the downloaded one
export MAGICC_PROB_DISTRIBUTION_PATH=/path/to/magicc-ar7-fast-track-drawnset-v0-3-0.json
# Number of processes to use (defaults to the number of CPUs)
export MAGICC_N_PROCESSES=8
```

Everything else (historical emissions, the infilling database,
the published results we check against
and the Indicators of Global Climate Change data)
is downloaded from Zenodo by the build.

## Creating the manuscript

```sh
bash scripts/create-cmip7-scenariomip-scm-projections-manuscript.sh
```

(or `make manuscript`).
The PDF is written to `compiled-manuscripts/cmip7-scenariomip-scm-projections.pdf`.
See the script for how to run only part of the build, force re-runs etc.

## Uploading to Zenodo

`scripts/upload-to-zenodo.py` uploads the compiled manuscript,
the source of this repository (via `git archive`)
and the assessed GSAT of every MAGICC ensemble member to 2500 (gzipped CSV)
to the manuscript's Zenodo record (a draft),
and sets the record's metadata,
all with [openscm-zenodo](https://github.com/openscm/OpenSCM-zenodo).
It never publishes the record.
It also doesn't add the record to the
[ScenarioMIP-CMIP7 community](https://zenodo.org/communities/scenariomip-cmip7):
for now, publish the record first,
then request its inclusion with openscm-zenodo's
`ZenodoClient.request_community_inclusion` (see the script's docstring).
Before writing the CSV, it checks that the data reproduces
the published climate assessment up to 2100.

You need a Zenodo token in `ZENODO_TOKEN` (or in `.env`, see `.env.sample`).

```sh
# Build, check and show what would be uploaded
uv run python scripts/upload-to-zenodo.py --dry-run
# Build, check and upload
uv run python scripts/upload-to-zenodo.py
```

## How the build works

The build is driven by [pytask](https://pytask-dev.readthedocs.io/).
The tasks are in `tasks/cmip7_scenariomip_scm_projections`,
the code they call is in `src/local`.

1. `task_download.py`: download the raw data for each scenario
   (from ssp_submission) and the other inputs (from Zenodo).
   `task_download_magicc.py`: download MAGICC and its probabilistic distribution.
   `task_download_igcc.py`: download the
   [Indicators of Global Climate Change 2025](https://doi.org/10.5194/essd-18-3889-2026)
   data ([IGCC-2025a](https://doi.org/10.5281/zenodo.21494229)),
   which we compare to in the figure of projected warming.
1. `task_run_magicc.py`: for each scenario, run the entire CMIP7 ScenarioMIP workflow
   with [gcages](https://github.com/openscm/gcages)
   (commit `c0c33d2ac83d502dc423895dc63ec06fff461960`):
   pre-processing, harmonisation, infilling, extension to 2500,
   MAGICC and post-processing.
   Every step's output is saved as feather files in
   `data/processed/magicc-runs/<scenario>/`
   (load them with `local.feather_io.load_feather`).
   Each run also checks that it reproduces the published
   harmonised and infilled emissions and climate assessment
   ([v0.2](https://zenodo.org/records/19825038)),
   exactly as gcages' test of the workflow does.
   The result is written to `reproduction-check.json` in the run's directory
   and the run fails if the check fails.
1. `task_tex_inputs.py`: summarise the runs, make the figures and tables,
   generate the author contributions statement from the metadata.
1. `task_manuscript.py`: assemble the manuscript and compile it to PDF.

### The manuscript's source

The manuscript's text is in `manuscripts/cmip7-scenariomip-scm-projections`,
split into one file per section.
It is put into [IOP's LaTeX template](https://publishingsupport.iopscience.iop.org/wp-content/uploads/2025/07/ioplatextemplate.zip)
(`iop-latex-template`) by `src/local/iop_latex.py`.

- The title, authors, affiliations and author contributions come from `metadata.toml`.
- Generated figures are included with tags,
  e.g. `\includegraphics{@warming-figure@}`,
  and generated files (e.g. tables) are inlined in place of their tags,
  e.g. `@peak-warming-table@`.
  The tags are defined in `src/local/cmip7_scenariomip_scm_projections/config.py`
  (`FIGURE_FILES` and `FILES_TO_INLINE`).
  The build fails if a tag isn't replaced.
- Shorthand (e.g. `CO_2`) is expanded using `replacements.yaml`.
- Statements which depend on the data are marked with value check comments, e.g.

  ```latex
  % value-check: {"tag": "peak-warming-median-range", "unit": "K", "lower": 1.4, "upper": 4.0}
  ```

  The build calculates the value
  (the checks are in `src/local/cmip7_scenariomip_scm_projections/value_checks.py`)
  and fails if it is outside the range or if there is no check for the tag.
  See `src/local/value_checks.py` for details.

## Development

### Tools

In this repository, we use the following tools:

- git for version-control
- [uv](https://docs.astral.sh/uv/) for environment management
- [pre-commit](https://pre-commit.com/) for basic file checks
  and code formatting with [ruff](https://docs.astral.sh/ruff/formatter/)
- [pytask](https://pytask-dev.readthedocs.io/) to drive the build
- [jupytext](https://jupytext.readthedocs.io/en/latest/index.html)
  to track any notebooks as `.py` files

### Repository structure

This repository follows the structure of
[CMIP7-GHG-Concentration-Manuscripts](https://github.com/climate-resource/CMIP7-GHG-Concentration-Manuscripts).
