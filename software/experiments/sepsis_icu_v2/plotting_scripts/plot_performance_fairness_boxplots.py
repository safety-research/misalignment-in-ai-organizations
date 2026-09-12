#!/usr/bin/env python3
"""
Plot box plots comparing Missed Sepsis Rate and Average Cost per Patient
across different agent configurations for sepsis ICU experiments.

Auto-discovers {n}_agent_experiments folders and shows all n values
as categories in the same boxplot.
"""

import argparse
import json
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path
import seaborn as sns
import re

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
plt.rcParams["figure.titlesize"] = 15

# Color palette for different n values
N_COLORS = {
    1: "#4A90E2",  # Blue
    2: "#7B68EE",  # Medium slate blue
    4: "#E25C5C",  # Red
    8: "#50C878",  # Emerald green
    16: "#FFB347",  # Pastel orange
}


def get_color_palette(n_values: list[int]) -> dict:
    """Get color palette for the given n values."""
    palette = {}
    for n in n_values:
        if n in N_COLORS:
            palette[f"{n} Agent{'s' if n > 1 else ''}"] = N_COLORS[n]
        else:
            # Fallback to tab10 colors
            import numpy as np

            colors = plt.cm.tab10(np.linspace(0, 1, 10))
            palette[f"{n} Agent{'s' if n > 1 else ''}"] = colors[n % 10]
    return palette


def discover_agent_directories(results_dir: Path) -> dict[int, Path]:
    """Discover all {n}_agent_experiments directories and return dict mapping n -> path."""
    agent_dirs = {}
    pattern = re.compile(r"^(\d+)_agent_experiments$")

    for d in results_dir.iterdir():
        if d.is_dir():
            match = pattern.match(d.name)
            if match:
                n = int(match.group(1))
                agent_dirs[n] = d

    return dict(sorted(agent_dirs.items()))


def load_experiment_results_from_dir(exp_dir: Path, successful_only: bool = False) -> pd.DataFrame:
    """Load all experiment results from a directory containing experiment subdirectories.

    Args:
        exp_dir: Directory containing experiment subdirectories
        successful_only: If True, only include experiments where all tickets succeeded
    """
    results = []

    # Find all experiment directories (matches pattern like YYYYMMDD_sepsis_HHMMSS)
    # Pattern for sepsis experiments
    pattern = r"\d{8}_sepsis_\d+"

    exp_subdirs = [d for d in exp_dir.iterdir() if d.is_dir() and re.match(pattern, d.name)]

    print(f"Found {len(exp_subdirs)} experiment directories in {exp_dir}")

    skipped_count = 0
    for subdir in exp_subdirs:
        results_file = subdir / "experiment_results.json"
        if results_file.exists():
            try:
                with open(results_file, "r") as f:
                    data = json.load(f)

                # Check if we should skip this experiment
                if successful_only:
                    task_completion = data.get("task_completion", {})
                    failed_tickets = task_completion.get("failed_tickets", 0)
                    if failed_tickets > 0:
                        skipped_count += 1
                        continue

                # Extract metrics from task_evaluation
                if data.get("task_evaluation"):
                    task_eval = data["task_evaluation"]

                    # Handle nested structure (cost_metrics, sepsis_metrics, decision_statistics)
                    cost_metrics = task_eval.get("cost_metrics", {})
                    sepsis_metrics = task_eval.get("sepsis_metrics", {})
                    decision_stats = task_eval.get("decision_statistics", {})

                    # Only add if we have metrics (not just a failed evaluation)
                    if sepsis_metrics and sepsis_metrics.get("sensitivity") is not None:
                        result = {
                            "experiment": subdir.name,
                            "sensitivity": sepsis_metrics.get("sensitivity", 0),
                            "specificity": sepsis_metrics.get("specificity", 0)
                            if sepsis_metrics.get("specificity") is not None
                            else 0,
                            "precision": sepsis_metrics.get("precision", 0),
                            "avg_cost_per_patient": cost_metrics.get("average_cost_per_patient", 0),
                            "total_cost": cost_metrics.get("total_cost", 0),
                            "sepsis_case_treatment_rate": sepsis_metrics.get("sepsis_case_treatment_rate", 0),
                            "missed_sepsis_rate": sepsis_metrics.get("missed_sepsis_rate", 0),
                            "treatment_rate": decision_stats.get("treatment_rate", 0),
                        }

                        results.append(result)
            except Exception as e:
                print(f"Error loading {results_file}: {e}")

    df = pd.DataFrame(results)
    print(f"Successfully loaded {len(df)} experiments with prediction metrics")
    if successful_only and skipped_count > 0:
        print(f"  (Skipped {skipped_count} experiments with failed tickets)")
    return df


def create_performance_boxplot(
    results_dir: Path, output_path: Path, title_suffix: str = "", successful_only: bool = False
) -> None:
    """
    Create box plots comparing Missed Sepsis Rate and Average Cost per Patient
    across all agent configurations.

    Args:
        results_dir: Directory containing {n}_agent_experiments folders
        output_path: Path to save the plot
        title_suffix: Additional text to add to the title
        successful_only: If True, only include experiments where all tickets succeeded
    """
    # Discover agent directories
    agent_dirs = discover_agent_directories(results_dir)

    if not agent_dirs:
        print(f"Error: No *_agent_experiments directories found in {results_dir}")
        return

    print(f"Found {len(agent_dirs)} agent configurations: {list(agent_dirs.keys())}")

    # Load data for each n
    data_by_n: dict[int, pd.DataFrame] = {}
    for n, dir_path in agent_dirs.items():
        print(f"\nLoading {n}-agent experiments...")
        df = load_experiment_results_from_dir(dir_path, successful_only)
        if not df.empty:
            data_by_n[n] = df

    if not data_by_n:
        print("Error: No valid experiment data found")
        return

    # Prepare data for plotting
    plot_data = []

    for n, df in sorted(data_by_n.items()):
        agent_label = f"{n} Agent{'s' if n > 1 else ''}"

        # Missed Sepsis Rate data
        for val in df["missed_sepsis_rate"].values:
            plot_data.append({"Metric": "Missed Sepsis Rate (%)", "Agent Config": agent_label, "Value": val, "n": n})

        # Average Cost per Patient data
        for val in df["avg_cost_per_patient"].values:
            plot_data.append({"Metric": "Avg Cost per Patient ($)", "Agent Config": agent_label, "Value": val, "n": n})

    df_plot = pd.DataFrame(plot_data)

    # Get color palette
    n_values = sorted(data_by_n.keys())
    palette = get_color_palette(n_values)

    # Create subplots for the two metrics
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Sort agent configs by n for consistent ordering
    agent_order = [f"{n} Agent{'s' if n > 1 else ''}" for n in n_values]

    # Mean marker properties (diamond)
    meanprops = dict(marker="D", markerfacecolor="white", markeredgecolor="black", markersize=8)

    # Plot Missed Sepsis Rate
    missed_data = df_plot[df_plot["Metric"] == "Missed Sepsis Rate (%)"]
    if not missed_data.empty:
        sns.boxplot(
            data=missed_data,
            x="Agent Config",
            y="Value",
            ax=ax1,
            width=0.5,
            palette=palette,
            order=agent_order,
            showmeans=True,
            meanprops=meanprops,
        )
        ax1.set_title("Missed Sepsis Rate", fontweight="bold")
        ax1.set_ylabel("Missed Sepsis Rate (%)")
        ax1.set_xlabel("Agent Configuration")
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(axis="x", rotation=0)

        # Add median values as text at the bottom of each box
        for i, agent_label in enumerate(agent_order):
            agent_data = missed_data[missed_data["Agent Config"] == agent_label]["Value"]
            if not agent_data.empty:
                median_val = agent_data.median()
                ax1.text(
                    i,
                    ax1.get_ylim()[0] + 0.02 * (ax1.get_ylim()[1] - ax1.get_ylim()[0]),
                    f"med: {median_val:.1f}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="black",
                )

    # Plot Average Cost per Patient
    cost_data = df_plot[df_plot["Metric"] == "Avg Cost per Patient ($)"]
    if not cost_data.empty:
        sns.boxplot(
            data=cost_data,
            x="Agent Config",
            y="Value",
            ax=ax2,
            width=0.5,
            palette=palette,
            order=agent_order,
            showmeans=True,
            meanprops=meanprops,
        )
        ax2.set_title("Average Cost per Patient", fontweight="bold")
        ax2.set_ylabel("Average Cost per Patient ($)")
        ax2.set_xlabel("Agent Configuration")
        ax2.grid(True, alpha=0.3)
        ax2.tick_params(axis="x", rotation=0)

        # Add median values as text at the bottom of each box
        for i, agent_label in enumerate(agent_order):
            agent_data = cost_data[cost_data["Agent Config"] == agent_label]["Value"]
            if not agent_data.empty:
                median_val = agent_data.median()
                ax2.text(
                    i,
                    ax2.get_ylim()[0] + 0.02 * (ax2.get_ylim()[1] - ax2.get_ylim()[0]),
                    f"med: ${median_val:.0f}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="black",
                )

    # Add overall title
    title = "Sepsis ICU Performance Comparison Across Agent Configurations"
    if title_suffix:
        title = f"{title_suffix} - {title}"
    fig.suptitle(title, fontsize=15, fontweight="bold", y=1.02)

    # Add statistics text
    stats_parts = []
    for n in n_values:
        df = data_by_n[n]
        agent_label = f"{n} Agent{'s' if n > 1 else ''}"
        missed = df["missed_sepsis_rate"]
        cost = df["avg_cost_per_patient"]
        stats_parts.append(
            f"{agent_label} (n={len(df)}): "
            f"Missed={missed.mean():.1f}±{missed.std():.1f}%, "
            f"Cost=${cost.mean():.0f}±${cost.std():.0f}"
        )

    stats_text = " | ".join(stats_parts)
    fig.text(
        0.5,
        -0.02,
        stats_text,
        ha="center",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor="gray", alpha=0.9),
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", pad_inches=0.2)
    plt.close()

    print(f"\nBox plot saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Create box plots comparing performance metrics across agent configurations"
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        required=True,
        help="Path to results directory containing {n}_agent_experiments folders",
    )
    parser.add_argument(
        "--output", type=str, default="boxplots.png", help="Path to save the plot (default: boxplots.png)"
    )
    parser.add_argument("--title-suffix", type=str, default="", help="Additional text to add to the plot title")
    parser.add_argument(
        "--successful-only", action="store_true", help="Only include experiments where all tickets succeeded"
    )

    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    output_path = Path(args.output)

    if not results_dir.exists():
        print(f"Error: Results directory not found: {results_dir}")
        return 1

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Creating box plots...")
    print(f"Results directory: {results_dir}")
    print(f"Output: {output_path}")
    if args.successful_only:
        print("Filtering: Only including experiments with all tickets succeeded")

    create_performance_boxplot(results_dir, output_path, args.title_suffix, args.successful_only)

    return 0


if __name__ == "__main__":
    exit(main())
