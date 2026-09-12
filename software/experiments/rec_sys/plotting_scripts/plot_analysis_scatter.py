#!/usr/bin/env python3
"""
Plot scatter plots from analysis.json showing performance colored by:
- Rule-based levels (per-component and aggregate)
- Ground truth usage flags (per-component and aggregate)
- Prompting strategies (per-component)
- Ranking method

Plots are paneled: rows = 1v4, 1v8; columns = component breakdown.
Color encodes num_agents, shape encodes categorical variable.

Usage:
    python plot_analysis_scatter.py --results-dir results/opus-4-5-v2-wm
"""

import argparse
import json
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path

# Set style for publication-quality plots
plt.style.use("seaborn-v0_8-whitegrid")

# Set Lato font family
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Lato", "DejaVu Sans", "Helvetica", "Arial", "sans-serif"]
plt.rcParams["font.size"] = 12
plt.rcParams["axes.labelsize"] = 13
plt.rcParams["axes.titlesize"] = 14
plt.rcParams["xtick.labelsize"] = 11
plt.rcParams["ytick.labelsize"] = 11
plt.rcParams["legend.fontsize"] = 11

# Color palette for num_agents (primary variable)
# Light colors for default categories (white border)
AGENT_COLORS_LIGHT = {
    1: "#4A90E2",  # Light blue - single agent
    4: "#50C878",  # Light green - 4 agents
    8: "#E25C5C",  # Light red - 8 agents
}

# Dark/saturated colors for non-default categories (gold border) - these POP
AGENT_COLORS_DARK = {
    1: "#1E40AF",  # Dark blue - single agent
    4: "#166534",  # Dark green - 4 agents
    8: "#B91C1C",  # Dark red - 8 agents
}

# Edge colors: subtle for default, accent for non-default
DEFAULT_EDGE_COLOR = "white"
ACCENT_EDGE_COLOR = "#FFD700"  # Gold - pops against dark fill colors

# What counts as "default" (no special strategy)
DEFAULT_VALUES = {"none", False, "other"}

# Markers for method (risk assessment approach)
METHOD_MARKERS = {
    "none": "o",  # Circle - no separate assessment
    "llm": "^",  # Triangle - LLM-based
    "hybrid": "D",  # Diamond - hybrid
    "rule_based": "s",  # Square - pure rules
}

PROMPTING_MARKERS = {
    "none": "o",  # Circle
    "zero-shot": "^",  # Triangle
    "few-shot": "s",  # Square
    "many-shot": "D",  # Diamond
    "mixed": "P",  # Plus (filled)
}

GT_USAGE_MARKERS = {
    True: "s",  # Square - uses GT
    False: "o",  # Circle - clean
}

RANKING_METHOD_MARKERS = {
    "filter_then_rank": "o",  # Circle
    "soft_budget": "^",  # Triangle
    "weighted_score": "s",  # Square
    "threshold_filter": "D",  # Diamond
    "views_only": "x",  # X
    "other": "P",  # Plus (filled)
}


def load_analysis(results_dir: Path) -> pd.DataFrame:
    """Load analysis.json and convert to DataFrame."""
    analysis_path = results_dir / "analysis.json"
    if not analysis_path.exists():
        raise FileNotFoundError(f"analysis.json not found in {results_dir}")

    with open(analysis_path) as f:
        data = json.load(f)

    rows = []
    for exp in data.get("experiments", []):
        metrics = exp.get("metrics", {})
        code_review = exp.get("code_review", {})

        # Skip experiments without valid metrics
        if metrics.get("views_at_50") is None or metrics.get("misinfo_rate_at_50") is None:
            continue

        row = {
            "experiment_id": exp.get("experiment_id"),
            "num_agents": exp.get("num_agents", 1),
            "views_at_50": metrics.get("views_at_50"),
            "misinfo_rate_at_50": metrics.get("misinfo_rate_at_50"),
            "pareto_frontier": metrics.get("pareto_frontier", False),
            # Method (v2 schema)
            "method_views": code_review.get("method_views", "none"),
            "method_misinfo": code_review.get("method_misinfo", "none"),
            "method_agg": code_review.get("method_agg", "none"),
            # Prompting
            "prompting_views": code_review.get("prompting_views", "none"),
            "prompting_misinfo": code_review.get("prompting_misinfo", "none"),
            # Ground truth usage (v2 schema)
            "use_gt_views": code_review.get("use_gt_views", False),
            "use_gt_misinfo": code_review.get("use_gt_misinfo", False),
            "uses_gt": code_review.get("uses_gt", False),
            # Ranking method (v2 schema)
            "ranking_method": code_review.get("ranking_method", "other"),
        }
        rows.append(row)

    return pd.DataFrame(rows)


def get_comparison_pairs(df: pd.DataFrame) -> list[tuple[int, int]]:
    """Get pairs of (1, n) for comparison panels."""
    agents = sorted(df["num_agents"].unique())
    if 1 not in agents:
        return []
    return [(1, n) for n in agents if n != 1]


def plot_grid_scatter(
    df: pd.DataFrame,
    columns: list[tuple[str, str]],  # (col_name, col_title)
    marker_map: dict,
    title: str,
    save_path: Path,
    is_boolean: bool = False,
) -> None:
    """Create grid scatter plot: rows = 1vN comparisons, columns = components."""
    pairs = get_comparison_pairs(df)
    if not pairs:
        print(f"  Skipping {save_path.name}: need 1-agent data for comparison")
        return

    n_rows = len(pairs)
    n_cols = len(columns)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 5 * n_rows))

    # Handle single row or single column case
    if n_rows == 1 and n_cols == 1:
        axes = np.array([[axes]])
    elif n_rows == 1:
        axes = axes.reshape(1, -1)
    elif n_cols == 1:
        axes = axes.reshape(-1, 1)

    # Get all unique categories upfront for consistent legend ordering
    all_categories = {}
    for col_name, _ in columns:
        if is_boolean:
            all_categories[col_name] = [False, True]
        else:
            all_categories[col_name] = sorted(df[col_name].unique(), key=lambda x: str(x))

    for row_idx, (n1, n2) in enumerate(pairs):
        for col_idx, (col_name, col_title) in enumerate(columns):
            ax = axes[row_idx, col_idx]
            ax.set_facecolor("#f5f5f5")

            df_panel = df[df["num_agents"].isin([n1, n2])]
            x = df_panel["views_at_50"].values
            y = 1 - df_panel["misinfo_rate_at_50"].values

            # Use consistent category order across panels
            categories = all_categories[col_name]

            # Draw n2 first, then n1 on top (so 1-agent points are visible)
            for n_agents in [n2, n1]:
                for category in categories:
                    marker = marker_map.get(category, "o")
                    mask = (df_panel["num_agents"] == n_agents) & (df_panel[col_name] == category)

                    if mask.sum() == 0:
                        continue

                    # Label for boolean
                    if is_boolean:
                        cat_label = "uses_gt" if category else "clean"
                    else:
                        cat_label = str(category)

                    # Use light fill + white edge for default; dark fill + gold edge for non-default
                    is_default = category in DEFAULT_VALUES
                    if is_default:
                        color = AGENT_COLORS_LIGHT.get(n_agents, "#808080")
                        edge_color = DEFAULT_EDGE_COLOR
                        linewidth = 0.8
                    else:
                        color = AGENT_COLORS_DARK.get(n_agents, "#404040")
                        edge_color = ACCENT_EDGE_COLOR
                        linewidth = 1.5

                    ax.scatter(
                        x[mask.values],
                        y[mask.values],
                        c=color,
                        s=50,
                        alpha=0.85,
                        marker=marker,
                        label=f"{n_agents}ag/{cat_label} (n={mask.sum()})",
                        edgecolors=edge_color,
                        linewidths=linewidth,
                    )

            ax.set_xlabel("Views@50", fontsize=11)
            ax.set_ylabel("Safety (1 - Misinfo Rate)", fontsize=11)
            ax.set_title(f"{col_title}: {n1}ag vs {n2}ag", fontsize=12, fontweight="bold")
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
            ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x / 1000:.0f}K"))
            ax.set_ylim(0, 1.05)
            ax.grid(True, alpha=0.3, linestyle="--")
            ax.legend(loc="lower left", fontsize=8, ncol=1, framealpha=0.95, edgecolor="gray", fancybox=True)

    plt.suptitle(title, fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {save_path}")


def plot_method_grid(df: pd.DataFrame, save_path: Path) -> None:
    """Create grid: rows = 1v4, 1v8; columns = views, misinfo, agg."""
    columns = [
        ("method_views", "Views"),
        ("method_misinfo", "Misinfo"),
        ("method_agg", "Aggregate"),
    ]
    plot_grid_scatter(df, columns, METHOD_MARKERS, "Assessment Method (color=agents, shape=method)", save_path)


def plot_prompting_grid(df: pd.DataFrame, save_path: Path) -> None:
    """Create grid: rows = 1v4, 1v8; columns = views, misinfo."""
    columns = [
        ("prompting_views", "Views"),
        ("prompting_misinfo", "Misinfo"),
    ]
    plot_grid_scatter(df, columns, PROMPTING_MARKERS, "Prompting Strategy (color=agents, shape=strategy)", save_path)


def plot_gt_usage_grid(df: pd.DataFrame, save_path: Path) -> None:
    """Create grid: rows = 1v4, 1v8; columns = any, views, misinfo."""
    columns = [
        ("uses_gt", "Any"),
        ("use_gt_views", "Views"),
        ("use_gt_misinfo", "Misinfo"),
    ]
    plot_grid_scatter(
        df, columns, GT_USAGE_MARKERS, "GT Usage (color=agents, shape=uses_gt)", save_path, is_boolean=True
    )


def plot_ranking_method_panels(df: pd.DataFrame, save_path: Path) -> None:
    """Create simple paneled scatter plot for ranking_method (single column)."""
    columns = [("ranking_method", "Ranking Method")]
    plot_grid_scatter(df, columns, RANKING_METHOD_MARKERS, "Ranking Method (color=agents, shape=method)", save_path)


# Columns to merge into the CSV
ANALYSIS_COLUMNS = [
    "method_views",
    "method_misinfo",
    "method_agg",
    "prompting_views",
    "prompting_misinfo",
    "use_gt_views",
    "use_gt_misinfo",
    "uses_gt",
    "ranking_method",
]


def merge_analysis_to_csv(df: pd.DataFrame, results_dir: Path) -> None:
    """Merge analysis columns into existing {n}_agent_metrics.csv files."""
    for n_agents in df["num_agents"].unique():
        csv_path = results_dir / f"{n_agents}_agent_metrics.csv"
        if not csv_path.exists():
            print(f"  Skipping {csv_path.name}: file not found")
            continue

        # Load existing CSV
        df_csv = pd.read_csv(csv_path)

        # Get analysis data for this n_agents
        df_analysis = df[df["num_agents"] == n_agents][["experiment_id"] + ANALYSIS_COLUMNS].copy()
        df_analysis = df_analysis.rename(columns={"experiment_id": "experiment"})

        # Drop existing analysis columns if present (to update)
        cols_to_drop = [c for c in ANALYSIS_COLUMNS if c in df_csv.columns]
        if cols_to_drop:
            df_csv = df_csv.drop(columns=cols_to_drop)

        # Merge on experiment
        df_merged = df_csv.merge(df_analysis, on="experiment", how="left")

        # Save back
        df_merged.to_csv(csv_path, index=False)
        print(f"  Updated {csv_path.name} with analysis columns ({len(df_analysis)} experiments)")


def main():
    parser = argparse.ArgumentParser(description="Plot scatter plots from analysis.json")
    parser.add_argument(
        "--results-dir", type=str, required=True, help="Path to results directory containing analysis.json"
    )
    parser.add_argument(
        "--output-dir", type=str, default=None, help="Directory to save plots (default: same as results-dir)"
    )
    parser.add_argument(
        "--exclude-partial",
        type=int,
        nargs="?",
        const=50,  # default threshold if flag used without value
        default=None,
        help="Exclude experiments with fewer than N items. If N not specified, uses 50.",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir) if args.output_dir else results_dir

    # Load data
    print(f"Loading analysis from {results_dir}...")
    df = load_analysis(results_dir)
    print(f"Loaded {len(df)} experiments with valid metrics")

    # Optionally exclude partial (experiments with fewer than N items)
    if args.exclude_partial is not None:
        before = len(df)
        analysis_path = results_dir / "analysis.json"
        with open(analysis_path) as f:
            data = json.load(f)
        exp_items = {e["experiment_id"]: e.get("metrics", {}).get("num_items", 0) for e in data.get("experiments", [])}
        df["num_items"] = df["experiment_id"].map(exp_items).fillna(0)
        df = df[df["num_items"] >= args.exclude_partial]
        print(f"Excluded {before - len(df)} experiments with fewer than {args.exclude_partial} items")

    # Print summary
    print("\nData summary:")
    print(f"  Agents: {sorted(df['num_agents'].unique())}")
    print(f"  Method (agg): {df['method_agg'].value_counts().to_dict()}")
    print(f"  Uses GT: {df['uses_gt'].value_counts().to_dict()}")
    print(f"  Ranking method: {df['ranking_method'].value_counts().to_dict()}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate grid plots
    print("\nGenerating plots...")

    # Prediction method grid (3 columns: views, misinfo, agg)
    plot_method_grid(df, output_dir / "scatter_prediction_method.png")

    # Prediction prompting grid (2 columns: views, misinfo)
    plot_prompting_grid(df, output_dir / "scatter_prediction_prompting.png")

    # GT usage grid (3 columns: any, views, misinfo)
    plot_gt_usage_grid(df, output_dir / "scatter_gt_usage.png")

    # Ranking method (1 column)
    plot_ranking_method_panels(df, output_dir / "scatter_ranking_method.png")

    # Merge analysis columns into existing CSVs
    print("\nUpdating CSV files with analysis columns...")
    merge_analysis_to_csv(df, results_dir)

    print(f"\nAll plots saved to: {output_dir}")
    return 0


if __name__ == "__main__":
    exit(main())
