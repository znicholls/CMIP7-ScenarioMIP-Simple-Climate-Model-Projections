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

from local.cmip7_scenariomip_scm_projections.igcc import (
    ASSESSED_RATE_BEST,
    ASSESSED_RATE_PERIOD,
    ASSESSED_RATE_RANGE,
    load_human_induced_warming,
    load_observed_gmst,
)
from local.cmip7_scenariomip_scm_projections.scenarios import (
    SCENARIOS,
    Scenario,
)
from local.cmip7_scenariomip_scm_projections.warming import (
    METRICS,
    PEAK,
    RATE_PERIODS,
    get_rate_period_label,
)
from local.feather_io import load_feather_df

INK = "#1f1f1f"
"""Colour of text and box outlines"""

MEDIAN_COLOUR = "white"
"""Colour of the median (best estimate) line in the boxes"""

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

IGCC_COLOUR = "#7f7f7f"
"""Colour of the IGCC assessment's box"""

NEAR_TERM_YEARS = (2000, 2100)
"""First and last year of the near-term timeseries panel (with IGCC's data)"""

LONG_TERM_YEARS = (2100, 2500)
"""First and last year of the long-term timeseries panel"""

RATE_GROUP_GAP = 1.0
"""Gap between the groups of boxes in the rate panel (scenarios are 1 apart)"""

RATE_IGCC_GAP = 0.3
"""Extra gap between IGCC's box and the scenarios' boxes for the same period"""


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


def plot_scenario_plumes(
    ax: Axes,
    timeseries_quantiles: pd.DataFrame,
    first_year: int,
    last_year: int,
) -> None:
    """
    Plot each scenario's median warming (line) and 5th to 95th percentile (plume)

    Parameters
    ----------
    ax
        Axes on which to plot

    timeseries_quantiles
        Quantiles of the assessed GSAT timeseries

    first_year
        First year to plot

    last_year
        Last year to plot
    """
    for scenario in SCENARIOS:
        sdf = select_scenario(timeseries_quantiles, scenario).loc[
            :, first_year:last_year
        ]
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

    ax.set_xlim(first_year, last_year)


def plot_long_term(ax: Axes, timeseries_quantiles: pd.DataFrame) -> None:
    """
    Plot the long-term median warming (line) and 5th to 95th percentile (plume)

    Over [LONG_TERM_YEARS][(m).], on its own y-axis.

    Parameters
    ----------
    ax
        Axes on which to plot

    timeseries_quantiles
        Quantiles of the assessed GSAT timeseries
    """
    plot_scenario_plumes(ax, timeseries_quantiles, *LONG_TERM_YEARS)
    ax.axhline(0.0, color=INK, linewidth=0.5)
    style_axes(ax)


def plot_near_term(
    ax: Axes,
    timeseries_quantiles: pd.DataFrame,
    observed_gmst: pd.Series,  # type: ignore[type-arg]
    human_induced_warming: pd.Series,  # type: ignore[type-arg]
) -> None:
    """
    Plot the near-term warming, with IGCC's observed and human-induced warming

    Parameters
    ----------
    ax
        Axes on which to plot

    timeseries_quantiles
        Quantiles of the assessed GSAT timeseries

    observed_gmst
        IGCC's observed GMST (indexed by year)

    human_induced_warming
        IGCC's human-induced warming (indexed by year)
    """
    first_year, last_year = NEAR_TERM_YEARS
    plot_scenario_plumes(ax, timeseries_quantiles, first_year, last_year)

    observed = observed_gmst.loc[first_year:last_year]
    ax.plot(
        observed.index,
        observed.to_numpy(),
        color=INK,
        linewidth=0.8,
        marker="o",
        markersize=2,
        label="Observed (IGCC)",
    )
    human_induced = human_induced_warming.loc[first_year:last_year]
    ax.plot(
        human_induced.index,
        human_induced.to_numpy(),
        color=INK,
        linewidth=1.5,
        linestyle=(0, (2, 1)),
        label="Human-induced (IGCC)",
    )

    # The plumes cover the full run, so only scale to what is shown
    in_window = timeseries_quantiles.loc[:, first_year:last_year]
    lowest = min(in_window.min().min(), observed.min())
    highest = max(in_window.max().max(), observed.max())
    padding = 0.05 * (highest - lowest)
    ax.set_ylim(lowest - padding, highest + padding)

    ax.set_ylabel("Warming relative to\n1850–1900 (K)", fontsize=8)  # noqa: RUF001
    style_axes(ax)

    # IGCC's data is only in this panel, so its legend goes here
    # (the scenarios' legend is for the whole figure)
    handles, labels = ax.get_legend_handles_labels()
    igcc = [(h, lab) for h, lab in zip(handles, labels) if "IGCC" in lab]
    ax.legend(
        [h for h, _ in igcc],
        [lab for _, lab in igcc],
        loc="upper left",
        fontsize=7,
        frameon=False,
        handlelength=2.2,
    )


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
        color=MEDIAN_COLOUR,
        linewidth=1.5,
        solid_capstyle="butt",
    )


def plot_peak_year(
    ax: Axes, peak_year_quantiles: pd.DataFrame, *, show_labels: bool = True
) -> None:
    """
    Plot nested boxes of the year of peak warming for each scenario

    The boxes run left to right, on the same time axis as the timeseries
    (share the x-axis with the timeseries panel before calling this).

    Parameters
    ----------
    ax
        Axes on which to plot

    peak_year_quantiles
        Quantiles of the year of peak warming

    show_labels
        Should the scenario labels and y-axis label be shown?
    """
    for i, scenario in enumerate(SCENARIOS):
        q = select_scenario(peak_year_quantiles, scenario).squeeze()
        draw_nested_box(ax, position=i, q=q, colour=scenario.colour, horizontal=True)

    ax.set_ylim(len(SCENARIOS) - 0.4, -0.6)
    ax.set_yticks(range(len(SCENARIOS)), [s.label for s in SCENARIOS])
    ax.set_xlabel("Year", fontsize=8)
    if show_labels:
        ax.set_ylabel("Peak year", fontsize=8)
    else:
        ax.tick_params(axis="y", labelleft=False)

    style_axes(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.5)


def draw_igcc_rate_box(ax: Axes, position: float) -> None:
    """
    Draw IGCC's assessed rate of warming

    IGCC only give a best estimate and range, so this is a single box
    (and the line is the best estimate).
    """
    low, high = ASSESSED_RATE_RANGE
    across_start = position - BOX_WIDTH / 2
    ax.add_patch(
        Rectangle(
            (across_start, low),
            BOX_WIDTH,
            high - low,
            facecolor=IGCC_COLOUR,
            alpha=BOX_LAYERS[0][2],
            edgecolor="none",
        )
    )
    ax.add_patch(
        Rectangle(
            (across_start, low),
            BOX_WIDTH,
            high - low,
            facecolor="none",
            edgecolor=INK,
            linewidth=0.4,
        )
    )
    ax.plot(
        [across_start, across_start + BOX_WIDTH],
        [ASSESSED_RATE_BEST, ASSESSED_RATE_BEST],
        color=MEDIAN_COLOUR,
        linewidth=1.5,
        solid_capstyle="butt",
    )
    ax.text(
        position,
        high,
        " IGCC",
        ha="center",
        va="bottom",
        # Vertical, so it fits above the (narrow) box
        rotation=90,
        fontsize=6.5,
        color=INK,
    )


def plot_rates(ax: Axes, rate_quantiles: pd.DataFrame) -> None:
    """
    Plot the projected rate of warming, with IGCC's assessment

    There is a group of nested boxes (one per scenario)
    for each of [RATE_PERIODS][(m).].
    IGCC's assessment (best estimate and likely range) is shown
    at the start of the group for the period it covers.

    Parameters
    ----------
    ax
        Axes on which to plot

    rate_quantiles
        Quantiles of the projected rate of warming
    """
    tick_positions = []
    tick_labels = []
    lowest = min(0.0, ASSESSED_RATE_RANGE[0])
    # Room for IGCC's label
    highest = 1.2 * ASSESSED_RATE_RANGE[1]
    position = 0.0
    for i_period, period in enumerate(RATE_PERIODS):
        if i_period > 0:
            # Separate the groups
            ax.axvline(position - (1.0 + RATE_GROUP_GAP) / 2, color=GRID, linewidth=0.8)

        group_start = position
        if period == ASSESSED_RATE_PERIOD:
            draw_igcc_rate_box(ax, position)
            position += 1.0 + RATE_IGCC_GAP

        period_quantiles = rate_quantiles.loc[
            rate_quantiles.index.get_level_values("period")
            == get_rate_period_label(*period)
        ]
        for scenario in SCENARIOS:
            q = select_scenario(period_quantiles, scenario).squeeze()
            draw_nested_box(ax, position=position, q=q, colour=scenario.colour)
            lowest = min(lowest, q[BOX_LAYERS[0][0]])
            highest = max(highest, q[BOX_LAYERS[0][1]])
            position += 1.0

        group_end = position - 1.0
        tick_positions.append((group_start + group_end) / 2)
        tick_labels.append(f"{period[0]}–{period[1]}")  # noqa: RUF001
        position = group_end + 1.0 + RATE_GROUP_GAP

    padding = 0.05 * (highest - lowest)
    ax.set_ylim(lowest - padding, highest + padding)
    ax.axhline(0.0, color=INK, linewidth=0.5)

    ax.set_xlim(-0.6, group_end + 0.6)
    ax.set_xticks(tick_positions, tick_labels)
    ax.tick_params(axis="x", labelsize=7, length=0)
    ax.set_ylabel("Rate of warming (K / decade)", fontsize=8)
    style_axes(ax)


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


def label_panel(ax: Axes, label: str) -> None:
    """Put the panel's letter above its top left corner"""
    ax.text(
        0.0,
        1.02,
        f"{label})",
        transform=ax.transAxes,
        fontsize=10,
        fontweight="bold",
        va="bottom",
        ha="right",
        color=INK,
    )


def generate_warming_figure(  # noqa: PLR0913
    out_file: Path,
    metrics_quantiles_file: Path,
    timeseries_quantiles_file: Path,
    peak_year_quantiles_file: Path,
    rate_quantiles_file: Path,
    igcc_dir: Path,
) -> Path:
    """
    Generate the figure of projected warming

    Panels a and b show the median and 5th to 95th percentile warming
    over [NEAR_TERM_YEARS][(m).] (with IGCC's observed and human-induced warming)
    and [LONG_TERM_YEARS][(m).], each on its own y-axis.
    Panels c and d show nested boxes of the year of peak warming
    on the same time axes as a and b.
    Panel e shows the rate of warming
    (nested boxes for each scenario for each period in `warming.RATE_PERIODS`,
    with IGCC's assessment for its latest period).
    Panels f to h show nested boxes of peak warming, warming in 2100 and in 2500.
    In each of f to h, the scenarios in [SEPARATE_SCENARIO_LABELS][(m).]
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

    rate_quantiles_file
        File which holds the quantiles of the rate of warming

    igcc_dir
        Directory which holds the IGCC data

    Returns
    -------
    :
        `out_file`
    """
    metrics_quantiles = load_feather_df(metrics_quantiles_file)
    timeseries_quantiles = load_feather_df(timeseries_quantiles_file)
    peak_year_quantiles = load_feather_df(peak_year_quantiles_file)
    rate_quantiles = load_feather_df(rate_quantiles_file)

    main_scenarios = [s for s in SCENARIOS if s.label not in SEPARATE_SCENARIO_LABELS]
    separate_scenarios = [s for s in SCENARIOS if s.label in SEPARATE_SCENARIO_LABELS]

    fig = plt.figure(figsize=(7.0, 9.7), layout="constrained")
    # Each row has its own layout (their columns don't line up)
    time_fig, rate_fig, box_fig = fig.subfigures(3, 1, height_ratios=[2.0, 1.1, 1.0])

    time_axd = time_fig.subplot_mosaic(
        [["a", "b"], ["c", "d"]], height_ratios=[1.4, 0.75]
    )
    plot_near_term(
        time_axd["a"],
        timeseries_quantiles,
        observed_gmst=load_observed_gmst(igcc_dir),
        human_induced_warming=load_human_induced_warming(igcc_dir),
    )
    plot_long_term(time_axd["b"], timeseries_quantiles)

    # Peak timing on the same time axes as the timeseries
    for timeseries_label, peak_label in (("a", "c"), ("b", "d")):
        time_axd[peak_label].sharex(time_axd[timeseries_label])
        time_axd[timeseries_label].tick_params(labelbottom=False)

    plot_peak_year(time_axd["c"], peak_year_quantiles)
    plot_peak_year(time_axd["d"], peak_year_quantiles, show_labels=False)

    # One legend of the scenarios for the whole figure
    # (the scenarios are only identified by colour in the box panels)
    handles, labels = time_axd["b"].get_legend_handles_labels()
    time_fig.legend(
        handles,
        labels,
        loc="outside upper center",
        ncols=len(handles),
        fontsize=7.5,
        title="Scenario",
        title_fontsize=8,
        frameon=False,
        handlelength=1.8,
        columnspacing=1.0,
    )

    rate_ax = rate_fig.subplots()
    plot_rates(rate_ax, rate_quantiles)

    box_labels = ["f", "g", "h"]
    box_row = [k for label in box_labels for k in (label, f"{label}-separate")]
    axd = box_fig.subplot_mosaic(
        [box_row],
        width_ratios=[len(main_scenarios), len(separate_scenarios) + 0.6]
        * len(box_labels),
    )
    axd.update(time_axd)
    axd["e"] = rate_ax

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

    axd[box_labels[0]].set_ylabel("Warming (K)", fontsize=8)

    for label in ["a", "b", "c", "d", "e"]:
        label_panel(axd[label], label)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file)
    plt.close(fig)

    return out_file
