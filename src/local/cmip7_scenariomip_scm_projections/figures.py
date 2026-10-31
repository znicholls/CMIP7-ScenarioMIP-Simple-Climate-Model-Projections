"""
Figures of the projected warming
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle

from local.cmip7_scenariomip_scm_projections.scenarios import (
    SCENARIOS,
    Scenario,
)
from local.cmip7_scenariomip_scm_projections.warming import (
    METRICS,
    PEAK,
)
from local.feather_io import load_feather_df

INK = "#1f1f1f"
"""Colour of text, medians and box outlines"""

GRID = "#d9d9d9"
"""Colour of grid lines"""

METRIC_TITLES = {
    PEAK: "Peak warming (to 2500)",
    "2100": "Warming in 2100",
    "2500": "Warming in 2500",
}
"""Title of each metric's panel"""

BOX_LAYERS = (
    # (lower quantile, upper quantile, alpha)
    (0.05, 0.95, 0.25),
    (0.17, 0.83, 0.5),
    (0.33, 0.67, 0.9),
)
"""The nested boxes we draw, outermost first"""

BOX_WIDTH = 0.7
"""Width of the boxes (scenarios are 1 apart)"""


def style_axes(ax: Axes) -> None:
    """Apply our (recessive) axis style"""
    ax.grid(axis="y", color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    ax.tick_params(colors=INK, labelsize=8)


def select_scenario(df: pd.DataFrame, scenario: Scenario) -> pd.DataFrame:
    """Select a scenario's data"""
    return df.loc[
        (df.index.get_level_values("model") == scenario.model)
        & (df.index.get_level_values("scenario") == scenario.scenario)
    ]


def plot_timeseries(ax: Axes, timeseries_quantiles: pd.DataFrame) -> None:
    """
    Plot the median warming (line) and 5th to 95th percentile (plume)

    Parameters
    ----------
    ax
        Axes on which to plot

    timeseries_quantiles
        Quantiles of the assessed GSAT timeseries
    """
    for scenario in SCENARIOS:
        sdf = select_scenario(timeseries_quantiles, scenario)
        quantiles = sdf.index.get_level_values("quantile")
        years = sdf.columns.to_numpy()

        ax.fill_between(
            years,
            sdf.loc[quantiles == 0.05].to_numpy().squeeze(),  # noqa: PLR2004
            sdf.loc[quantiles == 0.95].to_numpy().squeeze(),  # noqa: PLR2004
            color=scenario.colour,
            alpha=0.15,
            linewidth=0,
        )
        ax.plot(
            years,
            sdf.loc[quantiles == 0.5].to_numpy().squeeze(),  # noqa: PLR2004
            color=scenario.colour,
            linewidth=1.5,
            label=scenario.label,
        )

    ax.set_xlim(1850, 2500)
    ax.axhline(0.0, color=INK, linewidth=0.5)
    ax.set_ylabel("Warming relative to 1850–1900 (K)", fontsize=8)  # noqa: RUF001
    ax.legend(
        loc="upper left",
        ncols=len(SCENARIOS),
        fontsize=8,
        frameon=False,
        handlelength=1.5,
        columnspacing=1.0,
    )
    style_axes(ax)


def draw_nested_box(
    ax: Axes,
    position: float,
    q: pd.Series,  # type: ignore[type-arg]
    colour: str,
    horizontal: bool = False,
) -> None:
    """
    Draw nested boxes for one distribution

    The outer box shows the 5th to 95th percentile,
    the inner boxes the 17th to 83rd and 33rd to 67th percentiles,
    the line the median.

    Parameters
    ----------
    ax
        Axes on which to draw

    position
        Centre of the box across the value axis (e.g. the scenario's index)

    q
        Quantiles of the distribution (index is the quantile)

    colour
        Colour of the boxes

    horizontal
        If `True`, values are on the x-axis and the boxes run left to right
    """

    def rectangle(start: float, end: float, **kwargs: object) -> Rectangle:
        across_start = position - BOX_WIDTH / 2
        if horizontal:
            return Rectangle((start, across_start), end - start, BOX_WIDTH, **kwargs)  # type: ignore[arg-type]

        return Rectangle((across_start, start), BOX_WIDTH, end - start, **kwargs)  # type: ignore[arg-type]

    for lower, upper, alpha in BOX_LAYERS:
        ax.add_patch(
            rectangle(
                q[lower], q[upper], facecolor=colour, alpha=alpha, edgecolor="none"
            )
        )
        # Outline separately, so it isn't faded by the fill's alpha
        ax.add_patch(
            rectangle(
                q[lower], q[upper], facecolor="none", edgecolor=INK, linewidth=0.4
            )
        )

    across = [position - BOX_WIDTH / 2, position + BOX_WIDTH / 2]
    median = [q[0.5], q[0.5]]
    ax.plot(
        *((median, across) if horizontal else (across, median)),
        color=INK,
        linewidth=1.5,
        solid_capstyle="butt",
    )


def plot_peak_year(ax: Axes, peak_year_quantiles: pd.DataFrame) -> None:
    """
    Plot nested boxes of the year of peak warming for each scenario

    The boxes run left to right, on the same time axis as the timeseries.

    Parameters
    ----------
    ax
        Axes on which to plot

    peak_year_quantiles
        Quantiles of the year of peak warming
    """
    for i, scenario in enumerate(SCENARIOS):
        q = select_scenario(peak_year_quantiles, scenario).squeeze()
        draw_nested_box(ax, position=i, q=q, colour=scenario.colour, horizontal=True)

    ax.set_ylim(len(SCENARIOS) - 0.4, -0.6)
    ax.set_yticks(range(len(SCENARIOS)), [s.label for s in SCENARIOS])
    ax.set_xlabel("Year", fontsize=8)
    ax.set_ylabel("Peak year", fontsize=8)
    style_axes(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.5)


SEPARATE_SCENARIO_LABELS = ("M", "H")
"""Scenarios shown in their own box panels (their warming is on a different scale)"""


def plot_boxes(
    ax: Axes,
    metrics_quantiles: pd.DataFrame,
    metric: str,
    scenarios: Sequence[Scenario],
) -> None:
    """
    Plot nested boxes of a warming metric for each scenario

    The outer box shows the 5th to 95th percentile,
    the inner boxes the 17th to 83rd and 33rd to 67th percentiles,
    the line the median.

    Parameters
    ----------
    ax
        Axes on which to plot

    metrics_quantiles
        Quantiles of the warming metrics

    metric
        Metric to plot

    scenarios
        Scenarios to plot, in order
    """
    metric_quantiles = metrics_quantiles.loc[
        metrics_quantiles.index.get_level_values("metric") == metric
    ]
    lowest = 0.0
    highest = 0.0
    for i, scenario in enumerate(scenarios):
        q = select_scenario(metric_quantiles, scenario).squeeze()
        draw_nested_box(ax, position=i, q=q, colour=scenario.colour)
        lowest = min(lowest, q[BOX_LAYERS[0][0]])
        highest = max(highest, q[BOX_LAYERS[0][1]])

    # Each panel has its own y-axis, always including zero
    # (warming can be negative, e.g. LN in 2500)
    padding = 0.05 * (highest - lowest)
    ax.set_ylim(lowest - padding, highest + padding)
    ax.axhline(0.0, color=INK, linewidth=0.5)

    ax.set_xlim(-0.6, len(scenarios) - 0.4)
    ax.set_xticks(range(len(scenarios)), [s.label for s in scenarios])
    style_axes(ax)


def generate_warming_figure(
    out_file: Path,
    metrics_quantiles_file: Path,
    timeseries_quantiles_file: Path,
    peak_year_quantiles_file: Path,
) -> Path:
    """
    Generate the figure of projected warming

    Panel a shows the median and 5th to 95th percentile warming over time,
    panel b nested boxes of the year of peak warming (on the same time axis),
    panels c to e nested boxes of peak warming, warming in 2100 and in 2500.
    In each of c to e, the scenarios in [SEPARATE_SCENARIO_LABELS][(m).]
    are shown in their own panel, next to the others.
    Every box panel has its own y-axis.

    Parameters
    ----------
    out_file
        File in which to save the figure

    metrics_quantiles_file
        File which holds the quantiles of the warming metrics

    timeseries_quantiles_file
        File which holds the quantiles of the assessed GSAT timeseries

    peak_year_quantiles_file
        File which holds the quantiles of the year of peak warming

    Returns
    -------
    :
        `out_file`
    """
    metrics_quantiles = load_feather_df(metrics_quantiles_file)
    timeseries_quantiles = load_feather_df(timeseries_quantiles_file)
    peak_year_quantiles = load_feather_df(peak_year_quantiles_file)

    main_scenarios = [s for s in SCENARIOS if s.label not in SEPARATE_SCENARIO_LABELS]
    separate_scenarios = [s for s in SCENARIOS if s.label in SEPARATE_SCENARIO_LABELS]

    fig = plt.figure(figsize=(7.0, 8.0), layout="constrained")
    box_labels = ["c", "d", "e"]
    box_row = [k for label in box_labels for k in (label, f"{label}-separate")]
    axd = fig.subplot_mosaic(
        [["a"] * len(box_row), ["b"] * len(box_row), box_row],
        height_ratios=[1.2, 0.6, 1],
        width_ratios=[len(main_scenarios), len(separate_scenarios) + 0.6]
        * len(box_labels),
    )
    plot_timeseries(axd["a"], timeseries_quantiles)

    # Peak timing on the same time axis as the timeseries
    axd["b"].sharex(axd["a"])
    plot_peak_year(axd["b"], peak_year_quantiles)
    axd["a"].tick_params(labelbottom=False)

    for label, metric in zip(box_labels, METRICS):
        main_ax = axd[label]
        plot_boxes(main_ax, metrics_quantiles, metric, main_scenarios)
        # The panel's letter goes in the title, so the two don't collide
        main_ax.set_title(
            rf"$\bf{{{label})}}$  {METRIC_TITLES[metric]}",
            fontsize=9,
            color=INK,
            loc="left",
        )
        plot_boxes(
            axd[f"{label}-separate"], metrics_quantiles, metric, separate_scenarios
        )

    axd["c"].set_ylabel("Warming (K)", fontsize=8)

    for label in ["a", "b"]:
        axd[label].text(
            0.0,
            1.02,
            f"{label})",
            transform=axd[label].transAxes,
            fontsize=10,
            fontweight="bold",
            va="bottom",
            ha="right",
            color=INK,
        )

    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file)
    plt.close(fig)

    return out_file
