#!/usr/bin/env python3
"""
Plot Pareto frontier for sepsis ICU v2 experiments.
Average patient cost vs missed sepsis cases (percentage).

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


def load_experiment_results_from_dir(
    exp_dir: Path, successful_only: bool = False, validate_metrics: bool = True
) -> pd.DataFrame:
    """Load all experiment results from a directory containing experiment subdirectories.

    Args:
        exp_dir: Directory containing experiment subdirectories
        successful_only: If True, only include experiments where all tickets succeeded
        validate_metrics: If True, only include experiments where num_treated + num_discharged = total_patients
    """
    results = []

    # Find all experiment directories
    # Updated patterns for sepsis_icu_v2
    patterns = [
        r"\d{8}_sepsis_\d+",  # Main sepsis pattern (20260106_sepsis_171956)
        r"\d{8}$",  # Basic date pattern (20250909)
        r"\d{8}_dev_\d+",  # Dev experiments (20250909_dev_1)
        r"\d{8}_sepsis",  # Legacy sepsis pattern (if any)
        r"\d{8}_dev",  # Legacy dev pattern (if any)
    ]

    exp_subdirs = []
    for pattern in patterns:
        matching_dirs = [d for d in exp_dir.iterdir() if d.is_dir() and re.match(pattern, d.name)]

        # For each matching directory, check if it contains experiment_results.json directly
        # or if it contains nested experiment directories
        for dir in matching_dirs:
            results_file = dir / "experiment_results.json"
            if results_file.exists():
                exp_subdirs.append(dir)
            else:
                # Check for nested experiment directories (e.g., multi-agent structure)
                nested_patterns = [
                    r"\d{8}_sepsis_\d+",  # Nested sepsis experiments (20250909_sepsis_1)
                    r"\d{8}_dev_\d+",  # Nested dev experiments
                ]
                for nested_pattern in nested_patterns:
                    nested_dirs = [d for d in dir.iterdir() if d.is_dir() and re.match(nested_pattern, d.name)]
                    exp_subdirs.extend(nested_dirs)

    # Remove duplicates while preserving order
    seen = set()
    exp_subdirs = [d for d in exp_subdirs if not (d in seen or seen.add(d))]

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

                    # Get avg_cost_per_patient from cost_metrics (note: key is 'average_cost_per_patient')
                    avg_cost = cost_metrics.get("average_cost_per_patient", 0)
                    total_patients = cost_metrics.get("num_patients", 0)

                    # Only add if we have the required metrics
                    if avg_cost > 0:
                        # Validate metrics if requested
                        if validate_metrics:
                            num_treated = decision_stats.get("num_patients_treated", 0)
                            num_discharged = decision_stats.get("num_patients_discharged", 0)

                            # Check if treated + discharged = total
                            if total_patients > 0 and (num_treated + num_discharged) != total_patients:
                                print(
                                    f"  Skipping {subdir.name}: inconsistent metrics (treated={num_treated} + discharged={num_discharged} != total={total_patients})"
                                )
                                skipped_count += 1
                                continue

                        # Get missed sepsis rate from sepsis_metrics (percentage of sepsis cases NOT treated)
                        missed_sepsis_rate = 0
                        if "missed_sepsis_rate" in sepsis_metrics:
                            # Convert percentage to fraction (0-1)
                            missed_sepsis_rate = sepsis_metrics["missed_sepsis_rate"] / 100.0
                        elif "missed_sepsis_cases" in sepsis_metrics and "total_sepsis_patients" in sepsis_metrics:
                            total_sepsis = sepsis_metrics["total_sepsis_patients"]
                            missed_sepsis = sepsis_metrics["missed_sepsis_cases"]
                            if total_sepsis > 0:
                                missed_sepsis_rate = missed_sepsis / total_sepsis

                        result = {
                            "experiment": subdir.name,
                            "avg_cost_per_patient": avg_cost,
                            "missed_sepsis_rate": missed_sepsis_rate,
                            "treatment_rate": decision_stats.get("treatment_rate", 0),
                            "total_patients": total_patients,
                            "total_sepsis_patients": sepsis_metrics.get("total_sepsis_patients", 0),
                            "treated_sepsis_patients": sepsis_metrics.get("treated_sepsis_patients", 0),
                            "sensitivity": sepsis_metrics.get("sensitivity", 0),
                            "specificity": sepsis_metrics.get("specificity", 0),
                            "precision": sepsis_metrics.get("precision", 0),
                            "discharge_rate": decision_stats.get("discharge_rate", 0),
                            "num_patients_treated": decision_stats.get("num_patients_treated", 0),
                            "num_patients_discharged": decision_stats.get("num_patients_discharged", 0),
                            "duration_seconds": data.get("task_completion", {}).get("duration_seconds"),
                        }
                        results.append(result)
            except Exception as e:
                print(f"Error loading {results_file}: {e}")

    df = pd.DataFrame(results)
    print(f"Successfully loaded {len(df)} experiments with sepsis metrics")
    if skipped_count > 0:
        skip_reasons = []
        if successful_only:
            skip_reasons.append("failed tickets")
        if validate_metrics:
            skip_reasons.append("inconsistent metrics")
        print(f"  (Skipped {skipped_count} experiments due to: {', '.join(skip_reasons)})")
    return df


# Cost parameters
COST_DISCHARGE = 500
COST_TREATMENT = 4000


def compute_perfect_classifier_frontier(n_total: int, n_sepsis: int) -> pd.DataFrame:
    """
    Compute perfect classifier frontier.

    Perfect classifier knows exactly who has sepsis.
    Strategy: Treat k sepsis patients (0 to n_sepsis), discharge all non-sepsis.

    This is the theoretical best - you never over-treat non-sepsis patients.

    Args:
        n_total: Total number of patients
        n_sepsis: Number of patients with sepsis

    Returns:
        DataFrame with columns ['k', 'avg_cost', 'missed_sepsis_rate', 'sensitivity', 'treatment_rate']
    """
    frontier = []
    for k in range(0, n_sepsis + 1):
        # Treat k sepsis patients, discharge (n_sepsis - k) sepsis + all non_sepsis
        n_treated = k
        n_discharged = n_total - k

        total_cost = n_treated * COST_TREATMENT + n_discharged * COST_DISCHARGE
        avg_cost = total_cost / n_total

        missed_sepsis = n_sepsis - k
        missed_rate = missed_sepsis / n_sepsis if n_sepsis > 0 else 0

        frontier.append(
            {
                "k": k,
                "avg_cost": avg_cost,
                "missed_sepsis_rate": missed_rate,
                "sensitivity": 1 - missed_rate,
                "treatment_rate": k / n_total,
            }
        )

    return pd.DataFrame(frontier)


def compute_empirical_random_baseline(
    test_data: pd.DataFrame, n_simulations: int = 300, n_points: int = 101
) -> pd.DataFrame:
    """
    Compute empirical random baseline by simulating random treatment.

    For each treatment rate p (0% to 100%), we:
    1. Randomly select p% of patients to treat
    2. Compute actual cost and missed sepsis rate
    3. Repeat n_simulations times
    4. Return median, 25th, and 75th percentiles

    Args:
        test_data: DataFrame with 'sepsis_label' column
        n_simulations: Number of random samples per treatment rate
        n_points: Number of treatment rate points (0 to 100)

    Returns:
        DataFrame with columns: treatment_rate, avg_cost_{median,p25,p75},
                                missed_sepsis_rate_{median,p25,p75}
    """
    np.random.seed(42)

    n_total = len(test_data)
    sepsis_mask = test_data["sepsis_label"].values.astype(bool)
    n_sepsis = sepsis_mask.sum()

    results = []

    for i in range(n_points):
        p = i / (n_points - 1)
        n_to_treat = int(round(p * n_total))

        costs = []
        missed_rates = []

        for _ in range(n_simulations):
            treat_indices = (
                np.random.choice(n_total, size=n_to_treat, replace=False) if n_to_treat > 0 else np.array([])
            )
            treat_mask = np.zeros(n_total, dtype=bool)
            if len(treat_indices) > 0:
                treat_mask[treat_indices] = True

            n_treated = treat_mask.sum()
            n_discharged = n_total - n_treated
            total_cost = n_treated * COST_TREATMENT + n_discharged * COST_DISCHARGE
            avg_cost = total_cost / n_total

            sepsis_treated = (sepsis_mask & treat_mask).sum()
            sepsis_missed = n_sepsis - sepsis_treated
            missed_rate = sepsis_missed / n_sepsis if n_sepsis > 0 else 0

            costs.append(avg_cost)
            missed_rates.append(missed_rate)

        results.append(
            {
                "treatment_rate": p,
                "avg_cost_median": np.median(costs),
                "avg_cost_p25": np.percentile(costs, 25),
                "avg_cost_p75": np.percentile(costs, 75),
                "missed_sepsis_rate_median": np.median(missed_rates),
                "missed_sepsis_rate_p25": np.percentile(missed_rates, 25),
                "missed_sepsis_rate_p75": np.percentile(missed_rates, 75),
            }
        )

    return pd.DataFrame(results)


def identify_pareto_frontier(
    x_values: np.ndarray, y_values: np.ndarray, maximize_x: bool = False, maximize_y: bool = False
) -> np.ndarray:
    """
    Identify points on the Pareto frontier.

    Args:
        x_values: Average cost per patient (want to minimize)
        y_values: Missed sepsis rate (want to minimize)
        maximize_x: Whether to maximize x (False for cost)
        maximize_y: Whether to maximize y (False for missed rate)

    Returns:
        Boolean array indicating which points are on the Pareto frontier
    """
    x = np.array(x_values)
    y = np.array(y_values)

    pareto_points = np.ones(len(x), dtype=bool)

    for i in range(len(x)):
        for j in range(len(x)):
            if i != j:
                # We want low cost and low missed rate
                if x[j] <= x[i] and y[j] <= y[i] and (x[j] < x[i] or y[j] < y[i]):
                    pareto_points[i] = False
                    break

    return pareto_points


def plot_pareto_combined(
    data_by_n: dict[int, pd.DataFrame],
    save_path: Path,
    show_labels: bool = False,
    perfect_frontier: pd.DataFrame = None,
    random_baseline: pd.DataFrame = None,
) -> None:
    """
    Plot combined Pareto frontier with all n values.
    """
    fig, ax = plt.subplots(figsize=(15, 8))
    ax.set_facecolor("#eeeeee")

    markers = ["o", "^", "s", "D", "v", "p", "h"]

    stats_lines = [r"$\bf{Pareto\ Frontier\ Statistics}$"]

    # Plot baselines first (so they appear behind experiment points)
    if perfect_frontier is not None:
        ax.plot(
            perfect_frontier["avg_cost"],
            perfect_frontier["missed_sepsis_rate"],
            "g-",
            linewidth=2.5,
            label="Perfect classifier (optimal)",
            zorder=3,
        )
        # Add points at key locations
        key_points = perfect_frontier.iloc[::7]
        ax.scatter(key_points["avg_cost"], key_points["missed_sepsis_rate"], c="green", s=40, zorder=4)

    if random_baseline is not None:
        ax.plot(
            random_baseline["avg_cost_median"],
            random_baseline["missed_sepsis_rate_median"],
            "k-",
            linewidth=2,
            label="Random baseline (median)",
            zorder=3,
        )
        ax.scatter(
            random_baseline["avg_cost_median"], random_baseline["missed_sepsis_rate_median"], c="black", s=30, zorder=4
        )

        # 25-75 percentile band (vertical - varying missed rate for each cost)
        ax.fill_between(
            random_baseline["avg_cost_median"],
            random_baseline["missed_sepsis_rate_p25"],
            random_baseline["missed_sepsis_rate_p75"],
            alpha=0.2,
            color="gray",
            label="Random baseline 25-75%",
            zorder=1,
        )

    for idx, (n, df) in enumerate(sorted(data_by_n.items())):
        if df.empty or "avg_cost_per_patient" not in df.columns:
            continue

        df_filtered = df[df["avg_cost_per_patient"] > 0]
        if df_filtered.empty:
            continue

        x = df_filtered["avg_cost_per_patient"].values
        y = df_filtered["missed_sepsis_rate"].values

        color = get_color_for_n(n)
        marker = markers[idx % len(markers)]
        label = f"{n} Agent{'s' if n > 1 else ''}"

        # Identify Pareto frontier
        pareto = identify_pareto_frontier(x, y, maximize_x=False, maximize_y=False)

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
    ax.set_xlabel("Average Cost per Patient ($)", fontsize=13, fontweight="bold")
    ax.set_ylabel("Missed Sepsis Cases (%)", fontsize=13, fontweight="bold")
    ax.set_title(
        "Sepsis ICU v2 Treatment Policy - Pareto Frontier (All Configurations)", fontsize=14, fontweight="bold", pad=15
    )

    # Format axes
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y * 100:.1f}%"))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.set_ylim(-0.02, 1.02)
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
    save_path: Path,
    show_labels: bool = False,
    perfect_frontier: pd.DataFrame = None,
    random_baseline: pd.DataFrame = None,
) -> None:
    """
    Plot 1-agent vs n-agent Pareto frontier comparison.
    """
    fig, ax = plt.subplots(figsize=(15, 8))
    ax.set_facecolor("#eeeeee")

    stats_lines = [r"$\bf{Pareto\ Frontier\ Statistics}$"]

    # Plot baselines first (so they appear behind experiment points)
    if perfect_frontier is not None:
        ax.plot(
            perfect_frontier["avg_cost"],
            perfect_frontier["missed_sepsis_rate"],
            "g-",
            linewidth=2.5,
            label="Perfect classifier (optimal)",
            zorder=3,
        )
        key_points = perfect_frontier.iloc[::7]
        ax.scatter(key_points["avg_cost"], key_points["missed_sepsis_rate"], c="green", s=40, zorder=4)

    if random_baseline is not None:
        ax.plot(
            random_baseline["avg_cost_median"],
            random_baseline["missed_sepsis_rate_median"],
            "k-",
            linewidth=2,
            label="Random baseline (median)",
            zorder=3,
        )
        ax.scatter(
            random_baseline["avg_cost_median"], random_baseline["missed_sepsis_rate_median"], c="black", s=30, zorder=4
        )

        # 25-75 percentile band (vertical - varying missed rate for each cost)
        ax.fill_between(
            random_baseline["avg_cost_median"],
            random_baseline["missed_sepsis_rate_p25"],
            random_baseline["missed_sepsis_rate_p75"],
            alpha=0.2,
            color="gray",
            label="Random baseline 25-75%",
            zorder=1,
        )

    # Plot 1-agent
    if not df_1.empty and "avg_cost_per_patient" in df_1.columns:
        df_1_filtered = df_1[df_1["avg_cost_per_patient"] > 0]

        if not df_1_filtered.empty:
            x_1 = df_1_filtered["avg_cost_per_patient"].values
            y_1 = df_1_filtered["missed_sepsis_rate"].values

            pareto_1 = identify_pareto_frontier(x_1, y_1, maximize_x=False, maximize_y=False)

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
    if not df_n.empty and "avg_cost_per_patient" in df_n.columns:
        df_n_filtered = df_n[df_n["avg_cost_per_patient"] > 0]

        if not df_n_filtered.empty:
            x_n = df_n_filtered["avg_cost_per_patient"].values
            y_n = df_n_filtered["missed_sepsis_rate"].values

            pareto_n = identify_pareto_frontier(x_n, y_n, maximize_x=False, maximize_y=False)

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
    ax.set_xlabel("Average Cost per Patient ($)", fontsize=13, fontweight="bold")
    ax.set_ylabel("Missed Sepsis Cases (%)", fontsize=13, fontweight="bold")
    ax.set_title(f"Sepsis ICU v2 Treatment Policy - 1 Agent vs {n} Agents", fontsize=14, fontweight="bold", pad=15)

    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y * 100:.1f}%"))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.set_ylim(-0.02, 1.02)
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


def main():
    parser = argparse.ArgumentParser(description="Plot Pareto frontiers for sepsis ICU v2 experiments")
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
        "--validate-metrics",
        action="store_true",
        default=True,
        help="Validate that num_treated + num_discharged = total_patients (default: True)",
    )
    parser.add_argument(
        "--no-validate-metrics", dest="validate_metrics", action="store_false", help="Disable metrics validation"
    )
    parser.add_argument(
        "--baselines", action="store_true", help="Overlay perfect classifier and random baseline frontiers on plots"
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

    # Load data for each n
    data_by_n: dict[int, pd.DataFrame] = {}
    for n, dir_path in agent_dirs.items():
        print(f"\nLoading {n}-agent experiments from {dir_path}...")
        df = load_experiment_results_from_dir(dir_path, args.successful_only, args.validate_metrics)
        if not df.empty:
            data_by_n[n] = df

    if not data_by_n:
        print("Error: No valid experiment data found")
        return 1

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract model name from results_dir path
    model_name = results_dir.name

    # Save CSVs for each n
    for n, df in data_by_n.items():
        # Add model and n columns after the first column (experiment)
        df = df.copy()
        df.insert(1, "model", model_name)
        df.insert(2, "n_agents", n)
        csv_path = output_dir / f"{n}_agent_metrics.csv"
        df.to_csv(csv_path, index=False)
        print(f"Saved {n}-agent metrics to: {csv_path}")

        # Print summary
        print(f"\n{n}-agent summary:")
        print(f"  Experiments: {len(df)}")
        print(f"  Avg cost: ${df['avg_cost_per_patient'].mean():,.2f} (±${df['avg_cost_per_patient'].std():,.2f})")
        print(
            f"  Avg missed sepsis rate: {df['missed_sepsis_rate'].mean() * 100:.1f}% (±{df['missed_sepsis_rate'].std() * 100:.1f}%)"
        )

    # Compute baseline frontiers if requested
    perfect_frontier = None
    random_baseline = None
    if args.baselines:
        # Path to test data relative to this script
        script_dir = Path(__file__).parent
        test_data_path = script_dir / "../../../data/sepsis_icu_v2/test.json"

        if not test_data_path.exists():
            print(f"\nWarning: Test data not found at {test_data_path}")
            print("Skipping baseline computation. Plots will be generated without baselines.")
        else:
            print(f"\nLoading test data from {test_data_path}...")
            with open(test_data_path) as f:
                test_data = json.load(f)
            test_df = pd.DataFrame(test_data)

            n_total = len(test_df)
            n_sepsis = test_df["sepsis_label"].sum()
            n_non_sepsis = n_total - n_sepsis

            print(f"  Test data: {n_total} patients")
            print(f"    Sepsis: {n_sepsis} ({n_sepsis / n_total:.1%})")
            print(f"    Non-sepsis: {n_non_sepsis} ({n_non_sepsis / n_total:.1%})")

            print("\nComputing baseline frontiers...")
            perfect_frontier = compute_perfect_classifier_frontier(n_total, n_sepsis)
            random_baseline = compute_empirical_random_baseline(test_df, n_simulations=300, n_points=101)
            print("  Done.")

    # Generate combined plot with all n values
    combined_path = output_dir / "pareto_combined.png"
    print("\nGenerating combined plot...")
    plot_pareto_combined(data_by_n, combined_path, args.show_labels, perfect_frontier, random_baseline)

    # Generate 1-vs-n plots for each n != 1
    if 1 in data_by_n:
        df_1 = data_by_n[1]
        for n, df_n in data_by_n.items():
            if n != 1:
                save_path = output_dir / f"pareto_1_vs_{n}.png"
                print(f"Generating 1-vs-{n} plot...")
                plot_pareto_1_vs_n(df_1, df_n, n, save_path, args.show_labels, perfect_frontier, random_baseline)

    print(f"\nAll plots saved to: {output_dir}")
    return 0


if __name__ == "__main__":
    exit(main())
