r"""
Generation of the author contributions statement

IOP asks for the contributions using the
NISO Contributor Roles Taxonomy (CRediT, https://credit.niso.org).
Each author in the manuscript's metadata file lists their contributions as tags
(the keys of [CREDIT_ROLES][]).
We turn these into one line per author,
"<author name>: <role>, <role>, ...",
which the build puts in the template's `\\roles` section.

Adapted from `author_contributions.py` in
https://github.com/climate-resource/CMIP7-GHG-Concentration-Manuscripts
(which writes one sentence per contribution, as Copernicus asks for).
"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from loguru import logger

CREDIT_ROLES = {
    "conceptualization": "Conceptualization",
    "data-curation": "Data curation",
    "formal-analysis": "Formal analysis",
    "funding-acquisition": "Funding acquisition",
    "investigation": "Investigation",
    "methodology": "Methodology",
    "project-administration": "Project administration",
    "resources": "Resources",
    "software": "Software",
    "supervision": "Supervision",
    "validation": "Validation",
    "visualization": "Visualization",
    "writing-original-draft": "Writing -- original draft",
    "writing-review-editing": "Writing -- review \\& editing",
}
"""The CRediT roles, by the tag authors use for them in the metadata file

The roles are written in this order.
"""


def get_author_contributions(authors: Sequence[dict[str, Any]]) -> str:
    """
    Get the author contributions statement

    Parameters
    ----------
    authors
        The authors, as the metadata file gives them

        Each needs `contributions` (a list of the tags in [CREDIT_ROLES][]).

    Returns
    -------
    :
        The statement, one line (paragraph) per author

    Raises
    ------
    ValueError
        An author has no contributions, lists one more than once
        or lists a contribution which is not in [CREDIT_ROLES][]
    """
    lines = []
    for author in authors:
        name = f"{author['given_name']} {author['surname']}"
        contributions = author.get("contributions")
        if not contributions:
            msg = f"{name} has no `contributions` in the metadata file"
            raise ValueError(msg)

        unknown = [c for c in contributions if c not in CREDIT_ROLES]
        if unknown:
            msg = (
                f"{name} has unknown contributions: {unknown}. "
                f"Expected any of: {', '.join(CREDIT_ROLES)}"
            )
            raise ValueError(msg)

        if len(set(contributions)) != len(contributions):
            msg = f"{name} lists a contribution more than once: {contributions}"
            raise ValueError(msg)

        roles = [role for tag, role in CREDIT_ROLES.items() if tag in contributions]
        lines.append(f"{name}: {', '.join(roles)}.")

    # A blank line between authors, so each is its own paragraph
    return "\n\n".join(lines)


def generate_author_contributions(outfile: Path, metadata_file: Path) -> Path:
    """
    Generate the author contributions statement

    Parameters
    ----------
    outfile
        File in which to write the statement

    metadata_file
        The manuscript's metadata file, which holds the authors and their contributions

    Returns
    -------
    :
        `outfile`
    """
    with open(metadata_file, "rb") as fh:
        metadata = tomllib.load(fh)

    outfile.parent.mkdir(exist_ok=True, parents=True)
    logger.info(f"Writing {outfile}")
    outfile.write_text(get_author_contributions(metadata["authors"]) + "\n")

    return outfile
