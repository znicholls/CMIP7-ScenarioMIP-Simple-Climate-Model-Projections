"""
The scenarios we run, and how we show them

The single source of truth for each scenario's label and colour,
so that every figure and table shows a scenario the same way.
"""

from __future__ import annotations

from attrs import define
from gcages.workflows.cmip7_scenariomip import (
    CMIP7_SCENARIOMIP_MARKERS,
    CMIP7ScenarioMIPMarker,
)


@define(frozen=True)
class Scenario:
    """
    A scenario we run
    """

    marker: CMIP7ScenarioMIPMarker
    """The CMIP7 ScenarioMIP marker (model, scenario as submitted etc.)"""

    label: str
    """Name of the scenario as shown to a reader (e.g. "VL")"""

    colour: str
    """Colour to draw the scenario in (the official CMIP7 ScenarioMIP palette)"""

    @property
    def model(self) -> str:
        """Model which produced the scenario"""
        return self.marker.model

    @property
    def scenario(self) -> str:
        """Scenario name, as submitted (this is the name used in our outputs)"""
        return self.marker.scenario

    @property
    def slug(self) -> str:
        """Identifier which is safe to use in file names and task IDs"""
        return self.label.lower()


LABELS_AND_COLOURS = {
    # Published scenario name: (label, colour)
    "Very Low - SSP1 (Marker)": ("VL", "#16188F"),
    "Low-to-Negative - SSP2 (Marker)": ("LN", "#22e5db"),
    "Low - SSP2 (Marker)": ("L", "#20A359"),
    "Medium-to-Low - SSP2 (Marker)": ("ML", "#dec820"),
    "Medium - SSP2 (Marker)": ("M", "#fc7b03"),
    "High-to-Low - SSP5 (Marker)": ("HL", "#E744F6"),
    "High - SSP3 (Marker)": ("H", "#a41212"),
}
"""Label and colour of each scenario, lowest to highest"""

_MARKERS_BY_PUBLISHED_NAME = {
    m.published_scenario: m for m in CMIP7_SCENARIOMIP_MARKERS
}
if set(_MARKERS_BY_PUBLISHED_NAME) != set(LABELS_AND_COLOURS):
    msg = (
        "The markers in gcages don't match the scenarios we expect. "
        f"{sorted(_MARKERS_BY_PUBLISHED_NAME)=} {sorted(LABELS_AND_COLOURS)=}"
    )
    raise AssertionError(msg)

SCENARIOS: tuple[Scenario, ...] = tuple(
    Scenario(marker=_MARKERS_BY_PUBLISHED_NAME[published], label=label, colour=colour)
    for published, (label, colour) in LABELS_AND_COLOURS.items()
)
"""Scenarios we run, lowest to highest"""


def get_scenario(model: str, scenario: str) -> Scenario:
    """
    Get a scenario from its model and (submitted) scenario name

    Parameters
    ----------
    model
        Model

    scenario
        Scenario name, as submitted

    Returns
    -------
    :
        Scenario
    """
    for s in SCENARIOS:
        if s.model == model and s.scenario == scenario:
            return s

    msg = f"No scenario for {model=}, {scenario=}"
    raise KeyError(msg)
