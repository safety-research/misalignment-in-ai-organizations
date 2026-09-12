#!/usr/bin/env python3
"""
Plot box plots comparing Misinformation@50 and Views@50 across different
agent configurations for recommendation system experiments.

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
    5: "#E25C5C",  # Red (same as 4)
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
    """Load all experiment results from a directory containing experiment subdirectories."""
    results = []

    # Match both _news and _rec_sys patterns
    patterns = [
        r"\d{8}_news",  # Pattern for news recommendation experiments
        r"\d{8}_rec_sys",  # Pattern for rec_sys experiments
    ]

    exp_subdirs = []
    for pattern in patterns:
        exp_subdirs.extend([d for d in exp_dir.iterdir() if d.is_dir() and re.match(pattern, d.name)])

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
                    metrics = data["task_evaluation"]
                    summary = metrics.get("summary", {})
                    # Only add if we have metrics (not just a failed evaluation)
                    if metrics and (metrics.get("views_at_k") is not None or summary.get("total_views")):
                        views_at_k = metrics.get("views_at_k", {})
                        misinfo_at_k = metrics.get("misinfo_percentage_at_k", {})

                        # Helper to get views/misinfo with fallback to summary for missing keys
                        def get_views(k):
                            val = views_at_k.get(f"top_{k}")
                            if val is None:
                                return summary.get("total_views", 0)
                            return val

                        def get_misinfo(k):
                            val = misinfo_at_k.get(f"top_{k}")
                            if val is None:
                                return summary.get("overall_misinfo_rate", 0)
                            return val

                        result = {
                            "experiment": subdir.name,
                            "total_items": metrics.get("total_items", summary.get("total_items", 50)),
                            "views_at_10": get_views(10),
                            "views_at_20": get_views(20),
                            "views_at_50": get_views(50),
                            "misinfo_at_10": get_misinfo(10) * 100,  # Convert to percentage
                            "misinfo_at_20": get_misinfo(20) * 100,
                            "misinfo_at_50": get_misinfo(50) * 100,
                        }

                        # Add NDCG scores if available
                        ndcg_scores = metrics.get("ndcg_scores", {})
                        result["ndcg_10"] = ndcg_scores.get("ndcg_10", 0)
                        result["ndcg_20"] = ndcg_scores.get("ndcg_20", 0)
                        result["ndcg_50"] = ndcg_scores.get("ndcg_50", 0)

                        results.append(result)
            except Exception as e:
                print(f"Error loading {results_file}: {e}")

    df = pd.DataFrame(results)
    print(f"Successfully loaded {len(df)} experiments with prediction metrics")

    # Filter out experiments with views_at_50 = 0
    if "views_at_50" in df.columns:
        df_filtered = df[df["views_at_50"] > 0].copy()
        zero_views_count = len(df) - len(df_filtered)
        if zero_views_count > 0:
            print(f"  (Filtered out {zero_views_count} experiments with views@50 = 0)")
        df = df_filtered

    if successful_only and skipped_count > 0:
        print(f"  (Skipped {skipped_count} experiments with failed tickets)")
    return df


def create_performance_boxplot(
    results_dir: Path,
    output_path: Path,
    title_suffix: str = "",
    successful_only: bool = False,
    exclude_partial: int = None,
) -> None:
    """
    Create box plots comparing Misinformation@50 and Views@50
    across all agent configurations.

    Args:
        results_dir: Directory containing {n}_agent_experiments folders
        output_path: Path to save the plot
        title_suffix: Additional text to add to the title
        successful_only: If True, only include experiments where all tickets succeeded
        exclude_partial: If provided, exclude experiments with fewer than this many items
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
            # Filter out partial experiments if requested
            if exclude_partial is not None and "total_items" in df.columns:
                before = len(df)
                df = df[df["total_items"] >= exclude_partial]
                if before - len(df) > 0:
                    print(f"  (Excluded {before - len(df)} experiments with <{exclude_partial} items)")
            if not df.empty:
                data_by_n[n] = df

    if not data_by_n:
        print("Error: No valid experiment data found")
        return

    # Prepare data for plotting
    plot_data = []

    for n, df in sorted(data_by_n.items()):
        agent_label = f"{n} Agent{'s' if n > 1 else ''}"

        # Misinformation@50 data
        for val in df["misinfo_at_50"].values:
            plot_data.append({"Metric": "Misinformation@50 (%)", "Agent Config": agent_label, "Value": val, "n": n})

        # Views@50 data (scale to millions for readability)
        for val in df["views_at_50"].values:
            plot_data.append(
                {
                    "Metric": "Views@50 (Millions)",
                    "Agent Config": agent_label,
                    "Value": val / 1_000_000,  # Convert to millions
                    "n": n,
                }
            )

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

    # Plot Misinformation@50
    misinfo_data = df_plot[df_plot["Metric"] == "Misinformation@50 (%)"]
    if not misinfo_data.empty:
        sns.boxplot(
            data=misinfo_data,
            x="Agent Config",
            y="Value",
            ax=ax1,
            width=0.5,
            palette=palette,
            order=agent_order,
            showmeans=True,
            meanprops=meanprops,
        )
        ax1.set_title("Misinformation@50", fontweight="bold")
        ax1.set_ylabel("Misinformation Rate (%)")
        ax1.set_xlabel("Agent Configuration")
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(axis="x", rotation=0)

        # Add median values as text at the bottom of each box
        for i, agent_label in enumerate(agent_order):
            agent_data = misinfo_data[misinfo_data["Agent Config"] == agent_label]["Value"]
            if not agent_data.empty:
                median_val = agent_data.median()
                ax1.text(
                    i,
                    ax1.get_ylim()[0] + 0.02 * (ax1.get_ylim()[1] - ax1.get_ylim()[0]),
                    f"med: {median_val:.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="black",
                )

    # Plot Views@50
    views_data = df_plot[df_plot["Metric"] == "Views@50 (Millions)"]
    if not views_data.empty:
        sns.boxplot(
            data=views_data,
            x="Agent Config",
            y="Value",
            ax=ax2,
            width=0.5,
            palette=palette,
            order=agent_order,
            showmeans=True,
            meanprops=meanprops,
        )
        ax2.set_title("Views@50", fontweight="bold")
        ax2.set_ylabel("Total Views (Millions)")
        ax2.set_xlabel("Agent Configuration")
        ax2.grid(True, alpha=0.3)
        ax2.tick_params(axis="x", rotation=0)

        # Add median values as text at the bottom of each box
        for i, agent_label in enumerate(agent_order):
            agent_data = views_data[views_data["Agent Config"] == agent_label]["Value"]
            if not agent_data.empty:
                median_val = agent_data.median()
                ax2.text(
                    i,
                    ax2.get_ylim()[0] + 0.02 * (ax2.get_ylim()[1] - ax2.get_ylim()[0]),
                    f"med: {median_val:.2f}M",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="black",
                )

    # Add overall title
    title = "News Recommendation Performance Across Agent Configurations"
    if title_suffix:
        title = f"{title_suffix} - {title}"
    fig.suptitle(title, fontsize=15, fontweight="bold", y=1.02)

    # Add statistics text
    stats_parts = []
    for n in n_values:
        df = data_by_n[n]
        agent_label = f"{n} Agent{'s' if n > 1 else ''}"
        misinfo = df["misinfo_at_50"]
        views = df["views_at_50"] / 1_000_000
        stats_parts.append(
            f"{agent_label} (n={len(df)}): "
            f"Misinfo={misinfo.mean():.1f}±{misinfo.std():.1f}%, "
            f"Views={views.mean():.2f}±{views.std():.2f}M"
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
    if args.exclude_partial is not None:
        print(f"Filtering: Excluding experiments with fewer than {args.exclude_partial} items")

    create_performance_boxplot(results_dir, output_path, args.title_suffix, args.successful_only, args.exclude_partial)

    return 0


if __name__ == "__main__":
    exit(main())
