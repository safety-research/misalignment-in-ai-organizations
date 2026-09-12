#!/usr/bin/env python3
"""
Plot scatter plots from analysis.json showing performance colored by:
- Rule-based levels
- Ground truth usage flags
- Prompting strategies
- Decision method

Plots are paneled: 1-agent vs 4-agent, 1-agent vs 8-agent side by side.
Color encodes num_agents, shape encodes categorical variable.

Usage:
    python plot_analysis_scatter.py --results-dir results/opus-4-5-v2-wm
"""

import argparse
import json
import matplotlib.pyplot as plt
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

# Markers for categorical variables
METHOD_MARKERS = {
    "none": "o",  # Circle - no separate risk assessment
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

DECISION_METHOD_MARKERS = {
    "treat_all": "o",  # Circle
    "treat_none": "x",  # X
    "risk_threshold": "^",  # Triangle
    "llm_judgment_zero_shot": "v",  # Inverted triangle - LLM zero-shot
    "llm_judgment_with_examples": "<",  # Left triangle - LLM with examples
    "rule_based": "s",  # Square
    "cost_sensitive": "D",  # Diamond
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
        if metrics.get("avg_cost_per_patient") is None or metrics.get("missed_sepsis_rate") is None:
            continue

        row = {
            "experiment_id": exp.get("experiment_id"),
            "num_agents": exp.get("num_agents", 1),
            "avg_cost_per_patient": metrics.get("avg_cost_per_patient"),
            "missed_sepsis_rate": metrics.get("missed_sepsis_rate"),
            "sensitivity": metrics.get("sensitivity"),
            "pareto_frontier": metrics.get("pareto_frontier", False),
            # Method for risk assessment (v2 schema)
            "method_risk": code_review.get("method_risk", "none"),
            # Prompting
            "prompting_risk": code_review.get("prompting_risk", "none"),
            # Ground truth usage (v2 schema)
            "use_gt_sepsis": code_review.get("use_gt_sepsis", False),
            # Decision method (v2 schema)
            "decision_method": code_review.get("decision_method", "other"),
        }
        rows.append(row)

    return pd.DataFrame(rows)


def get_comparison_pairs(df: pd.DataFrame) -> list[tuple[int, int]]:
    """Get pairs of (1, n) for comparison panels."""
    agents = sorted(df["num_agents"].unique())
    if 1 not in agents:
        return []
    return [(1, n) for n in agents if n != 1]


def plot_panel_scatter(
    df: pd.DataFrame,
    category_col: str,
    marker_map: dict,
    title: str,
    save_path: Path,
    category_label: str = None,
    is_boolean: bool = False,
) -> None:
    """Create paneled scatter plot: rows = 1v4, 1v8."""
    pairs = get_comparison_pairs(df)
    if not pairs:
        print(f"  Skipping {save_path.name}: need 1-agent data for comparison")
        return

    n_rows = len(pairs)
    fig, axes = plt.subplots(n_rows, 1, figsize=(8, 5 * n_rows))
    if n_rows == 1:
        axes = [axes]

    # Get all unique categories upfront for consistent legend ordering
    if is_boolean:
        categories = [False, True]
    else:
        categories = sorted(df[category_col].unique(), key=lambda c: str(c))

    for row_idx, (n1, n2) in enumerate(pairs):
        ax = axes[row_idx]
        ax.set_facecolor("#f5f5f5")

        # Filter to just these two agent counts
        df_panel = df[df["num_agents"].isin([n1, n2])]
        x = df_panel["avg_cost_per_patient"].values
        y = df_panel["missed_sepsis_rate"].values

        # Draw n2 first, then n1 on top (so 1-agent points are visible)
        for n_agents in [n2, n1]:
            for category in categories:
                marker = marker_map.get(category, "o")
                mask = (df_panel["num_agents"] == n_agents) & (df_panel[category_col] == category)

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

        ax.set_xlabel("Avg Cost per Patient ($)", fontsize=12, fontweight="bold")
        ax.set_ylabel("Missed Sepsis Rate", fontsize=12, fontweight="bold")
        ax.set_title(f"{n1}-agent vs {n2}-agent", fontsize=13, fontweight="bold")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x / 1000:.1f}K"))
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend(loc="lower left", fontsize=9, ncol=1, framealpha=0.95, edgecolor="gray", fancybox=True)

    plt.suptitle(
        f"{title} (color=agents, shape={category_label or category_col})", fontsize=14, fontweight="bold", y=1.01
    )
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {save_path}")


def plot_method_panels(df: pd.DataFrame, save_path: Path) -> None:
    """Create paneled scatter plot for method_risk."""
    plot_panel_scatter(df, "method_risk", METHOD_MARKERS, "Performance by Risk Assessment Method", save_path, "method")


def plot_gt_usage_panels(df: pd.DataFrame, save_path: Path) -> None:
    """Create paneled scatter plot for use_gt_sepsis."""
    plot_panel_scatter(
        df, "use_gt_sepsis", GT_USAGE_MARKERS, "Performance by GT Usage", save_path, "gt_usage", is_boolean=True
    )


def plot_decision_method_panels(df: pd.DataFrame, save_path: Path) -> None:
    """Create paneled scatter plot for decision_method."""
    plot_panel_scatter(
        df, "decision_method", DECISION_METHOD_MARKERS, "Performance by Decision Method", save_path, "method"
    )


def plot_prompting_panels(df: pd.DataFrame, save_path: Path) -> None:
    """Create paneled scatter plot for prompting_risk."""
    plot_panel_scatter(
        df, "prompting_risk", PROMPTING_MARKERS, "Performance by Prompting Strategy", save_path, "strategy"
    )


# Columns to merge into the CSV
ANALYSIS_COLUMNS = [
    "method_risk",
    "prompting_risk",
    "use_gt_sepsis",
    "decision_method",
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
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir) if args.output_dir else results_dir

    # Load data
    print(f"Loading analysis from {results_dir}...")
    df = load_analysis(results_dir)
    print(f"Loaded {len(df)} experiments with valid metrics")

    # Print summary
    print("\nData summary:")
    print(f"  Agents: {sorted(df['num_agents'].unique())}")
    print(f"  Method (risk): {df['method_risk'].value_counts().to_dict()}")
    print(f"  Prompting: {df['prompting_risk'].value_counts().to_dict()}")
    print(f"  Uses GT: {df['use_gt_sepsis'].value_counts().to_dict()}")
    print(f"  Decision method: {df['decision_method'].value_counts().to_dict()}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate paneled plots
    print("\nGenerating plots...")

    # Risk assessment method panels
    plot_method_panels(df, output_dir / "scatter_risk_method.png")

    # GT usage panels
    plot_gt_usage_panels(df, output_dir / "scatter_gt_usage.png")

    # Decision method panels
    plot_decision_method_panels(df, output_dir / "scatter_decision_method.png")

    # Risk assessment prompting panels
    plot_prompting_panels(df, output_dir / "scatter_risk_prompting.png")

    # Merge analysis columns into existing CSVs
    print("\nUpdating CSV files with analysis columns...")
    merge_analysis_to_csv(df, results_dir)

    print(f"\nAll plots saved to: {output_dir}")
    return 0


if __name__ == "__main__":
    exit(main())
