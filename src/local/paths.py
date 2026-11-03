"""
Path helpers
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]

DATA_RAW_DIR = REPO_ROOT / "data" / "raw"
"""Directory in which we keep raw data

Everything in here is downloaded, hence ignored by git.
"""

DATA_PROCESSED_DIR = REPO_ROOT / "data" / "processed"
"""Directory in which we keep data we produce (ignored by git)"""

FIGURES_DIR = REPO_ROOT / "figures"
"""Directory in which we write generated figures"""

TABLES_DIR = REPO_ROOT / "tables"
"""Directory in which we write generated tables"""
