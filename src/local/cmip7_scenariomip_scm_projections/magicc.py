"""
Getting MAGICC and its probabilistic distribution

MAGICC v7.6.0a3 is downloaded from the artifacts of the GitLab job which built it.
The bundle only has a binary for Linux (x86-64).
On any other platform, you have to build MAGICC from source
and tell us where the binary is with `MAGICC_EXECUTABLE_7`
(the binary needs the bundle's `run` directory at `../run`, relative to itself).

The probabilistic distribution used in CMIP7 ScenarioMIP
(`magicc-ar7-fast-track-drawnset-v0-3-0.json`) is downloaded from Zenodo.

Either can be overridden with an environment variable
(`MAGICC_EXECUTABLE_7` and `MAGICC_PROB_DISTRIBUTION_PATH`).
"""

from __future__ import annotations

import os
import platform
import tarfile
import zipfile
from pathlib import Path

import pooch

from local.paths import DATA_RAW_DIR

MAGICC_EXECUTABLE_ENV_VAR = "MAGICC_EXECUTABLE_7"
"""Environment variable which gives the path to the MAGICC v7.6.0a3 executable"""

MAGICC_PROB_DISTRIBUTION_ENV_VAR = "MAGICC_PROB_DISTRIBUTION_PATH"
"""Environment variable which gives the path to MAGICC's probabilistic distribution"""

MAGICC_VERSION = "v7.6.0a3"
"""Version of MAGICC we use"""

MAGICC_SOURCE_URL = "https://gitlab.com/magicc/magicc/-/commits/v7.6.0a3"
"""Where MAGICC's source (at the version we use) is"""

MAGICC_BUNDLE_URL = (
    "https://gitlab.com/magicc/magicc/-/jobs/8636354904/artifacts/download"
)
"""
Where to download MAGICC from (the artifacts of the job which built it)

Browse them at https://gitlab.com/magicc/magicc/-/jobs/8636354904/artifacts/browse
"""

MAGICC_BUNDLE_HASH = (
    "sha256:4a3c162068539cc24fc7c087f637c7c2cb086c0c8696d6991e8539045bd3ceb3"
)
"""Hash of the artifacts' zip file (GitLab doesn't give one, so we calculated it)"""

MAGICC_BUNDLE_TARBALL = f"build/magicc-{MAGICC_VERSION}.tar.gz"
"""Path of MAGICC's tarball within the artifacts' zip file"""

MAGICC_DIR = DATA_RAW_DIR / "magicc" / f"magicc-{MAGICC_VERSION}"
"""Directory into which we extract MAGICC"""

MAGICC_BUNDLE_FILES = tuple(
    MAGICC_DIR / f for f in ("VERSION", "bin/magicc", "run/MAGCFG_DEFAULTALL.CFG")
)
"""Files we check for after extracting MAGICC (they are the download's products)"""

BUNDLED_EXECUTABLES = {
    ("Linux", "x86_64"): MAGICC_DIR / "bin" / "magicc",
}
"""Executable in the bundle for each platform (`platform.system()`, `.machine()`)"""

PROB_DISTRIBUTION_FILENAME = "magicc-ar7-fast-track-drawnset-v0-3-0.json"
"""Name of the probabilistic distribution's file"""

PROB_DISTRIBUTION_URL = (
    f"https://zenodo.org/records/14678474/files/{PROB_DISTRIBUTION_FILENAME}?download=1"
)
"""
Where to download the probabilistic distribution from

https://doi.org/10.5281/zenodo.14678474 (v0.3.0)
"""

PROB_DISTRIBUTION_HASH = "md5:a9d439b8d3aabc123465fe90f65c9866"
"""Hash of the probabilistic distribution (as given by Zenodo)"""

PROB_DISTRIBUTION_DOWNLOAD_PATH = DATA_RAW_DIR / "magicc" / PROB_DISTRIBUTION_FILENAME
"""Where we save the probabilistic distribution"""


class MAGICCNotAvailableError(RuntimeError):
    """
    Raised when the MAGICC bundle has no binary for this platform
    """

    def __init__(self, system: str, machine: str) -> None:
        msg = (
            f"The MAGICC {MAGICC_VERSION} bundle ({MAGICC_BUNDLE_URL}) "
            f"has no binary for this platform ({system}, {machine}). "
            "Its binaries are for: "
            f"{sorted(BUNDLED_EXECUTABLES)}. "
            "You need to build MAGICC from source "
            f"({MAGICC_SOURCE_URL}), "
            f"then set {MAGICC_EXECUTABLE_ENV_VAR} to the path of your binary. "
            "The binary needs MAGICC's `run` directory at `../run` relative to itself "
            f"(you can copy it from {MAGICC_DIR / 'run'})."
        )
        super().__init__(msg)


def download_magicc() -> tuple[Path, ...]:
    """
    Download MAGICC (checking its hash) and extract it

    We download it even if `MAGICC_EXECUTABLE_7` is set
    (e.g. its `run` directory is useful for a binary built from source).

    Returns
    -------
    :
        [MAGICC_BUNDLE_FILES][(m).]

    Raises
    ------
    MAGICCNotAvailableError
        The bundle has no binary for this platform
        and `MAGICC_EXECUTABLE_7` isn't set
    """
    zip_file = pooch.retrieve(
        MAGICC_BUNDLE_URL,
        known_hash=MAGICC_BUNDLE_HASH,
        fname=f"magicc-{MAGICC_VERSION}-artifacts.zip",
        path=MAGICC_DIR.parent,
        progressbar=False,
    )
    MAGICC_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_file) as zf, zf.open(MAGICC_BUNDLE_TARBALL) as tarball:
        with tarfile.open(fileobj=tarball, mode="r:gz") as tf:
            # The `data` filter refuses anything which would end up
            # outside `MAGICC_DIR` (or links, devices etc.)
            tf.extractall(MAGICC_DIR, filter="data")

    missing = [f for f in MAGICC_BUNDLE_FILES if not f.exists()]
    if missing:
        msg = f"Expected MAGICC's bundle to contain {missing}"
        raise AssertionError(msg)

    # Raises if there is no binary we can use, so we find out now
    get_magicc_executable()

    return MAGICC_BUNDLE_FILES


def download_prob_distribution() -> Path:
    """
    Download MAGICC's probabilistic distribution (checking its hash)

    Returns
    -------
    :
        [PROB_DISTRIBUTION_DOWNLOAD_PATH][(m).]
    """
    return Path(
        pooch.retrieve(
            PROB_DISTRIBUTION_URL,
            known_hash=PROB_DISTRIBUTION_HASH,
            fname=PROB_DISTRIBUTION_FILENAME,
            path=PROB_DISTRIBUTION_DOWNLOAD_PATH.parent,
            progressbar=False,
        )
    )


def get_executable_override() -> Path | None:
    """Get the MAGICC executable set by the environment variable, if it is set"""
    value = os.environ.get(MAGICC_EXECUTABLE_ENV_VAR)

    return Path(value) if value else None


def get_prob_distribution_path() -> Path:
    """
    Get the path to MAGICC's probabilistic distribution

    Returns
    -------
    :
        The environment variable's value if it is set,
        otherwise where we download the distribution to
    """
    value = os.environ.get(MAGICC_PROB_DISTRIBUTION_ENV_VAR)

    return Path(value) if value else PROB_DISTRIBUTION_DOWNLOAD_PATH


def get_magicc_executable() -> Path:
    """
    Get the path to the MAGICC executable

    Returns
    -------
    :
        The environment variable's value if it is set,
        otherwise the bundle's binary for this platform

    Raises
    ------
    MAGICCNotAvailableError
        The environment variable isn't set and the bundle has no binary for this
        platform
    """
    override = get_executable_override()
    if override is not None:
        return override

    system, machine = platform.system(), platform.machine()
    try:
        return BUNDLED_EXECUTABLES[(system, machine)]
    except KeyError:
        raise MAGICCNotAvailableError(system, machine) from None


def get_magicc_dependencies() -> list[Path]:
    """
    Get the MAGICC files the runs depend on

    Used so that the runs are re-done if MAGICC or its distribution changes
    (and so they come after the downloads).
    This never raises, even if there is no binary for this platform
    (the download raises instead), so the rest of the build can be collected.

    Returns
    -------
    :
        The bundle's files, the executable set by `MAGICC_EXECUTABLE_7` (if set)
        and the probabilistic distribution
    """
    override = get_executable_override()
    executable_files = [override] if override is not None else []

    return [*MAGICC_BUNDLE_FILES, *executable_files, get_prob_distribution_path()]
