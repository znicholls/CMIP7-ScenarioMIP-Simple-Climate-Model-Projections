r"""
Assembly and compilation of IOP-template based latex manuscripts

[assemble_main_tex][] puts the manuscript's pieces into IOP's template
(`iop-latex-template/template_clean.tex`) and checks the result,
[compile_latex][] turns it into a PDF.

Adapted from `gmd_latex.py` in
https://github.com/climate-resource/CMIP7-GHG-Concentration-Manuscripts.

Figures and generated files (e.g. tables) are wired in with tags:
write `@some-tag@` in the latex (e.g. `\\includegraphics{@warming-figure@}`)
and pass the tag and the file to use in its place.
"""

from __future__ import annotations

import copy
import re
import shutil
import subprocess
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO, Any

import yaml

from local.paths import REPO_ROOT
from local.value_checks import ValueCheckCollector

IOP_TEMPLATE_FILES = ("iopjournal.cls", "orcid.pdf")
"""Files from IOP's template which latex needs next to `main.tex`"""


def get_source_file_str(source_file: Path) -> str:
    """Get a string to insert in the compiled latex so we can see the original source"""
    shown = (
        source_file.relative_to(REPO_ROOT)
        if source_file.is_relative_to(REPO_ROOT)
        else source_file
    )
    return f"% Source file: {shown}"


def insert_after_tag(
    start: str, to_insert: str | list[str] | tuple[str, ...], tag: str
) -> str:
    """
    Insert text after a given tag
    """
    if isinstance(to_insert, str):
        to_insert = to_insert.splitlines()

    res_l = []
    found_tag = False
    for line in start.splitlines():
        res_l.append(line)
        if tag in line:
            res_l.extend(to_insert)
            found_tag = True

    if not found_tag:
        msg = f"Did not find {tag=} in the text"
        raise AssertionError(msg)

    return "\n".join(res_l)


def replace_placeholder(start: str, command: str, replacement: str) -> str:
    r"""
    Replace `\command{TEXT}` with `\command{replacement}`

    Raises
    ------
    AssertionError
        `\command{TEXT}` is not in `start`
    """
    to_replace = rf"\{command}{{TEXT}}"
    if to_replace not in start:
        msg = f"Did not find {to_replace!r} in the template"
        raise AssertionError(msg)

    return start.replace(to_replace, rf"\{command}{{{replacement}}}")


def get_author_line(metadata: dict[str, Any]) -> str:
    r"""
    Get IOP's `\author{...}` line

    Each author is followed by their affiliation numbers
    (and a `*` if they are the corresponding author)
    and their ORCID, if they have one.
    """
    affiliation_numbers = {
        key: i + 1 for i, key in enumerate(metadata["affiliations"].keys())
    }

    entries = []
    for author in metadata["authors"]:
        marks = [str(affiliation_numbers[key]) for key in author["affiliations"]]
        if author.get("correspondence_author", False):
            marks.append("*")

        entry = f"{author['given_name']} {author['surname']}$^{{{','.join(marks)}}}$"
        if author.get("orcid"):
            entry = rf"{entry}\orcid{{{author['orcid']}}}"

        entries.append(entry)

    if len(entries) == 1:
        authors = entries[0]
    else:
        authors = f"{', '.join(entries[:-1])} and {entries[-1]}"

    return rf"\author{{{authors}}}"


def insert_author_list_and_affiliations(
    start: str, metadata: dict[str, Any], metadata_file: Path
) -> str:
    """Insert the author list, affiliations and correspondence email"""
    res = insert_after_tag(
        start,
        [get_source_file_str(metadata_file), get_author_line(metadata)],
        "@author-start@",
    )

    affiliations_entries = [
        get_source_file_str(metadata_file),
        *(
            rf"\affil{{$^{i + 1}${address}}}"
            for i, address in enumerate(metadata["affiliations"].values())
        ),
        r"\affil{$^*$Author to whom any correspondence should be addressed.}",
    ]
    res = insert_after_tag(res, affiliations_entries, "@affiliation-start@")

    correspondence = [
        a["email"] for a in metadata["authors"] if a.get("correspondence_author", False)
    ]
    if len(correspondence) != 1:
        msg = "Exactly one author must be the correspondence author"
        raise AssertionError(msg)

    res = replace_placeholder(res, "email", correspondence[0])

    return res


def apply_replacements(in_text: str, replacements: Mapping[str, str]) -> str:
    """
    Apply replacements from our replacements file
    """
    out = copy.deepcopy(in_text)
    for old, new in replacements.items():
        out = out.replace(old, new)

    return out


def remove_stale_latex_artifacts(latex_main: Path) -> None:
    """Remove outputs that can otherwise be reused from an earlier build."""
    for suffix in [".aux", ".bbl", ".bcf", ".blg", ".log", ".out", ".pdf", ".run.xml"]:
        latex_main.with_suffix(suffix).unlink(missing_ok=True)


def aux_file_has_citations(aux_file: Path) -> bool:
    """Check whether BibTeX has citation entries to process"""
    if not aux_file.exists():
        return False

    return any(
        line.startswith(r"\citation")
        for line in aux_file.read_text(encoding="utf-8").splitlines()
    )


def run_pdflatex(latex_main: Path, output_sink: int | IO[Any] | None) -> None:
    """
    Run a single pdflatex pass over `latex_main`

    Parameters
    ----------
    latex_main
        Main latex file to compile

    output_sink
        Where to send pdflatex's output, see [compile_latex][]
    """
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", latex_main.name],
        cwd=latex_main.parent,
        check=True,
        stdout=output_sink,
    )


def compile_latex(
    latex_main: Path,
    output_sink: int | IO[Any] | None,
    n_passes_after_bibtex: int = 2,
) -> Path:
    """
    Compile `latex_main` to PDF

    Parameters
    ----------
    latex_main
        Main latex file to compile

    output_sink
        Where to send the output of pdflatex and bibtex.

        They write everything, errors and warnings included,
        to stdout (as well as their log files).
        Anything [subprocess.run][]'s `stdout` accepts can be used, e.g.
        `sys.stderr`, `subprocess.DEVNULL` (to drop it)
        or `None` (to leave it on stdout).

    n_passes_after_bibtex
        Number of pdflatex passes to do after running bibtex.

    Returns
    -------
    :
        Path to the compiled PDF
    """
    run_pdflatex(latex_main, output_sink=output_sink)

    if aux_file_has_citations(latex_main.with_suffix(".aux")):
        subprocess.run(
            ["bibtex", latex_main.stem],
            cwd=latex_main.parent,
            check=True,
            stdout=output_sink,
        )

    for _ in range(n_passes_after_bibtex):
        run_pdflatex(latex_main, output_sink=output_sink)

    log = latex_main.with_suffix(".log").read_text(encoding="utf-8", errors="replace")
    if "Rerun to get cross-references right" in log:
        print(
            "WARNING: latex still wants another pass "
            "to get the cross-references right. "
            "Consider increasing `n_passes_after_bibtex`."
        )

    built_pdf = latex_main.with_suffix(".pdf")
    if not built_pdf.exists():
        raise FileNotFoundError(built_pdf)

    return built_pdf


COMMENT_START = re.compile(r"(?<!\\)%")
"""
The start of a latex comment (a `%`, unless it is escaped)
"""


def split_comment(line: str) -> tuple[str, str]:
    """
    Split a line of latex into the part before its comment and its comment

    Parameters
    ----------
    line
        Line to split

    Returns
    -------
    :
        The part of `line` before its comment
        and its comment (empty if it has none),
        so that joining them gives back `line`
    """
    match = COMMENT_START.search(line)
    if match is None:
        return line, ""

    return line[: match.start()], line[match.start() :]


def tag_in_text(tag: str, text: str) -> bool:
    """
    Check whether a tag appears in the text, outside of comments
    """
    return any(tag in split_comment(line)[0] for line in text.splitlines())


def replace_tag(text: str, tag: str, replacement: str) -> str:
    """
    Replace a tag in the text, except where it appears in comments

    Comments can then mention tags
    (e.g. to explain where something comes from)
    without the tag being replaced there.
    """
    res_l = []
    for line in text.splitlines():
        before_comment, comment = split_comment(line)
        res_l.append(f"{before_comment.replace(tag, replacement)}{comment}")

    return "\n".join(res_l)


UNREPLACED_FIGURE_TAG = re.compile(r"\\includegraphics(\[[^\]]*\])?\{(@[^}@]*@)\}")
"""
A figure which is still a tag, i.e. one we were never given a file for
"""


def check_no_unreplaced_figure_tags(text: str) -> None:
    """
    Check that every figure included in the text has been given a file

    Raises
    ------
    AssertionError
        A figure included in `text` (outside a comment) is still a tag
    """
    unreplaced = [
        match.group(2)
        for line in text.splitlines()
        for match in UNREPLACED_FIGURE_TAG.finditer(split_comment(line)[0])
    ]
    if unreplaced:
        msg = (
            "No figure file was given for these tags: "
            f"{', '.join(unreplaced)}. "
            "Add them to `FIGURE_FILES` in the manuscript's config."
        )
        raise AssertionError(msg)


UNREPLACED_TAG = re.compile(r"@[a-z0-9][a-z0-9-]*@")
"""
Any tag, i.e. something we should have replaced
"""


def check_no_unreplaced_tags(text: str) -> None:
    """
    Check that every tag in the text has been replaced

    Without this, a tag we were never given anything for
    ends up in the PDF as text.

    Raises
    ------
    AssertionError
        `text` (outside comments) still contains tags
    """
    unreplaced = sorted(
        {
            match.group(0)
            for line in text.splitlines()
            for match in UNREPLACED_TAG.finditer(split_comment(line)[0])
        }
    )
    if unreplaced:
        msg = (
            "Nothing was given to replace these tags: "
            f"{', '.join(unreplaced)}. "
            "Add them to `FIGURE_FILES` or `FILES_TO_INLINE` "
            "in the manuscript's config."
        )
        raise AssertionError(msg)


def inline_files(
    in_text: str, files: Sequence[tuple[str, Path]], collector: ValueCheckCollector
) -> str:
    """
    Inline files in place of their tags

    The files' content is put straight into the text,
    rather than being left for latex to pull in with an input command,
    so the output stays a single file
    and our replacements are applied to the files' content too.

    Raises
    ------
    AssertionError
        A tag is not in the text (outside of comments)
    """
    res = in_text
    for tag, full_path in files:
        if not tag_in_text(tag, res):
            msg = f"Did not find {tag=} in the text (outside of comments)"
            raise AssertionError(msg)

        res = replace_tag(
            res,
            tag,
            f"{get_source_file_str(full_path)}\n{collector.read_text(full_path)}",
        )

    return res


def get_included_text(source_file: Path, collector: ValueCheckCollector) -> str:
    """Get a file's text, preceded by a comment which says where it came from"""
    return f"{get_source_file_str(source_file)}\n{collector.read_text(source_file)}"


def assemble_main_tex(  # noqa: PLR0913
    *,
    abstract: Path,
    introduction: Path,
    sections: Sequence[Path],
    conclusion: Path,
    acknowledgements: Path,
    funding: Path,
    author_contributions: Path,
    data_availability: Path,
    replacements: Path,
    metadata: Path,
    references_bib_file: Path,
    iop_template_dir: Path,
    clean_iop_template_filename: str,
    build_dir: Path,
    appendices: Sequence[Path] = (),
    figure_files: Sequence[tuple[str, Path]] = (),
    files_to_inline: Sequence[tuple[str, Path]] = (),
) -> tuple[Path, ValueCheckCollector]:
    r"""
    Assemble the manuscript's `main.tex` in the build directory

    The pieces are put into IOP's template,
    the figures and the files to inline go in place of their tags,
    the result is checked (no tags left over)
    and then our replacements are applied.
    Everything latex needs to compile `main.tex`
    (the template's class file, the bibliography, the figures)
    is copied next to it.

    Parameters
    ----------
    abstract
        Abstract (no headers, they come from the template)

    introduction
        Introduction (no headers, they come from the template)

    sections
        Body sections, in order (with their own headers)

    conclusion
        Conclusion (no headers, they come from the template)

    acknowledgements
        Acknowledgements (goes in `\ack`)

    funding
        Funding statement (goes in `\funding`)

    author_contributions
        Author contributions (goes in `\roles`), generated from the metadata

    data_availability
        Data availability statement (goes in `\data`)

    replacements
        YAML file of replacements to apply to the assembled latex

    metadata
        The manuscript's metadata file (title, authors, affiliations etc.)

    references_bib_file
        Bibtex references file

    iop_template_dir
        Directory in which IOP's latex template was extracted

    clean_iop_template_filename
        Name of the clean template file (in `iop_template_dir`)

    build_dir
        Directory in which to build (`main.tex` goes in its `latex` sub-directory)

    appendices
        Appendices, in order (each `\section` is a new appendix: A, B, ...)

        The `\appendix` command is added here, so the files must not contain it.

    figure_files
        Tag to replace and the figure to replace it with, for each figure

        Figures whose tag is not in the text are skipped.

    files_to_inline
        Tag to replace and the file to inline in its place, for each file

        Every tag must be in the text.

    Returns
    -------
    :
        Path to `main.tex` and the collector of the value check comments
        in everything which went into it

    Raises
    ------
    AssertionError
        Two figures would land at the same path in the build directory
    """
    collector = ValueCheckCollector(root=REPO_ROOT)

    with open(metadata, "rb") as fh:
        metadata_values = tomllib.load(fh)

    res = (iop_template_dir / clean_iop_template_filename).read_text()

    title_info = metadata_values["title_info"]
    res = replace_placeholder(res, "articletype", title_info["article_type"])
    res = replace_placeholder(res, "title", title_info["title"])
    res = replace_placeholder(res, "keywords", ", ".join(title_info["keywords"]))
    res = replace_placeholder(res, "bibliography", references_bib_file.stem)

    res = insert_author_list_and_affiliations(
        res, metadata_values, metadata_file=metadata
    )

    res = insert_after_tag(
        res, get_included_text(abstract, collector), tag="@abstract-start@"
    )
    res = insert_after_tag(
        res, get_included_text(introduction, collector), tag="@introduction-start@"
    )

    body_text = "\n\n".join(get_included_text(sf, collector) for sf in sections)
    res = insert_after_tag(res, body_text, tag="@body-start@")

    res = insert_after_tag(
        res, get_included_text(conclusion, collector), tag="@conclusions-start@"
    )

    for command, source_file in (
        ("ack", acknowledgements),
        ("funding", funding),
        ("roles", author_contributions),
        ("data", data_availability),
    ):
        res = replace_placeholder(
            res, command, f"\n{get_included_text(source_file, collector)}\n"
        )

    if appendices:
        appendix_text = "\n\n".join(
            [r"\appendix", *(get_included_text(af, collector) for af in appendices)]
        )
        res = insert_after_tag(res, appendix_text, tag="@appendix-start@")

    # Before any other replacements,
    # so the inlined files get the same replacements as the rest of the text
    # (including the figure replacements, as they can include figures).
    res = inline_files(res, files_to_inline, collector=collector)

    latex_dir = build_dir / "latex"
    latex_dir.mkdir(exist_ok=True, parents=True)

    seen = set()
    for tag, full_path in figure_files:
        # Otherwise every figure we are given ends up in the build,
        # whether the text uses it or not.
        if not tag_in_text(tag, res):
            continue

        dest = latex_dir / full_path.name
        if dest in seen:
            msg = f"Multiple figure files will land at {dest!r}"
            raise AssertionError(msg)

        shutil.copy2(full_path, dest)
        seen.add(dest)
        res = replace_tag(res, tag, str(dest.relative_to(latex_dir)))

    # The figure check first, as its message is more specific
    check_no_unreplaced_figure_tags(res)
    check_no_unreplaced_tags(res)

    replacements_map = yaml.safe_load(replacements.read_text()) or {}
    res = apply_replacements(res, replacements_map)

    latex_main = latex_dir / "main.tex"
    latex_main.write_text(res)

    remove_stale_latex_artifacts(latex_main)

    for fn in IOP_TEMPLATE_FILES:
        shutil.copy2(iop_template_dir / fn, latex_dir / fn)

    shutil.copy2(references_bib_file, latex_dir / references_bib_file.name)

    return latex_main, collector
