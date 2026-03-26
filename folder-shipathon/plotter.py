
"""
MANTHA — Tool 4: plotter.py
Generates charts and graphs from a transformed DataFrame.
Uses Matplotlib + Seaborn for static publication-quality plots.
Plots are saved as PNG files and paths are returned for use by report_creator.py.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend — safe for pipelines
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [plotter]  %(levelname)s — %(message)s",
)
log = logging.getLogger("plotter")


# ── Theme ──────────────────────────────────────────────────────────────────────
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)
MANTHA_PALETTE = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B2", "#937860"]
DEFAULT_FIG_SIZE = (10, 6)
DEFAULT_DPI      = 150
OUTPUT_DIR       = "mantha_plots"   # default output folder


def _ensure_dir(directory: str) -> str:
    Path(directory).mkdir(parents=True, exist_ok=True)
    return directory


def _save(fig: plt.Figure, filepath: str, dpi: int = DEFAULT_DPI) -> str:
    fig.savefig(filepath, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    log.info("Saved plot: %s", filepath)
    return filepath


# ── Individual plot functions ──────────────────────────────────────────────────
def bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "Bar Chart",
    hue: Optional[str] = None,
    output_dir: str = OUTPUT_DIR,
    filename: Optional[str] = None,
    top_n: Optional[int] = None,
) -> Optional[str]:
    """Grouped or simple bar chart."""
    try:
        _ensure_dir(output_dir)
        data = df[[x, y] + ([hue] if hue else [])].dropna()
        if top_n:
            top_vals = data.groupby(x)[y].sum().nlargest(top_n).index
            data = data[data[x].isin(top_vals)]

        fig, ax = plt.subplots(figsize=DEFAULT_FIG_SIZE)
        sns.barplot(data=data, x=x, y=y, hue=hue, ax=ax, palette=MANTHA_PALETTE)
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel(x.replace("_", " ").title())
        ax.set_ylabel(y.replace("_", " ").title())
        plt.xticks(rotation=30, ha="right")
        fig.tight_layout()

        fname = filename or f"bar_{x}_vs_{y}.png"
        return _save(fig, os.path.join(output_dir, fname))
    except Exception as exc:
        log.error("bar_chart failed: %s", exc)
        return None


def line_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "Line Chart",
    hue: Optional[str] = None,
    output_dir: str = OUTPUT_DIR,
    filename: Optional[str] = None,
) -> Optional[str]:
    """Time-series or trend line chart."""
    try:
        _ensure_dir(output_dir)
        data = df[[x, y] + ([hue] if hue else [])].dropna().sort_values(x)

        fig, ax = plt.subplots(figsize=DEFAULT_FIG_SIZE)
        sns.lineplot(data=data, x=x, y=y, hue=hue, ax=ax,
                     palette=MANTHA_PALETTE, marker="o", linewidth=2)
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel(x.replace("_", " ").title())
        ax.set_ylabel(y.replace("_", " ").title())
        plt.xticks(rotation=30, ha="right")
        fig.tight_layout()

        fname = filename or f"line_{x}_vs_{y}.png"
        return _save(fig, os.path.join(output_dir, fname))
    except Exception as exc:
        log.error("line_chart failed: %s", exc)
        return None


def pie_chart(
    df: pd.DataFrame,
    labels_col: str,
    values_col: str,
    title: str = "Pie Chart",
    top_n: int = 8,
    output_dir: str = OUTPUT_DIR,
    filename: Optional[str] = None,
) -> Optional[str]:
    """Pie / donut chart for proportional data."""
    try:
        _ensure_dir(output_dir)
        data = df.groupby(labels_col)[values_col].sum().nlargest(top_n)

        fig, ax = plt.subplots(figsize=(8, 8))
        wedges, texts, autotexts = ax.pie(
            data.values,
            labels=data.index,
            autopct="%1.1f%%",
            colors=MANTHA_PALETTE[:len(data)],
            startangle=140,
            wedgeprops=dict(width=0.6),   # donut style
        )
        for t in autotexts:
            t.set_fontsize(9)
        ax.set_title(title, fontweight="bold")
        fig.tight_layout()

        fname = filename or f"pie_{labels_col}.png"
        return _save(fig, os.path.join(output_dir, fname))
    except Exception as exc:
        log.error("pie_chart failed: %s", exc)
        return None


def histogram(
    df: pd.DataFrame,
    column: str,
    title: str = "Distribution",
    bins: int = 20,
    output_dir: str = OUTPUT_DIR,
    filename: Optional[str] = None,
) -> Optional[str]:
    """Histogram with KDE overlay."""
    try:
        _ensure_dir(output_dir)
        data = df[column].dropna()

        fig, ax = plt.subplots(figsize=DEFAULT_FIG_SIZE)
        sns.histplot(data, bins=bins, kde=True, ax=ax, color=MANTHA_PALETTE[0])
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel(column.replace("_", " ").title())
        ax.set_ylabel("Frequency")
        fig.tight_layout()

        fname = filename or f"hist_{column}.png"
        return _save(fig, os.path.join(output_dir, fname))
    except Exception as exc:
        log.error("histogram failed: %s", exc)
        return None


def heatmap(
    df: pd.DataFrame,
    title: str = "Correlation Heatmap",
    output_dir: str = OUTPUT_DIR,
    filename: str = "heatmap_correlation.png",
) -> Optional[str]:
    """Correlation heatmap for all numeric columns."""
    try:
        _ensure_dir(output_dir)
        numeric_df = df.select_dtypes(include="number")
        if numeric_df.shape[1] < 2:
            log.warning("Not enough numeric columns for a heatmap.")
            return None

        corr = numeric_df.corr()
        fig, ax = plt.subplots(figsize=(max(8, len(corr)), max(6, len(corr) - 1)))
        sns.heatmap(
            corr, annot=True, fmt=".2f", cmap="coolwarm",
            linewidths=0.5, ax=ax, square=True,
        )
        ax.set_title(title, fontweight="bold")
        fig.tight_layout()
        return _save(fig, os.path.join(output_dir, filename))
    except Exception as exc:
        log.error("heatmap failed: %s", exc)
        return None


def scatter_plot(
    df: pd.DataFrame,
    x: str,
    y: str,
    hue: Optional[str] = None,
    title: str = "Scatter Plot",
    output_dir: str = OUTPUT_DIR,
    filename: Optional[str] = None,
) -> Optional[str]:
    """Scatter plot with optional colour grouping."""
    try:
        _ensure_dir(output_dir)
        data = df[[x, y] + ([hue] if hue else [])].dropna()

        fig, ax = plt.subplots(figsize=DEFAULT_FIG_SIZE)
        sns.scatterplot(data=data, x=x, y=y, hue=hue, ax=ax,
                        palette=MANTHA_PALETTE, alpha=0.75, s=60)
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel(x.replace("_", " ").title())
        ax.set_ylabel(y.replace("_", " ").title())
        fig.tight_layout()

        fname = filename or f"scatter_{x}_vs_{y}.png"
        return _save(fig, os.path.join(output_dir, fname))
    except Exception as exc:
        log.error("scatter_plot failed: %s", exc)
        return None


# ── Auto-plot: generate sensible charts from a DataFrame automatically ────────
def auto_plot(
    df: pd.DataFrame,
    breakdown: Optional[dict] = None,   # from data_categorizer.auto_breakdown()
    output_dir: str = OUTPUT_DIR,
) -> list[str]:
    """
    Automatically generate the most relevant plots based on DataFrame content
    or a breakdown dict from data_categorizer.auto_breakdown().

    Returns a list of saved file paths.
    """
    paths: list[str] = []
    _ensure_dir(output_dir)

    dims     = breakdown.get("dimensions", []) if breakdown else []
    measures = breakdown.get("measures",   []) if breakdown else []
    dates    = breakdown.get("dates",      []) if breakdown else []

    # Always fall back to dtype inference for any missing category
    # (handles empty breakdown {} or partial LLM responses)
    if not dims:
        dims = df.select_dtypes(include=["object", "category"]).columns.tolist()
    if not measures:
        measures = df.select_dtypes(include="number").columns.tolist()
    if not dates:
        dates = df.select_dtypes(include=["datetime64"]).columns.tolist()

    # Filter out columns that don't actually exist in the df (LLM hallucinations)
    dims     = [c for c in dims     if c in df.columns]
    measures = [c for c in measures if c in df.columns]
    dates    = [c for c in dates    if c in df.columns]

    # 1. Heatmap (always useful if ≥2 numeric cols)
    p = heatmap(df, output_dir=output_dir)
    if p:
        paths.append(p)

    # 2. Bar charts: first dim × each measure
    if dims and measures:
        for m in measures[:3]:  # max 3 measures
            p = bar_chart(df, x=dims[0], y=m,
                          title=f"{m.replace('_',' ').title()} by {dims[0].replace('_',' ').title()}",
                          top_n=12, output_dir=output_dir)
            if p:
                paths.append(p)

    # 3. Line chart over date if available
    if dates and measures:
        p = line_chart(df, x=dates[0], y=measures[0],
                       title=f"{measures[0].replace('_',' ').title()} over Time",
                       output_dir=output_dir)
        if p:
            paths.append(p)

    # 4. Pie for first categorical dim
    if dims and measures:
        p = pie_chart(df, labels_col=dims[0], values_col=measures[0],
                      title=f"{measures[0].replace('_',' ').title()} share by {dims[0].replace('_',' ').title()}",
                      output_dir=output_dir)
        if p:
            paths.append(p)

    # 5. Histograms for numeric columns
    for m in measures[:2]:
        p = histogram(df, column=m,
                      title=f"Distribution of {m.replace('_',' ').title()}",
                      output_dir=output_dir)
        if p:
            paths.append(p)

    log.info("auto_plot generated %d charts.", len(paths))
    return paths


# ── Quick smoke-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import numpy as np
    rng = np.random.default_rng(42)
    sample = pd.DataFrame({
        "city":     rng.choice(["Delhi", "Mumbai", "Bangalore", "Chennai"], 100),
        "category": rng.choice(["Electronics", "Food", "Apparel"], 100),
        "revenue":  rng.integers(500, 50000, 100),
        "quantity": rng.integers(1, 200, 100),
    })
    paths = auto_plot(sample, output_dir="test_plots")
    print("Generated:", paths)
