"""
Checks that the numbers in a manuscript match the data

A statement in the latex which depends on the data is marked
with a comment of the form

```latex
% value-check: {"tag": "co2-diff-from-igcc", "unit": "ppm", "lower": -1, "upper": 1}
```

The JSON after the colon says which check applies ("tag")
and the range of values for which the statement holds ("lower" and "upper",
in "unit").
A statement which is either true or false, rather than a number,
just has a tag, e.g. `% value-check: {"tag": "x-is-the-source-of-y"}`.
The same tag can appear more than once
(e.g. in the abstract and in the results),
in which case each is checked against its own range.
The comment can itself be commented out
(e.g. `% % value-check: {...}`, for a statement which is commented out for now),
in which case it is still checked.

The checks themselves ([ValueCheck][]) are written in python
and say which tag they calculate the value for.
[run_value_checks][] runs each check against the comments with its tag
and reports

- comments whose statement no longer holds
- comments which no check looked at
- checks whose tag doesn't appear in the latex (not an error,
  the statement may simply not be written yet, or have been removed)
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import openscm_units
import pint

VALUE_CHECK_COMMENT = re.compile(r"^\s*(?:%\s*)+value-check:(?P<raw>.*)$")
"""
Regular expression which matches a value check comment

Any number of `%` are allowed, so commented out comments are still checked.
"""

VALUE_CHECK_KEYS = ("tag", "unit", "lower", "upper")
"""Keys a value check comment's JSON can have"""


@dataclass(frozen=True)
class ValueCheckSpec:
    """
    A value check comment in the latex
    """

    file: Path
    """File the comment is in"""

    line: int
    """Line the comment is on (counting from 1)"""

    raw: str
    """The comment's JSON, as written"""

    tag: str
    """Tag of the check which applies"""

    unit: str | None = None
    """
    Unit of `lower` and `upper`

    `None` if the statement is either true or false, rather than a number.
    """

    lower: float = -float("inf")
    """Lowest value for which the statement holds"""

    upper: float = float("inf")
    """Highest value for which the statement holds"""

    @property
    def location(self) -> str:
        """Where the comment is, as `file:line`"""
        return f"{self.file}:{self.line}"

    @property
    def is_boolean(self) -> bool:
        """Whether the statement is either true or false, rather than a number"""
        return self.unit is None

    @property
    def bounds_str(self) -> str:
        """The bounds within which the statement holds, as a string"""
        if self.is_boolean:
            return "True (true/false check)"

        return f"[{self.lower:.4g}, {self.upper:.4g}] {self.unit}"

    @classmethod
    def from_raw(cls, raw: str, file: Path, line: int) -> ValueCheckSpec:
        """
        Initialise from a comment's JSON

        Parameters
        ----------
        raw
            The comment's JSON

        file
            File the comment is in

        line
            Line the comment is on

        Returns
        -------
        :
            Initialised instance

        Raises
        ------
        ValueError
            The JSON is not a valid value check
        """
        location = f"{file}:{line}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            msg = f"{location}: could not parse value check JSON {raw!r}"
            raise ValueError(msg) from exc

        if not isinstance(parsed, dict) or "tag" not in parsed:
            msg = f"{location}: value check must be a JSON object with a 'tag'"
            raise ValueError(msg)

        unknown = sorted(set(parsed) - set(VALUE_CHECK_KEYS))
        if unknown:
            msg = (
                f"{location}: unknown keys {unknown} in value check. "
                f"Allowed keys: {list(VALUE_CHECK_KEYS)}"
            )
            raise ValueError(msg)

        has_bounds = "lower" in parsed or "upper" in parsed
        if "unit" in parsed and not has_bounds:
            msg = f"{location}: value check has a unit, but no 'lower' or 'upper'"
            raise ValueError(msg)

        if has_bounds and "unit" not in parsed:
            msg = (
                f"{location}: value check has 'lower' or 'upper', but no unit. "
                'Use "unit": "dimensionless" for a value without units.'
            )
            raise ValueError(msg)

        if "unit" in parsed:
            try:
                openscm_units.unit_registry.Unit(parsed["unit"])
            except pint.UndefinedUnitError as exc:
                msg = f"{location}: unknown unit {parsed['unit']!r} in value check"
                raise ValueError(msg) from exc

        res = cls(
            file=file,
            line=line,
            raw=raw,
            tag=parsed["tag"],
            unit=parsed.get("unit"),
            lower=float(parsed.get("lower", -float("inf"))),
            upper=float(parsed.get("upper", float("inf"))),
        )
        if res.lower > res.upper:
            msg = f"{location}: value check's lower is greater than its upper"
            raise ValueError(msg)

        return res


def extract_value_check_specs(text: str, file: Path) -> tuple[ValueCheckSpec, ...]:
    """
    Extract the value check comments from latex

    Parameters
    ----------
    text
        Latex to extract from

    file
        File the latex is from

    Returns
    -------
    :
        The value check comments in `text`

    Raises
    ------
    ValueError
        A line mentions `value-check` but isn't a value check comment
        (most likely a typo, which would otherwise be silently ignored)
    """
    res = []
    for i, line in enumerate(text.splitlines()):
        match = VALUE_CHECK_COMMENT.match(line)
        if match is None:
            if "value-check" in line:
                msg = (
                    f"{file}:{i + 1}: line mentions value-check "
                    "but is not of the form `% value-check: {...}` "
                    "(or `% % value-check: {...}`)"
                )
                raise ValueError(msg)

            continue

        res.append(
            ValueCheckSpec.from_raw(match.group("raw").strip(), file=file, line=i + 1)
        )

    return tuple(res)


@dataclass
class ValueCheckCollector:
    """
    Collects value check comments as latex files are read
    """

    specs: list[ValueCheckSpec] = field(default_factory=list)
    """Value check comments found so far"""

    root: Path | None = None
    """
    Directory to show file paths relative to

    If `None`, paths are shown as given.
    """

    def read_text(self, file: Path) -> str:
        """
        Read a latex file, collecting its value check comments

        Parameters
        ----------
        file
            File to read

        Returns
        -------
        :
            The file's content
        """
        text = file.read_text()
        display_file = (
            file.relative_to(self.root)
            if self.root is not None and file.is_relative_to(self.root)
            else file
        )
        self.specs.extend(extract_value_check_specs(text, file=display_file))

        return text


CheckValue = bool | pint.Quantity
"""What a check calculates: a quantity, or whether a statement is true"""


@dataclass(frozen=True)
class ValueCheck:
    """
    A check of the value behind a statement in the latex
    """

    tag: str
    """Tag of the value check comments this checks"""

    calculate: Callable[[], CheckValue]
    """
    Calculate the value

    Return a quantity (which is converted to each comment's unit)
    or, for a statement which is either true or false, a bool.
    If the quantity is an array (e.g. one value per hemisphere),
    every element must be in the comment's range.
    Only called if the tag appears in the latex.
    """

    description: str
    """What is calculated, for the report"""


@dataclass(frozen=True)
class ValueCheckResult:
    """
    Result of checking one value check comment
    """

    spec: ValueCheckSpec
    """Comment which was checked"""

    check: ValueCheck
    """Check which was run"""

    value: CheckValue | None
    """Calculated value, in the comment's unit (`None` if it couldn't be)"""

    passed: bool
    """Whether the statement holds"""

    problem: str | None = None
    """Why the comment couldn't be checked (e.g. incompatible units)"""

    @property
    def value_str(self) -> str:
        """The calculated value, as a string"""
        if self.value is None:
            return "n/a"

        if isinstance(self.value, bool):
            return str(self.value)

        magnitude = np.atleast_1d(self.value.m)
        if magnitude.size == 1:
            return f"{magnitude[0]:.4g} {self.spec.unit}"

        return f"[{', '.join(f'{v:.4g}' for v in magnitude)}] {self.spec.unit}"


def evaluate_check(
    spec: ValueCheckSpec, check: ValueCheck, value: CheckValue
) -> ValueCheckResult:
    """
    Evaluate a calculated value against a value check comment

    Parameters
    ----------
    spec
        Comment to evaluate against

    check
        Check which calculated the value

    value
        Calculated value

    Returns
    -------
    :
        Result of the evaluation
    """
    if spec.is_boolean:
        if not isinstance(value, bool):
            return ValueCheckResult(
                spec=spec,
                check=check,
                value=None,
                passed=False,
                problem=(
                    f"the comment has no unit, so expects a true/false check, "
                    f"but the check calculated {value}"
                ),
            )

        # Shouldn't this check that value is True?
        return ValueCheckResult(spec=spec, check=check, value=value, passed=value)

    if isinstance(value, bool):
        return ValueCheckResult(
            spec=spec,
            check=check,
            value=None,
            passed=False,
            problem=(
                "the check is a true/false check, "
                "so the comment should have no unit, lower or upper"
            ),
        )

    try:
        converted = value.to(spec.unit)
    except pint.DimensionalityError:
        return ValueCheckResult(
            spec=spec,
            check=check,
            value=None,
            passed=False,
            problem=f"cannot convert the calculated {value:~} to {spec.unit}",
        )

    return ValueCheckResult(
        spec=spec,
        check=check,
        value=converted,
        passed=bool(np.all((spec.lower <= converted.m) & (converted.m <= spec.upper))),
    )


@dataclass(frozen=True)
class ValueCheckReport:
    """
    Report of running value checks
    """

    results: tuple[ValueCheckResult, ...]
    """Result of each comment which was checked"""

    unchecked: tuple[ValueCheckSpec, ...]
    """Comments which no check looked at"""

    tags_not_in_text: tuple[str, ...]
    """Tags of checks which have no comment in the latex"""

    @property
    def failed(self) -> tuple[ValueCheckResult, ...]:
        """Results whose statement doesn't hold"""
        return tuple(r for r in self.results if not r.passed)

    @property
    def ok(self) -> bool:
        """Whether every comment was checked and holds"""
        return not self.failed and not self.unchecked

    def to_str(self) -> str:
        """
        Get the report as a string

        Returns
        -------
        :
            The report
        """
        lines = [
            f"Value checks: {len(self.results) - len(self.failed)} passed, "
            f"{len(self.failed)} failed, {len(self.unchecked)} unchecked"
        ]
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(
                f"- {status} {r.spec.location} {r.spec.tag}: "
                f"actual value {r.value_str}, parsed bounds {r.spec.bounds_str}"
                + (f". {r.problem}" if r.problem else "")
            )

        if self.unchecked:
            lines.append("No check exists for these comments:")
            lines.extend(f"- {s.location} {s.tag}" for s in self.unchecked)

        if self.tags_not_in_text:
            lines.append("These checks have no comment in the latex (not an error):")
            lines.extend(f"- {t}" for t in self.tags_not_in_text)

        return "\n".join(lines)

    def raise_if_not_ok(self) -> None:
        """
        Raise if any comment failed or was not checked

        Raises
        ------
        ValueCheckError
            Any comment failed or was not checked
        """
        if self.ok:
            return

        msg = []
        if self.failed:
            msg.append(
                "These statements no longer hold "
                "(update the latex, including the value check comment, "
                "to match the data):"
            )
            for r in self.failed:
                msg.extend(
                    [
                        f"- {r.spec.location}",
                        f"    % value-check: {r.spec.raw}",
                        f"    Parsed bounds: {r.spec.bounds_str}",
                        f"    Actual value: {r.value_str}",
                        f"    {r.check.description} is {r.value_str}"
                        + (f". Problem: {r.problem}" if r.problem else ""),
                    ]
                )

        if self.unchecked:
            msg.append(
                "No check exists for these value check comments "
                "(write one, or fix the tag):"
            )
            msg.extend(f"- {s.location} {s.tag}" for s in self.unchecked)

        raise ValueCheckError("\n".join(msg))


class ValueCheckError(AssertionError):
    """
    Raised when value check comments fail or are not checked
    """


def run_value_checks(
    specs: Iterable[ValueCheckSpec], checks: Iterable[ValueCheck]
) -> ValueCheckReport:
    """
    Run value checks against the value check comments

    Parameters
    ----------
    specs
        Value check comments found in the latex

    checks
        Checks to run

        A check is only calculated if its tag appears in `specs`.

    Returns
    -------
    :
        Report of the results

    Raises
    ------
    ValueError
        More than one check has the same tag
    """
    specs = tuple(specs)
    checks = tuple(checks)

    tags = [c.tag for c in checks]
    duplicates = sorted({t for t in tags if tags.count(t) > 1})
    if duplicates:
        msg = f"More than one check has these tags: {duplicates}"
        raise ValueError(msg)

    results = []
    tags_not_in_text = []
    checked: set[int] = set()
    for check in checks:
        matching = [(i, s) for i, s in enumerate(specs) if s.tag == check.tag]
        if not matching:
            tags_not_in_text.append(check.tag)
            continue

        value = check.calculate()
        for i, spec in matching:
            results.append(evaluate_check(spec, check, value))
            checked.add(i)

    return ValueCheckReport(
        results=tuple(sorted(results, key=lambda r: (str(r.spec.file), r.spec.line))),
        unchecked=tuple(s for i, s in enumerate(specs) if i not in checked),
        tags_not_in_text=tuple(tags_not_in_text),
    )
