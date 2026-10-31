#!/bin/bash
# Handy trick (full details here https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425?permalink_comment_id=3799230):
# -e: exit immediately if any command fails
# -u: exit if you reference any unset variable
# -o: pipefail means that a non-zero exit code is returned if any command in the script fails
set -euo pipefail

# Create the CMIP7 ScenarioMIP simple climate model projections manuscript
#
# Based on pytask.
#
# Before the first run you need:
#
# - an IIASA login with access to the ssp_submission database
#   (`uv run ixmp4 login <your-username>`), to download the raw scenario data
# - MAGICC v7.6.0a3 and the CMIP7 ScenarioMIP probabilistic distribution,
#   given by environment variables:
#
#   ```sh
#   export MAGICC_EXECUTABLE_7=/path/to/magicc-v7.6.0a3/bin/magicc
#   export MAGICC_PROB_DISTRIBUTION_PATH=/path/to/magicc-ar7-fast-track-drawnset-v0-3-0.json
#   # Optional, defaults to the number of CPUs
#   export MAGICC_N_PROCESSES=8
#   ```
#
# The MAGICC runs (one task per scenario) take a while.
# Each run checks that it reproduces the published results
# (https://zenodo.org/records/19825038) and fails if it doesn't.
#
# A task re-runs when any of its dependencies or products changed
# (by content, not modification time) or when the module it is defined in changed.
# Helper modules (e.g. `src/local/cmip7_scenariomip_scm_projections/figures.py`)
# are only tracked where a task lists them as a dependency.
# The slow MAGICC runs are in their own module (`task_run_magicc.py`)
# so that editing the other tasks doesn't re-run them.
#
# To see what would run, without running it:
#
# ```sh
# uv run pytask --dry-run
# # Every task's dependencies and products
# uv run pytask collect --nodes
# # The graph of the tasks (needs graphviz, e.g. `brew install graphviz`)
# uv run --with networkx --with pygraphviz pytask dag -o dag.pdf
# ```
#
# To re-run tasks even if they're up to date, use `-f` (force)
# with a selection (otherwise everything re-runs), e.g.
#
# ```sh
# # Re-run MAGICC for the VL scenario
# uv run pytask -f -k "task_run_magicc and vl"
# ```
#
# Tasks are selected like tests in pytest:
#
# - `-k` matches expressions against task IDs (module and function name), e.g.
#   `-k task_warming_figure`.
#   The whole graph is still collected,
#   so the tasks the selected ones depend on are selected too,
#   but they only run if they are out of date.
# - Paths limit which tasks are collected at all.
#   Tasks in other modules are then not part of the graph,
#   so what they produce is used as-is if it exists (even if it is out of date),
#   and the build fails if it doesn't.
#   Prefer `-k` unless you specifically want this.
#   (This is also why `pyproject.toml` doesn't set pytask's `paths`:
#   in pytask 0.6.0, `paths` set there overrides paths given on the command line.)
#
# pytask collects tasks from the directory it is run in,
# so it has to be run from the root of the repository.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
cd "${repo_root}"

# Careful: a `-k` which matches no task deselects everything
# and pytask still reports success, so check the task name.
uv run pytask -k "task_manuscript.py::task_compile_pdf" "$@"
