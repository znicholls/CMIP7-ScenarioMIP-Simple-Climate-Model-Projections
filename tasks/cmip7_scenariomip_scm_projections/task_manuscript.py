"""
Tasks which assemble the manuscript and compile it to PDF
"""

import shutil
import sys
from pathlib import Path
from typing import Annotated

from pytask import Product

import local.cmip7_scenariomip_scm_projections.value_checks
import local.iop_latex
from local.cmip7_scenariomip_scm_projections.config import (
    ABSTRACT,
    ACKNOWLEDGEMENTS,
    APPENDICES,
    AUTHOR_CONTRIBUTIONS,
    BUILD_DIR,
    CLEAN_IOP_TEMPLATE_FILENAME,
    CONCLUSION,
    DATA_AVAILABILITY,
    FIGURE_FILES,
    FILES_TO_INLINE,
    FUNDING,
    INTRODUCTION,
    IOP_TEMPLATE_DIR,
    LATEX_DIR,
    LATEX_MAIN,
    METADATA,
    OUTPUT_PDF,
    REFERENCES_BIB,
    REPLACEMENTS,
    REPRODUCTION_CHECK_FILES,
    SECTIONS,
    WARMING_METRICS_QUANTILES,
)
from local.cmip7_scenariomip_scm_projections.value_checks import get_value_checks
from local.iop_latex import IOP_TEMPLATE_FILES, assemble_main_tex, compile_latex
from local.value_checks import run_value_checks

MANUSCRIPT_FILES = {
    "abstract": ABSTRACT,
    "introduction": INTRODUCTION,
    "sections": list(SECTIONS),
    "appendices": list(APPENDICES),
    "conclusion": CONCLUSION,
    "acknowledgements": ACKNOWLEDGEMENTS,
    "funding": FUNDING,
    "data_availability": DATA_AVAILABILITY,
}
"""The manuscript's text, by the part of the template it goes into"""

IOP_TEMPLATE = [
    IOP_TEMPLATE_DIR / fn for fn in (CLEAN_IOP_TEMPLATE_FILENAME, *IOP_TEMPLATE_FILES)
]
"""The template files the assembly reads or copies"""

LATEX_SUPPORT_FILES = [
    *(LATEX_DIR / fn for fn in IOP_TEMPLATE_FILES),
    LATEX_DIR / REFERENCES_BIB.name,
    *(LATEX_DIR / figure.name for figure in FIGURE_FILES.values()),
]
"""Files the assembly puts next to `main.tex`, which latex needs to compile it"""


def task_assemble_latex(  # noqa: PLR0913
    manuscript_files: dict[str, Path | list[Path]] = MANUSCRIPT_FILES,
    author_contributions: Path = AUTHOR_CONTRIBUTIONS,
    metadata: Path = METADATA,
    replacements: Path = REPLACEMENTS,
    references_bib: Path = REFERENCES_BIB,
    iop_template: list[Path] = IOP_TEMPLATE,
    figure_files: dict[str, Path] = FIGURE_FILES,
    files_to_inline: dict[str, Path] = FILES_TO_INLINE,
    value_check_data: list[Path] = [
        WARMING_METRICS_QUANTILES,
        *REPRODUCTION_CHECK_FILES,
    ],
    value_checks_source: Path = Path(
        local.cmip7_scenariomip_scm_projections.value_checks.__file__
    ),
    iop_latex_source: Path = Path(local.iop_latex.__file__),
    main_tex: Annotated[Path, Product] = LATEX_MAIN,
    latex_support_files: Annotated[list[Path], Product] = LATEX_SUPPORT_FILES,
) -> None:
    """
    Assemble `main.tex` and check the values behind its statements

    Fails if any value check comment's statement no longer holds
    or has no check.
    """
    latex_main, collector = assemble_main_tex(
        **manuscript_files,  # type: ignore[arg-type]
        author_contributions=author_contributions,
        replacements=replacements,
        metadata=metadata,
        references_bib_file=references_bib,
        iop_template_dir=IOP_TEMPLATE_DIR,
        clean_iop_template_filename=CLEAN_IOP_TEMPLATE_FILENAME,
        build_dir=BUILD_DIR,
        figure_files=list(figure_files.items()),
        files_to_inline=list(files_to_inline.items()),
    )
    if latex_main != main_tex:
        msg = f"Assembly wrote {latex_main}, expected {main_tex}"
        raise AssertionError(msg)

    value_check_report = run_value_checks(
        collector.specs,
        get_value_checks(
            metrics_quantiles_file=WARMING_METRICS_QUANTILES,
            reproduction_check_files=REPRODUCTION_CHECK_FILES,
        ),
    )
    print(value_check_report.to_str())
    value_check_report.raise_if_not_ok()


def task_compile_pdf(
    main_tex: Path = LATEX_MAIN,
    latex_support_files: list[Path] = LATEX_SUPPORT_FILES,
    output_pdf: Annotated[Path, Product] = OUTPUT_PDF,
) -> None:
    """Compile `main.tex` to PDF"""
    # stderr, so the latex output can be dropped with `2>/dev/null`
    built_pdf = compile_latex(main_tex, output_sink=sys.stderr)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built_pdf, output_pdf)
