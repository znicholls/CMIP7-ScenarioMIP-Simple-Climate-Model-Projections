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

**MAGICC.**
You need MAGICC v7.6.0a3 and the CMIP7 ScenarioMIP probabilistic distribution
(`magicc-ar7-fast-track-drawnset-v0-3-0.json`).
Tell the build where they are with environment variables:

```sh
export MAGICC_EXECUTABLE_7=/path/to/magicc-v7.6.0a3/bin/magicc
export MAGICC_PROB_DISTRIBUTION_PATH=/path/to/magicc-ar7-fast-track-drawnset-v0-3-0.json
# Optional: number of processes to use (defaults to the number of CPUs)
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

## How the build works

The build is driven by [pytask](https://pytask-dev.readthedocs.io/).
The tasks are in `tasks/cmip7_scenariomip_scm_projections`,
the code they call is in `src/local`.

1. `task_download.py`: download the raw data for each scenario
   (from ssp_submission) and the other inputs (from Zenodo).
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
