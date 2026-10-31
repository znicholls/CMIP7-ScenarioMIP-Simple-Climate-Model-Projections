"""
Saving and loading pandas objects as feather files

`pd.DataFrame.to_feather` drops the index and needs string column names.
Our data has a (multi-)index and years as columns,
so we go via pyarrow, which keeps the index in the file's pandas metadata,
and record the columns' type so we can restore it on loading.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.feather

METADATA_KEY = b"local"
"""Key of our metadata in the file's schema metadata"""

NON_STR_TYPES = {"int": int, "float": float}
"""Types of non-string values we support in mixed-type index levels"""


def stringify_mixed_index_levels(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, dict[str, str]]]:
    """
    Convert index levels which mix strings and numbers to strings

    Arrow can't store a column which mixes types
    (e.g. gcages' `metric` level, which holds "max" and 2100).

    Returns
    -------
    :
        Converted data and, for each converted level,
        the type of each value which wasn't a string (keyed by its string form)
    """
    converted = {}
    for i, name in enumerate(df.index.names):
        values = df.index.get_level_values(i)
        if values.dtype != object:
            continue

        non_str = {str(v): type(v) for v in values.unique() if not isinstance(v, str)}
        if not non_str or len(non_str) == values.nunique():
            # All strings, or all non-strings (arrow handles these)
            continue

        unsupported = {k: t for k, t in non_str.items() if t not in (int, float)}
        if unsupported:
            msg = f"Can't save index level {name!r} with values {unsupported}"
            raise TypeError(msg)

        converted[name] = {k: t.__name__ for k, t in non_str.items()}
        df.index = df.index.set_levels(
            df.index.levels[i].map(str), level=i, verify_integrity=False
        )

    return df, converted


def restore_mixed_index_levels(
    df: pd.DataFrame, converted: dict[str, dict[str, str]]
) -> pd.DataFrame:
    """Undo [stringify_mixed_index_levels][(m).]"""
    for name, types in converted.items():
        df.index = df.index.set_levels(
            df.index.levels[df.index.names.index(name)].map(
                lambda v, types=types: (NON_STR_TYPES[types[v]](v) if v in types else v)
            ),
            level=name,
            verify_integrity=False,
        )

    return df


def save_feather(obj: pd.DataFrame | pd.Series, fp: Path) -> Path:  # type: ignore[type-arg]
    """
    Save a [pd.DataFrame][pandas.DataFrame] or [pd.Series][pandas.Series]

    Parameters
    ----------
    obj
        Object to save

    fp
        File in which to save

    Returns
    -------
    :
        `fp`
    """
    is_series = isinstance(obj, pd.Series)
    df = obj.to_frame("value") if is_series else obj.copy()

    columns_name = df.columns.name
    if pd.api.types.is_integer_dtype(df.columns):
        columns_type = "int"
    elif pd.api.types.is_float_dtype(df.columns):
        columns_type = "float"
    else:
        columns_type = "str"

    df.columns = df.columns.astype(str)
    df.columns.name = None

    mixed_index_levels: dict[str, dict[str, str]] = {}
    if isinstance(df.index, pd.MultiIndex):
        df, mixed_index_levels = stringify_mixed_index_levels(df)

    table = pa.Table.from_pandas(df, preserve_index=True)
    local_metadata = {
        "is_series": is_series,
        "series_name": obj.name if is_series else None,
        "columns_type": columns_type,
        "columns_name": columns_name,
        "mixed_index_levels": mixed_index_levels,
    }
    table = table.replace_schema_metadata(
        {
            **(table.schema.metadata or {}),
            METADATA_KEY: json.dumps(local_metadata).encode(),
        }
    )

    fp.parent.mkdir(parents=True, exist_ok=True)
    pyarrow.feather.write_feather(table, fp)

    return fp


def load_feather(fp: Path) -> pd.DataFrame | pd.Series:  # type: ignore[type-arg]
    """
    Load a file saved with [save_feather][(m).]

    Parameters
    ----------
    fp
        File to load

    Returns
    -------
    :
        Loaded object
    """
    table = pyarrow.feather.read_table(fp)
    local_metadata = json.loads(table.schema.metadata[METADATA_KEY])

    df = table.to_pandas()
    if local_metadata["columns_type"] in ("int", "float"):
        df.columns = df.columns.astype(local_metadata["columns_type"])

    df.columns.name = local_metadata["columns_name"]
    if local_metadata.get("mixed_index_levels"):
        df = restore_mixed_index_levels(df, local_metadata["mixed_index_levels"])

    if local_metadata["is_series"]:
        res = df["value"]
        res.name = local_metadata["series_name"]
        return res

    return df


def load_feather_df(fp: Path) -> pd.DataFrame:
    """
    Load a file saved with [save_feather][(m).] that holds a DataFrame

    Parameters
    ----------
    fp
        File to load

    Returns
    -------
    :
        Loaded data
    """
    res = load_feather(fp)
    if not isinstance(res, pd.DataFrame):
        msg = f"{fp} holds a {type(res)}, not a DataFrame"
        raise TypeError(msg)

    return res
