#!/usr/bin/env python3
"""
Plot Pareto frontier for recommendation system experiments.
Views@K vs Misinformation@K metrics.

Auto-discovers {n}_agent_experiments folders and generates:
1. Combined plot with all n values
2. Separate 1-vs-n plots for each n != 1
3. {n}_agent_metrics.csv for each n
"""

import argparse
import json
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
import seaborn as sns
import re

# Set style for publication-quality plots
plt.style.use("seaborn-v0_8-whitegrid")
sns.set_palette("Set2")

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


def get_color_for_n(n: int) -> str:
    """Get a color for a given n value."""
    if n in N_COLORS:
        return N_COLORS[n]
    # Generate a color based on n if not in predefined palette
    colors = plt.cm.tab10(np.linspace(0, 1, 10))
    return colors[n % 10]


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
                    # Only add if we have metrics
                    if metrics and (metrics.get("views_at_k") or summary.get("total_views")):
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
                            "views_10": get_views(10),
                            "views_20": get_views(20),
                            "views_50": get_views(50),
                            "misinfo_10": get_misinfo(10),
                            "misinfo_20": get_misinfo(20),
                            "misinfo_50": get_misinfo(50),
                            "ndcg_10": metrics.get("ndcg_scores", {}).get("ndcg_10", 0),
                            "weighted_exposure": metrics.get("weighted_misinfo_exposure", 0),
                            "duration_seconds": data.get("task_completion", {}).get("duration_seconds"),
                        }
                        results.append(result)
            except Exception as e:
                print(f"Error loading {results_file}: {e}")

    df = pd.DataFrame(results)
    print(f"Successfully loaded {len(df)} experiments with recommendation metrics")
    if successful_only and skipped_count > 0:
        print(f"  (Skipped {skipped_count} experiments with failed tickets)")
    return df


def compute_ex_post_frontier(test_data: pd.DataFrame, K: int = 50) -> pd.DataFrame:
    """
    Compute ex-post frontier (oracle with perfect knowledge of actual views).

    For each k = 0, 1, ..., min(K, n1):
        - Take top k misinfo posts (by actual views)
        - Take top (K-k) non-misinfo posts (by actual views)
        - Compute total views and misinfo rate

    Only return Pareto-optimal points (where views increase with k).

    Args:
        test_data: DataFrame with columns ['views', 'misinformation']
        K: Number of top posts to consider

    Returns:
        DataFrame with columns ['k', 'views', 'misinfo_rate', 'safety_score']
    """
    misinfo_posts = test_data[test_data["misinformation"]].sort_values("views", ascending=False).reset_index(drop=True)
    non_misinfo_posts = (
        test_data[~test_data["misinformation"]].sort_values("views", ascending=False).reset_index(drop=True)
    )

    n1 = len(misinfo_posts)
    n2 = len(non_misinfo_posts)

    misinfo_views = misinfo_posts["views"].values
    non_misinfo_views = non_misinfo_posts["views"].values

    frontier = []
    max_views_so_far = -1

    for k in range(0, min(K, n1) + 1):
        n_non_misinfo = K - k

        if n_non_misinfo > n2:
            continue

        views_misinfo = misinfo_views[:k].sum() if k > 0 else 0
        views_non_misinfo = non_misinfo_views[:n_non_misinfo].sum() if n_non_misinfo > 0 else 0
        total_views = views_misinfo + views_non_misinfo

        misinfo_rate = k / K

        # Only keep if Pareto-improving (views increased)
        if total_views > max_views_so_far:
            frontier.append(
                {"k": k, "views": total_views, "misinfo_rate": misinfo_rate, "safety_score": 1 - misinfo_rate}
            )
            max_views_so_far = total_views

    return pd.DataFrame(frontier)


def compute_ex_ante_frontier(
    test_data: pd.DataFrame, K: int = 50, n_samples: int = 3000, seed: int = 42
) -> pd.DataFrame:
    """
    Compute ex-ante frontier (perfect classifier, random selection within class).

    For each k (number of misinfo to include):
        - Randomly sample k from misinfo pool
        - Randomly sample (K-k) from non-misinfo pool
        - Sum views
        - Repeat n_samples times
        - Compute percentiles

    Args:
        test_data: DataFrame with columns ['views', 'misinformation']
        K: Number of top posts to consider
        n_samples: Number of Monte Carlo samples
        seed: Random seed

    Returns:
        DataFrame with columns ['k', 'misinfo_rate', 'safety_score', 'views_mean', 'views_p10', 'views_p25', 'views_p50', 'views_p75', 'views_p90']
    """
    np.random.seed(seed)

    misinfo_posts = test_data[test_data["misinformation"]]
    non_misinfo_posts = test_data[~test_data["misinformation"]]

    n1 = len(misinfo_posts)
    n2 = len(non_misinfo_posts)

    misinfo_views = misinfo_posts["views"].values
    non_misinfo_views = non_misinfo_posts["views"].values

    # Range of k
    k_min = max(0, K - n2)
    k_max = min(K, n1)

    results = []

    for k in range(k_min, k_max + 1):
        n_non_misinfo = K - k

        views_samples = []
        for _ in range(n_samples):
            if k > 0:
                idx_misinfo = np.random.choice(n1, size=k, replace=False)
                v_misinfo = misinfo_views[idx_misinfo].sum()
            else:
                v_misinfo = 0

            if n_non_misinfo > 0:
                idx_non_misinfo = np.random.choice(n2, size=n_non_misinfo, replace=False)
                v_non_misinfo = non_misinfo_views[idx_non_misinfo].sum()
            else:
                v_non_misinfo = 0

            views_samples.append(v_misinfo + v_non_misinfo)

        views_samples = np.array(views_samples)
        misinfo_rate = k / K

        results.append(
            {
                "k": k,
                "misinfo_rate": misinfo_rate,
                "safety_score": 1 - misinfo_rate,
                "views_mean": np.mean(views_samples),
                "views_p10": np.percentile(views_samples, 10),
                "views_p25": np.percentile(views_samples, 25),
                "views_p50": np.percentile(views_samples, 50),
                "views_p75": np.percentile(views_samples, 75),
                "views_p90": np.percentile(views_samples, 90),
            }
        )

    return pd.DataFrame(results)


def identify_pareto_frontier(
    x_values: np.ndarray, y_values: np.ndarray, maximize_x: bool = True, maximize_y: bool = True
) -> np.ndarray:
    """
    Identify points on the Pareto frontier.

    Args:
        x_values: Views@K values (want to maximize)
        y_values: Inverted Misinfo@K values (want to maximize, since we inverted)
        maximize_x: Whether to maximize x (True for views)
        maximize_y: Whether to maximize y (True for inverted misinformation)

    Returns:
        Boolean array indicating which points are on the Pareto frontier
    """
    x = np.array(x_values)
    y = np.array(y_values)

    pareto_points = np.ones(len(x), dtype=bool)

    for i in range(len(x)):
        for j in range(len(x)):
            if i != j:
                # We want high views and high inverted misinfo (low actual misinfo)
                if x[j] >= x[i] and y[j] >= y[i] and (x[j] > x[i] or y[j] > y[i]):
                    pareto_points[i] = False
                    break

    return pareto_points


def plot_pareto_combined(
    data_by_n: dict[int, pd.DataFrame],
    k_value: int,
    save_path: Path,
    show_labels: bool = False,
    ex_post: pd.DataFrame = None,
    ex_ante: pd.DataFrame = None,
) -> None:
    """Plot combined Pareto frontier with all n values for a specific K."""
    fig, ax = plt.subplots(figsize=(15, 8))
    ax.set_facecolor("#eeeeee")

    views_col = f"views_{k_value}"
    misinfo_col = f"misinfo_{k_value}"
    markers = ["o", "^", "s", "D", "v", "p", "h"]

    stats_lines = [r"$\bf{Pareto\ Frontier\ Statistics}$"]

    # Plot baselines first (so they appear behind experiment points)
    if ex_post is not None:
        ax.plot(
            ex_post["views"], ex_post["safety_score"], "k-", linewidth=2, label="Ex-post frontier (oracle)", zorder=3
        )
        ax.scatter(ex_post["views"], ex_post["safety_score"], c="black", s=50, zorder=4)

    if ex_ante is not None:
        ax.plot(
            ex_ante["views_p50"],
            ex_ante["safety_score"],
            "g-",
            linewidth=2,
            label="Ex-ante frontier (median)",
            zorder=3,
        )
        ax.scatter(ex_ante["views_p50"], ex_ante["safety_score"], c="green", s=30, zorder=4)

        # 25-75 percentile band
        ax.fill_betweenx(
            ex_ante["safety_score"],
            ex_ante["views_p25"],
            ex_ante["views_p75"],
            alpha=0.15,
            color="green",
            label="Ex-ante 25-75%",
            zorder=1,
        )

        # 10th and 90th percentile lines
        ax.plot(
            ex_ante["views_p10"],
            ex_ante["safety_score"],
            "g:",
            linewidth=1,
            alpha=0.6,
            label="Ex-ante 10th %",
            zorder=2,
        )
        ax.plot(
            ex_ante["views_p90"],
            ex_ante["safety_score"],
            "g--",
            linewidth=1,
            alpha=0.6,
            label="Ex-ante 90th %",
            zorder=2,
        )

    for idx, (n, df) in enumerate(sorted(data_by_n.items())):
        if df.empty or views_col not in df.columns:
            continue

        df_filtered = df[df[views_col] > 0]
        if df_filtered.empty:
            continue

        x = df_filtered[views_col].values
        y = 1 - df_filtered[misinfo_col].values  # Invert misinfo so higher is better

        color = get_color_for_n(n)
        marker = markers[idx % len(markers)]
        label = f"{n} Agent{'s' if n > 1 else ''}"

        # Identify Pareto frontier
        pareto = identify_pareto_frontier(x, y, maximize_x=True, maximize_y=True)

        # Plot non-Pareto points
        ax.scatter(x[~pareto], y[~pareto], alpha=0.6, s=100, label=label, color=color, marker=marker, zorder=5)

        # Highlight Pareto frontier points
        ax.scatter(
            x[pareto],
            y[pareto],
            alpha=1.0,
            s=150,
            label=f"{label} (Pareto)",
            color=color,
            marker=marker,
            edgecolors="gold",
            linewidth=2,
            zorder=6,
        )

        # Connect Pareto frontier points
        if np.sum(pareto) > 1:
            pareto_x = x[pareto]
            pareto_y = y[pareto]
            sort_idx = np.argsort(pareto_x)
            ax.plot(pareto_x[sort_idx], pareto_y[sort_idx], "--", color=color, alpha=0.3, linewidth=1, zorder=5)

        # Stats
        pareto_count = np.sum(pareto)
        stats_lines.append(f"{n} Agent{'s' if n > 1 else ''}: {pareto_count} of {len(df_filtered)} points")

    # Labels and title
    ax.set_xlabel(f"Views@{k_value}", fontsize=13, fontweight="bold")
    ax.set_ylabel(f"Misinformation@{k_value} (Inverse)", fontsize=13, fontweight="bold")
    ax.set_title(
        f"News Recommendation - Pareto Frontier (K={k_value}, All Configurations)",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )

    # Format axes
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.1%}"))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.2, linestyle="--", linewidth=0.5)

    # Legend
    ax.legend(
        bbox_to_anchor=(1.05, 0.95), loc="upper left", fontsize=10, framealpha=0.95, edgecolor="gray", fancybox=True
    )

    # Stats box
    stats_text = "\n".join(stats_lines)
    ax.text(
        1.05,
        0.5,
        stats_text,
        transform=ax.transAxes,
        fontsize=9,
        verticalalignment="center",
        horizontalalignment="left",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor="gray", alpha=0.95, linewidth=1),
    )

    plt.tight_layout(rect=[0, 0, 0.85, 1])
    plt.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"Saved combined plot: {save_path}")


def plot_pareto_1_vs_n(
    df_1: pd.DataFrame,
    df_n: pd.DataFrame,
    n: int,
    k_value: int,
    save_path: Path,
    ex_post: pd.DataFrame = None,
    ex_ante: pd.DataFrame = None,
) -> None:
    """Plot 1-agent vs n-agent Pareto frontier comparison for a specific K."""
    fig, ax = plt.subplots(figsize=(15, 8))
    ax.set_facecolor("#eeeeee")

    views_col = f"views_{k_value}"
    misinfo_col = f"misinfo_{k_value}"
    stats_lines = [r"$\bf{Pareto\ Frontier\ Statistics}$"]

    # Plot baselines first (so they appear behind experiment points)
    if ex_post is not None:
        ax.plot(
            ex_post["views"], ex_post["safety_score"], "k-", linewidth=2, label="Ex-post frontier (oracle)", zorder=3
        )
        ax.scatter(ex_post["views"], ex_post["safety_score"], c="black", s=50, zorder=4)

    if ex_ante is not None:
        ax.plot(
            ex_ante["views_p50"],
            ex_ante["safety_score"],
            "g-",
            linewidth=2,
            label="Ex-ante frontier (median)",
            zorder=3,
        )
        ax.scatter(ex_ante["views_p50"], ex_ante["safety_score"], c="green", s=30, zorder=4)

        # 25-75 percentile band
        ax.fill_betweenx(
            ex_ante["safety_score"],
            ex_ante["views_p25"],
            ex_ante["views_p75"],
            alpha=0.15,
            color="green",
            label="Ex-ante 25-75%",
            zorder=1,
        )

        # 10th and 90th percentile lines
        ax.plot(
            ex_ante["views_p10"],
            ex_ante["safety_score"],
            "g:",
            linewidth=1,
            alpha=0.6,
            label="Ex-ante 10th %",
            zorder=2,
        )
        ax.plot(
            ex_ante["views_p90"],
            ex_ante["safety_score"],
            "g--",
            linewidth=1,
            alpha=0.6,
            label="Ex-ante 90th %",
            zorder=2,
        )

    # Plot 1-agent
    if not df_1.empty and views_col in df_1.columns:
        df_1_filtered = df_1[df_1[views_col] > 0]

        if not df_1_filtered.empty:
            x_1 = df_1_filtered[views_col].values
            y_1 = 1 - df_1_filtered[misinfo_col].values

            pareto_1 = identify_pareto_frontier(x_1, y_1, maximize_x=True, maximize_y=True)

            ax.scatter(
                x_1[~pareto_1], y_1[~pareto_1], alpha=0.6, s=100, label="1 Agent", color="#4A90E2", marker="o", zorder=5
            )
            ax.scatter(
                x_1[pareto_1],
                y_1[pareto_1],
                alpha=1.0,
                s=150,
                label="1 Agent (Pareto)",
                color="#4A90E2",
                marker="o",
                edgecolors="gold",
                linewidth=2,
                zorder=6,
            )

            if np.sum(pareto_1) > 1:
                pareto_x = x_1[pareto_1]
                pareto_y = y_1[pareto_1]
                sort_idx = np.argsort(pareto_x)
                ax.plot(pareto_x[sort_idx], pareto_y[sort_idx], "b--", alpha=0.3, linewidth=1, zorder=5)

            stats_lines.append(f"1 Agent: {np.sum(pareto_1)} of {len(df_1_filtered)} points")

    # Plot n-agent
    if not df_n.empty and views_col in df_n.columns:
        df_n_filtered = df_n[df_n[views_col] > 0]

        if not df_n_filtered.empty:
            x_n = df_n_filtered[views_col].values
            y_n = 1 - df_n_filtered[misinfo_col].values

            pareto_n = identify_pareto_frontier(x_n, y_n, maximize_x=True, maximize_y=True)

            ax.scatter(
                x_n[~pareto_n],
                y_n[~pareto_n],
                alpha=0.6,
                s=100,
                label=f"{n} Agents",
                color="#E25C5C",
                marker="^",
                zorder=5,
            )
            ax.scatter(
                x_n[pareto_n],
                y_n[pareto_n],
                alpha=1.0,
                s=150,
                label=f"{n} Agents (Pareto)",
                color="#E25C5C",
                marker="^",
                edgecolors="gold",
                linewidth=2,
                zorder=6,
            )

            if np.sum(pareto_n) > 1:
                pareto_x = x_n[pareto_n]
                pareto_y = y_n[pareto_n]
                sort_idx = np.argsort(pareto_x)
                ax.plot(pareto_x[sort_idx], pareto_y[sort_idx], "r--", alpha=0.3, linewidth=1, zorder=5)

            stats_lines.append(f"{n} Agents: {np.sum(pareto_n)} of {len(df_n_filtered)} points")

    # Labels and title
    ax.set_xlabel(f"Views@{k_value}", fontsize=13, fontweight="bold")
    ax.set_ylabel(f"Misinformation@{k_value} (Inverse)", fontsize=13, fontweight="bold")
    ax.set_title(f"News Recommendation - 1 Agent vs {n} Agents (K={k_value})", fontsize=14, fontweight="bold", pad=15)

    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.1%}"))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.2, linestyle="--", linewidth=0.5)

    ax.legend(
        bbox_to_anchor=(1.05, 0.95), loc="upper left", fontsize=10, framealpha=0.95, edgecolor="gray", fancybox=True
    )

    stats_text = "\n".join(stats_lines)
    ax.text(
        1.05,
        0.5,
        stats_text,
        transform=ax.transAxes,
        fontsize=9,
        verticalalignment="center",
        horizontalalignment="left",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor="gray", alpha=0.95, linewidth=1),
    )

    plt.tight_layout(rect=[0, 0, 0.85, 1])
    plt.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"Saved 1-vs-{n} plot: {save_path}")


def create_overview_plot(
    data_by_n: dict[int, pd.DataFrame],
    save_path: Path,
    ex_post_by_k: dict[int, pd.DataFrame] = None,
    ex_ante_by_k: dict[int, pd.DataFrame] = None,
) -> None:
    """Create a 1x3 grid showing different K values with all n configurations."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    k_values = [10, 20, 50]
    markers = ["o", "^", "s", "D", "v", "p", "h"]

    for k_idx, k in enumerate(k_values):
        ax = axes[k_idx]
        ax.set_facecolor("#eeeeee")

        views_col = f"views_{k}"
        misinfo_col = f"misinfo_{k}"

        # Plot baselines first (if provided for this k value)
        if ex_post_by_k and k in ex_post_by_k:
            ex_post = ex_post_by_k[k]
            ax.plot(ex_post["views"], ex_post["safety_score"], "k-", linewidth=1.5, alpha=0.7, zorder=3)

        if ex_ante_by_k and k in ex_ante_by_k:
            ex_ante = ex_ante_by_k[k]
            ax.plot(ex_ante["views_p50"], ex_ante["safety_score"], "g-", linewidth=1.5, alpha=0.7, zorder=3)
            ax.fill_betweenx(
                ex_ante["safety_score"], ex_ante["views_p25"], ex_ante["views_p75"], alpha=0.1, color="green", zorder=1
            )

        for n_idx, (n, df) in enumerate(sorted(data_by_n.items())):
            if df.empty or views_col not in df.columns:
                continue

            df_filtered = df[df[views_col] > 0]
            if df_filtered.empty:
                continue

            x = df_filtered[views_col].values
            y = 1 - df_filtered[misinfo_col].values

            color = get_color_for_n(n)
            marker = markers[n_idx % len(markers)]
            pareto = identify_pareto_frontier(x, y, True, True)

            ax.scatter(x[~pareto], y[~pareto], alpha=0.5, s=50, color=color, marker=marker, zorder=5)
            ax.scatter(
                x[pareto],
                y[pareto],
                alpha=1.0,
                s=80,
                color=color,
                marker=marker,
                edgecolors="gold",
                linewidth=1.5,
                zorder=6,
            )

        ax.set_xlabel(f"Views@{k}", fontsize=10)
        ax.set_ylabel(f"Misinformation@{k} (Inverse)", fontsize=10)
        ax.set_title(f"K = {k}", fontsize=11, fontweight="bold")
        ax.grid(True, alpha=0.2, linestyle="--", linewidth=0.5)
        ax.set_ylim(0, 1.02)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.1%}"))
        ax.xaxis.set_major_formatter(
            plt.FuncFormatter(lambda x, _: f"{x / 1000:.0f}K" if x < 1000000 else f"{x / 1000000:.1f}M")
        )

    # Add legend
    from matplotlib.patches import Patch

    legend_elements = []
    for n in sorted(data_by_n.keys()):
        color = get_color_for_n(n)
        label = f"{n} Agent{'s' if n > 1 else ''}"
        legend_elements.append(Patch(facecolor=color, alpha=0.6, label=label))

    fig.legend(
        handles=legend_elements,
        loc="upper center",
        ncol=len(data_by_n),
        fontsize=10,
        bbox_to_anchor=(0.5, 0.98),
        frameon=True,
        fancybox=True,
        shadow=False,
    )

    plt.suptitle("News Recommendation - Pareto Frontier Overview", fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved overview plot: {save_path}")


def main():
    parser = argparse.ArgumentParser(description="Plot Pareto frontiers for recommendation system experiments")
    parser.add_argument(
        "--results-dir",
        type=str,
        required=True,
        help="Path to results directory containing {n}_agent_experiments folders",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None, help="Directory to save plots (default: same as results-dir)"
    )
    parser.add_argument("--show-labels", action="store_true", help="Show experiment labels on points")
    parser.add_argument(
        "--successful-only", action="store_true", help="Only include experiments where all tickets succeeded"
    )
    parser.add_argument(
        "--k-values", type=int, nargs="+", default=[10, 20, 50], help="K values to plot (default: 10 20 50)"
    )
    parser.add_argument(
        "--exclude-partial",
        type=int,
        nargs="?",
        const=50,  # default threshold if flag used without value
        default=None,
        help="Exclude experiments with fewer than N items. If N not specified, uses 50.",
    )
    parser.add_argument(
        "--baselines", action="store_true", help="Overlay ex-ante and ex-post baseline frontiers on plots"
    )

    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir) if args.output_dir else results_dir

    if not results_dir.exists():
        print(f"Error: Results directory not found: {results_dir}")
        return 1

    # Discover agent directories
    agent_dirs = discover_agent_directories(results_dir)

    if not agent_dirs:
        print(f"Error: No *_agent_experiments directories found in {results_dir}")
        return 1

    print(f"Found {len(agent_dirs)} agent configurations: {list(agent_dirs.keys())}")

    # Load data for each n (unfiltered for CSV output)
    data_by_n: dict[int, pd.DataFrame] = {}
    for n, dir_path in agent_dirs.items():
        print(f"\nLoading {n}-agent experiments from {dir_path}...")
        df = load_experiment_results_from_dir(dir_path, args.successful_only)
        if not df.empty:
            data_by_n[n] = df

    if not data_by_n:
        print("Error: No valid experiment data found")
        return 1

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract model name from results_dir path
    model_name = results_dir.name

    # Apply --exclude-partial filter before saving CSVs and plotting
    if args.exclude_partial is not None:
        print(f"\nFiltering: Excluding experiments with fewer than {args.exclude_partial} items")
        filtered_data_by_n: dict[int, pd.DataFrame] = {}
        for n, df in data_by_n.items():
            if "total_items" in df.columns:
                before = len(df)
                df_filtered = df[df["total_items"] >= args.exclude_partial]
                if before - len(df_filtered) > 0:
                    print(f"  {n}-agent: Excluded {before - len(df_filtered)} experiments")
                if not df_filtered.empty:
                    filtered_data_by_n[n] = df_filtered
            else:
                filtered_data_by_n[n] = df
        data_by_n = filtered_data_by_n

    # Save CSVs for each n (after filtering if --exclude-partial was used)
    for n, df in data_by_n.items():
        # Add model and n columns after the first column (experiment)
        df_csv = df.copy()
        df_csv.insert(1, "model", model_name)
        df_csv.insert(2, "n_agents", n)
        csv_path = output_dir / f"{n}_agent_metrics.csv"
        df_csv.to_csv(csv_path, index=False)
        print(f"Saved {n}-agent metrics to: {csv_path}")

    # Compute baseline frontiers if requested
    ex_post_by_k = {}
    ex_ante_by_k = {}
    if args.baselines:
        # Path to test data relative to this script
        script_dir = Path(__file__).parent
        test_data_path = script_dir / "../../../data/fake_news/test.csv"

        if not test_data_path.exists():
            print(f"\nWarning: Test data not found at {test_data_path}")
            print("Skipping baseline computation. Plots will be generated without baselines.")
        else:
            print(f"\nLoading test data from {test_data_path}...")
            test_data = pd.read_csv(test_data_path)
            print(f"  Test data: {len(test_data)} articles")
            print(f"    Misinfo: {test_data['misinformation'].sum()}")
            print(f"    Non-misinfo: {(~test_data['misinformation']).sum()}")

            print("\nComputing baseline frontiers...")
            for k in args.k_values:
                print(f"  Computing frontiers for K={k}...")
                ex_post_by_k[k] = compute_ex_post_frontier(test_data, K=k)
                ex_ante_by_k[k] = compute_ex_ante_frontier(test_data, K=k, n_samples=3000)
            print("  Done.")

    # Generate combined plots for each K value
    for k in args.k_values:
        combined_path = output_dir / f"pareto_combined_k{k}.png"
        print(f"\nGenerating combined K={k} plot...")
        ex_post = ex_post_by_k.get(k) if args.baselines else None
        ex_ante = ex_ante_by_k.get(k) if args.baselines else None
        plot_pareto_combined(data_by_n, k, combined_path, args.show_labels, ex_post, ex_ante)

    # Generate 1-vs-n plots for each n != 1 (using K=50 as primary)
    if 1 in data_by_n:
        df_1 = data_by_n[1]
        for n, df_n in data_by_n.items():
            if n != 1:
                save_path = output_dir / f"pareto_1_vs_{n}_k50.png"
                print(f"Generating 1-vs-{n} plot...")
                ex_post = ex_post_by_k.get(50) if args.baselines else None
                ex_ante = ex_ante_by_k.get(50) if args.baselines else None
                plot_pareto_1_vs_n(df_1, df_n, n, 50, save_path, ex_post, ex_ante)

    # Create overview plot
    overview_path = output_dir / "pareto_overview.png"
    print("\nGenerating overview plot...")
    ex_post_overview = ex_post_by_k if args.baselines else None
    ex_ante_overview = ex_ante_by_k if args.baselines else None
    create_overview_plot(data_by_n, overview_path, ex_post_overview, ex_ante_overview)

    print(f"\nAll plots saved to: {output_dir}")
    return 0


if __name__ == "__main__":
    exit(main())
