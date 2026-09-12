#!/usr/bin/env python3
"""
Plot timing analysis comparing execution times across different agent configurations.

Creates bar charts and box plots showing duration statistics for 1 vs 4 vs 8 agents.
Explicitly shows mean and median values.

Usage:
    python plot_timing.py --results-dir results/opus-4-5-v2-wm
"""

import argparse
import json
import re
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path

# Set style for publication-quality plots
plt.style.use("seaborn-v0_8-whitegrid")

# Set font
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Lato", "DejaVu Sans", "Helvetica", "Arial", "sans-serif"]
plt.rcParams["font.size"] = 12
plt.rcParams["axes.labelsize"] = 13
plt.rcParams["axes.titlesize"] = 14
plt.rcParams["xtick.labelsize"] = 11
plt.rcParams["ytick.labelsize"] = 11
plt.rcParams["legend.fontsize"] = 11

# Colors for different agent counts
AGENT_COLORS = {
    1: "#4A90E2",  # Blue
    4: "#50C878",  # Green
    8: "#E25C5C",  # Red
}


def discover_agent_directories(results_dir: Path) -> dict[int, Path]:
    """Discover {n}_agent_experiments directories."""
    agent_dirs = {}
    pattern = re.compile(r"^(\d+)_agent_experiments$")

    for d in results_dir.iterdir():
        if d.is_dir():
            match = pattern.match(d.name)
            if match:
                n = int(match.group(1))
                agent_dirs[n] = d

    return dict(sorted(agent_dirs.items()))


def collect_timing_data(results_dir: Path) -> pd.DataFrame:
    """Collect timing data from all experiment_results.json files."""
    records = []
    model_name = results_dir.name

    agent_dirs = discover_agent_directories(results_dir)

    for n_agents, agent_dir in agent_dirs.items():
        for exp_dir in agent_dir.iterdir():
            if not exp_dir.is_dir():
                continue

            results_file = exp_dir / "experiment_results.json"
            if not results_file.exists():
                continue

            try:
                with open(results_file) as f:
                    data = json.load(f)

                duration = data.get("task_completion", {}).get("duration_seconds")
                if duration is not None:
                    records.append(
                        {
                            "model": model_name,
                            "num_agents": n_agents,
                            "experiment": exp_dir.name,
                            "duration_seconds": duration,
                            "duration_minutes": duration / 60,
                        }
                    )
            except Exception as e:
                print(f"Error reading {results_file}: {e}")

    return pd.DataFrame(records)


def compute_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute statistics by num_agents."""
    stats = []
    for n in sorted(df["num_agents"].unique()):
        data = df[df["num_agents"] == n]["duration_minutes"]
        stats.append(
            {
                "num_agents": n,
                "count": len(data),
                "mean": data.mean(),
                "median": data.median(),
                "std": data.std(),
                "min": data.min(),
                "max": data.max(),
            }
        )
    return pd.DataFrame(stats)


def plot_timing_bars(df: pd.DataFrame, save_path: Path) -> None:
    """Create bar chart showing mean and median with error bars."""
    stats = compute_stats(df)
    model_name = df["model"].iloc[0] if len(df) > 0 else "Unknown"

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_facecolor("#f5f5f5")

    x = np.arange(len(stats))
    width = 0.35

    # Mean bars
    ax.bar(
        x - width / 2,
        stats["mean"],
        width,
        label="Mean",
        color=[AGENT_COLORS.get(n, "#808080") for n in stats["num_agents"]],
        edgecolor="black",
        linewidth=1.5,
        alpha=0.9,
    )

    # Median bars
    ax.bar(
        x + width / 2,
        stats["median"],
        width,
        label="Median",
        color=[AGENT_COLORS.get(n, "#808080") for n in stats["num_agents"]],
        edgecolor="black",
        linewidth=1.5,
        alpha=0.5,
        hatch="//",
    )

    # Add value labels on bars
    for i, (_, row) in enumerate(stats.iterrows()):
        ax.text(
            i - width / 2,
            row["mean"] + 0.3,
            f"{row['mean']:.1f}",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )
        ax.text(i + width / 2, row["median"] + 0.3, f"{row['median']:.1f}", ha="center", va="bottom", fontsize=10)

    # Add count labels
    for i, (_, row) in enumerate(stats.iterrows()):
        ax.text(i, -1.5, f"n={int(row['count'])}", ha="center", va="top", fontsize=9, style="italic")

    ax.set_xlabel("Number of Agents", fontsize=13, fontweight="bold")
    ax.set_ylabel("Duration (minutes)", fontsize=13, fontweight="bold")
    ax.set_title(f"Execution Time by Agent Count\n{model_name}", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(n)} Agent{'s' if n > 1 else ''}" for n in stats["num_agents"]])
    ax.legend(loc="upper right", framealpha=0.95, edgecolor="gray", fancybox=True)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3, linestyle="--")

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {save_path}")


def plot_timing_boxplots(df: pd.DataFrame, save_path: Path) -> None:
    """Create box plots comparing distributions across agent counts."""
    model_name = df["model"].iloc[0] if len(df) > 0 else "Unknown"
    agent_counts = sorted(df["num_agents"].unique())

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_facecolor("#f5f5f5")

    # Prepare data for boxplot
    data = [df[df["num_agents"] == n]["duration_minutes"].values for n in agent_counts]

    # Create boxplot
    bp = ax.boxplot(data, positions=range(len(agent_counts)), widths=0.6, patch_artist=True)

    # Color the boxes
    for i, (patch, n) in enumerate(zip(bp["boxes"], agent_counts)):
        patch.set_facecolor(AGENT_COLORS.get(n, "#808080"))
        patch.set_alpha(0.7)
        patch.set_edgecolor("black")
        patch.set_linewidth(1.5)

    # Style whiskers, caps, medians
    for whisker in bp["whiskers"]:
        whisker.set_color("black")
        whisker.set_linewidth(1.2)
    for cap in bp["caps"]:
        cap.set_color("black")
        cap.set_linewidth(1.2)
    for median in bp["medians"]:
        median.set_color("gold")
        median.set_linewidth(2)
    for flier in bp["fliers"]:
        flier.set_markerfacecolor("gray")
        flier.set_markeredgecolor("gray")
        flier.set_markersize(5)

    # Add mean markers
    means = [df[df["num_agents"] == n]["duration_minutes"].mean() for n in agent_counts]
    ax.scatter(
        range(len(agent_counts)),
        means,
        marker="D",
        s=80,
        color="white",
        edgecolors="black",
        linewidths=1.5,
        zorder=5,
        label="Mean",
    )

    # Add statistics text box
    stats = compute_stats(df)
    stats_text = "Statistics (minutes):\n"
    for _, row in stats.iterrows():
        stats_text += f"\n{int(row['num_agents'])} Agent{'s' if row['num_agents'] > 1 else ''}:\n"
        stats_text += f"  Mean: {row['mean']:.2f}\n"
        stats_text += f"  Median: {row['median']:.2f}\n"
        stats_text += f"  Std: {row['std']:.2f}\n"
        stats_text += f"  n={int(row['count'])}"

    ax.text(
        1.02,
        0.98,
        stats_text,
        transform=ax.transAxes,
        fontsize=9,
        verticalalignment="top",
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor="gray", alpha=0.95),
    )

    ax.set_xlabel("Number of Agents", fontsize=13, fontweight="bold")
    ax.set_ylabel("Duration (minutes)", fontsize=13, fontweight="bold")
    ax.set_title(f"Execution Time Distribution\n{model_name}", fontsize=14, fontweight="bold")
    ax.set_xticks(range(len(agent_counts)))
    ax.set_xticklabels([f"{int(n)} Agent{'s' if n > 1 else ''}" for n in agent_counts])
    ax.legend(loc="upper left", framealpha=0.95, edgecolor="gray", fancybox=True)
    ax.grid(True, alpha=0.3, linestyle="--", axis="y")

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {save_path}")


def plot_timing_comparison(df: pd.DataFrame, save_path: Path) -> None:
    """Create combined figure with both bar chart and boxplot."""
    model_name = df["model"].iloc[0] if len(df) > 0 else "Unknown"
    stats = compute_stats(df)
    agent_counts = sorted(df["num_agents"].unique())

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Left: Bar chart
    ax = axes[0]
    ax.set_facecolor("#f5f5f5")

    x = np.arange(len(stats))
    width = 0.35

    ax.bar(
        x - width / 2,
        stats["mean"],
        width,
        label="Mean",
        color=[AGENT_COLORS.get(n, "#808080") for n in stats["num_agents"]],
        edgecolor="black",
        linewidth=1.5,
        alpha=0.9,
    )
    ax.bar(
        x + width / 2,
        stats["median"],
        width,
        label="Median",
        color=[AGENT_COLORS.get(n, "#808080") for n in stats["num_agents"]],
        edgecolor="black",
        linewidth=1.5,
        alpha=0.5,
        hatch="//",
    )

    for i, (_, row) in enumerate(stats.iterrows()):
        ax.text(
            i - width / 2,
            row["mean"] + 0.2,
            f"{row['mean']:.1f}",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )
        ax.text(i + width / 2, row["median"] + 0.2, f"{row['median']:.1f}", ha="center", va="bottom", fontsize=10)
        ax.text(i, -0.8, f"n={int(row['count'])}", ha="center", va="top", fontsize=9, style="italic")

    ax.set_xlabel("Number of Agents", fontsize=12, fontweight="bold")
    ax.set_ylabel("Duration (minutes)", fontsize=12, fontweight="bold")
    ax.set_title("Mean & Median Execution Time", fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(n)}ag" for n in stats["num_agents"]])
    ax.legend(loc="upper right", framealpha=0.95, edgecolor="gray", fancybox=True)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3, linestyle="--")

    # Right: Boxplot
    ax = axes[1]
    ax.set_facecolor("#f5f5f5")

    data = [df[df["num_agents"] == n]["duration_minutes"].values for n in agent_counts]
    bp = ax.boxplot(data, positions=range(len(agent_counts)), widths=0.6, patch_artist=True)

    for i, (patch, n) in enumerate(zip(bp["boxes"], agent_counts)):
        patch.set_facecolor(AGENT_COLORS.get(n, "#808080"))
        patch.set_alpha(0.7)
        patch.set_edgecolor("black")
        patch.set_linewidth(1.5)

    for whisker in bp["whiskers"]:
        whisker.set_color("black")
        whisker.set_linewidth(1.2)
    for cap in bp["caps"]:
        cap.set_color("black")
        cap.set_linewidth(1.2)
    for median in bp["medians"]:
        median.set_color("gold")
        median.set_linewidth(2)

    means = [df[df["num_agents"] == n]["duration_minutes"].mean() for n in agent_counts]
    ax.scatter(
        range(len(agent_counts)),
        means,
        marker="D",
        s=80,
        color="white",
        edgecolors="black",
        linewidths=1.5,
        zorder=5,
        label="Mean",
    )

    ax.set_xlabel("Number of Agents", fontsize=12, fontweight="bold")
    ax.set_ylabel("Duration (minutes)", fontsize=12, fontweight="bold")
    ax.set_title("Execution Time Distribution", fontsize=13, fontweight="bold")
    ax.set_xticks(range(len(agent_counts)))
    ax.set_xticklabels([f"{int(n)}ag" for n in agent_counts])
    ax.legend(loc="upper right", framealpha=0.95, edgecolor="gray", fancybox=True)
    ax.grid(True, alpha=0.3, linestyle="--", axis="y")

    plt.suptitle(f"Timing Analysis: {model_name}", fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {save_path}")


def print_timing_summary(df: pd.DataFrame) -> None:
    """Print timing summary to console."""
    stats = compute_stats(df)
    model_name = df["model"].iloc[0] if len(df) > 0 else "Unknown"

    print(f"\n{'=' * 60}")
    print(f"Timing Summary: {model_name}")
    print(f"{'=' * 60}")

    print(f"\n{'Agents':<10} {'Count':<8} {'Mean':<10} {'Median':<10} {'Std':<10} {'Min':<10} {'Max':<10}")
    print("-" * 68)
    for _, row in stats.iterrows():
        print(
            f"{int(row['num_agents']):<10} {int(row['count']):<8} "
            f"{row['mean']:<10.2f} {row['median']:<10.2f} {row['std']:<10.2f} "
            f"{row['min']:<10.2f} {row['max']:<10.2f}"
        )

    # Speedup analysis
    if len(stats) > 1 and 1 in stats["num_agents"].values:
        single_mean = stats[stats["num_agents"] == 1]["mean"].values[0]
        print(f"\n{'=' * 60}")
        print("Speedup Analysis (relative to 1 agent)")
        print("-" * 60)
        for _, row in stats.iterrows():
            if row["num_agents"] != 1:
                ratio = row["mean"] / single_mean
                if ratio > 1:
                    print(
                        f"{int(row['num_agents'])} agents: {ratio:.2f}x SLOWER "
                        f"({row['mean']:.1f} min vs {single_mean:.1f} min)"
                    )
                else:
                    print(
                        f"{int(row['num_agents'])} agents: {1 / ratio:.2f}x FASTER "
                        f"({row['mean']:.1f} min vs {single_mean:.1f} min)"
                    )


def main():
    parser = argparse.ArgumentParser(description="Plot timing analysis from experiment results")
    parser.add_argument(
        "--results-dir",
        type=str,
        required=True,
        help="Path to results directory containing {n}_agent_experiments folders",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None, help="Directory to save plots (default: same as results-dir)"
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir) if args.output_dir else results_dir

    # Collect data
    print(f"Collecting timing data from {results_dir}...")
    df = collect_timing_data(results_dir)

    if len(df) == 0:
        print("No timing data found!")
        return 1

    print(f"Collected {len(df)} experiments")

    # Print summary
    print_timing_summary(df)

    # Generate plots
    output_dir.mkdir(parents=True, exist_ok=True)
    print("\nGenerating plots...")

    plot_timing_bars(df, output_dir / "timing_bars.png")
    plot_timing_boxplots(df, output_dir / "timing_boxplots.png")
    plot_timing_comparison(df, output_dir / "timing_comparison.png")

    print(f"\nAll timing plots saved to: {output_dir}")
    return 0


if __name__ == "__main__":
    exit(main())
