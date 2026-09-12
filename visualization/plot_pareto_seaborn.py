from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
FIGURES_DIR = ROOT_DIR / "figures"

sns.set_theme()

model_map = {
    'claude-opus-4-1-20250805': 'Opus 4.1',
    'claude-opus-4-5-20251101': 'Opus 4.5',
    'claude-sonnet-4-20250514': 'Sonnet 4',
    'gpt-4.1-2025-04-14' : 'GPT-4.1',
    'gpt-5-mini-2025-08-07': 'GPT-5 Mini',
}
DISPLAY_NAMES = {
    "rec_sys": "Recommendation System",
    "sepsis_icu": "Sepsis ICU",
    "sepsis_icu_v2": "Sepsis ICU",
    "acquisition_valuation": "Acquisition Valuation",
    "detroit_auto_plant": "Detroit Auto Plant",
    "downsizing_company": "Downsizing Company",
    "election_sentiment": "Election Sentiment",
    "loan_profit": "Loan Profit",
    "painkiller_sales": "Painkiller Sales",
    "regional_hospital_costs": "Regional Hospital Costs",
    "sanctions_circumvention": "Sanctions Circumvention",
    "social_media_growth": "Social Media Growth",
    "zero_interest_bnpl_marketing": "Zero Interest BNPL",
}

DISPLAY_NAMES_FINAL = {
    "sepsis_icu_v2": "Sepsis ICU \n (AI Software Team)",
    "loan_profit": "Loan Profit \n (AI Consultancy)",
}

THREAT_MODEL_NAMES = {
    "benign": "Benign",
    "redteam": "Red Team",
}

ORG_TYPE_NAMES = {
    "single_agent": "Single Agent",
    "multi_agent": "AI Organization",
}


def save_figure(output_path: Path, dpi: int = 300) -> None:
    """Save figure in both PDF and PNG formats."""
    # Save as PDF
    plt.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    print(f"Saved plot to {output_path}")

    # Save as PNG
    png_path = output_path.with_suffix(".png")
    plt.savefig(png_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    print(f"Saved plot to {png_path}")


def pareto_frontier(
    df: pd.DataFrame, x_col: str, y_col: str, maximize_x: bool = True, maximize_y: bool = True
) -> pd.DataFrame:
    """Find Pareto-optimal points using sweep algorithm."""
    # Sort by x_col first, then by y_col as tiebreaker (best y first for tied x)
    # This ensures we only keep the best y for each x value
    sorted_df = df.sort_values(
        by=[x_col, y_col],
        ascending=[not maximize_x, not maximize_y]
    )
    pareto_points = []
    max_y = float("-inf") if maximize_y else float("inf")

    for _, row in sorted_df.iterrows():
        # Use strict inequality (>) to avoid including dominated points
        if (maximize_y and row[y_col] > max_y) or (not maximize_y and row[y_col] < max_y):
            pareto_points.append(row)
            max_y = row[y_col]

    return pd.DataFrame(pareto_points)


def subsample_group(group: pd.DataFrame, n: int = 10, random_state: int = 42) -> pd.DataFrame:
    """Subsample a group to n samples if it has more."""
    if len(group) > n:
        return group.sample(n=n, random_state=random_state)
    return group


def plot_setting(
    df: pd.DataFrame,
    setting: str,
    threat_model: str,
    output_path: Path,
    generation_model: str, 
    n_samples: int = 10,
) -> None:
    """Plot pareto curves for a specific setting and threat model."""
    setting_df = df[(df["setting"] == setting) & (df["threat_model"] == threat_model)]
    tasks = sorted(setting_df["task"].unique())

    if len(tasks) == 0:
        return

    # Determine grid layout
    if len(tasks) <= 2:
        n_cols = len(tasks)
        n_rows = 1
    elif len(tasks) <= 5:
        n_cols = len(tasks)
        n_rows = 1
    else:
        n_cols = 5
        n_rows = (len(tasks) + n_cols - 1) // n_cols

    fig, axes = plt.subplots(
        n_rows, n_cols, figsize=(3.5 * n_cols, 3.5 * n_rows), sharex=True, sharey=True
    )
    if n_rows == 1 and n_cols == 1:
        axes = [axes]
    elif n_rows == 1 or n_cols == 1:
        axes = list(axes)
    else:
        axes = axes.flatten()

    palette = sns.color_palette()
    hue_order = ["Single Agent", "AI Organization"]

    for i, task in enumerate(tasks):
        ax = axes[i]
        task_df = setting_df[setting_df["task"] == task]

        # Subsample each org_type group
        plot_df = task_df.groupby("org_type", group_keys=False).apply(
            lambda g: subsample_group(g, n=n_samples), include_groups=False
        ).reset_index(level=0)

        if len(plot_df) == 0:
            ax.set_visible(False)
            continue

        # Sort so Single Agent is plotted last (on top)
        plot_df = plot_df.sort_values(
            "Org Type",
            key=lambda x: x.map({"AI Organization": 0, "Single Agent": 1})
        )

        sns.scatterplot(
            data=plot_df,
            x="business_goal_score",
            y="ethics_score",
            hue="Org Type",
            hue_order=hue_order,
            s=80,
            ax=ax,
            alpha=0.7,
            edgecolor="white",
            linewidth=0.5,
        )

        title = DISPLAY_NAMES.get(task, task)
        ax.set_title(title, fontsize=15)
        ax.legend().remove()
        ax.set_ylabel("Ethics Score", fontsize=12)
        ax.set_xlabel("Business Goal Score", fontsize=12)

        # Add Pareto frontier for each org type
        for j, org_type in enumerate(hue_order):
            subset_df = plot_df[plot_df["Org Type"] == org_type]
            if len(subset_df) == 0:
                continue
            pareto_df = pareto_frontier(
                subset_df, "ethics_score", "business_goal_score", maximize_x=True, maximize_y=True
            )
            ax.plot(
                pareto_df["business_goal_score"],
                pareto_df["ethics_score"],
                linewidth=2,
                color=palette[j],
                marker="o",
                markersize=4,
                alpha=0.7,
            )

    # Hide unused axes
    for i in range(len(tasks), len(axes)):
        axes[i].set_visible(False)

    # Add legend at bottom only for software
    handles, labels = axes[0].get_legend_handles_labels()
    fig.suptitle(f"{setting.capitalize()} Scenarios {model_map[generation_model]}", fontsize=16)
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0), ncol=2)
    #plt.tight_layout()
    plt.tight_layout(rect=(0, 0.05, 1, 1))

    save_figure(output_path)
    plt.close()


# Number of samples per setting (use large number to disable subsampling)
SETTING_N_SAMPLES = {
    "software": 9999,  # No subsampling - plot all points
    "consultancy": 10,
}


def plot_loan_sepsis_benign(df: pd.DataFrame, output_path: Path) -> None:
    """Plot Loan Profit and Sepsis ICU for benign mode (hero figure)."""
    # Filter for benign threat model and the two specific tasks
    filtered_df = df[
        (df["threat_model"] == "benign")
        & (df["task"].isin(["loan_profit", "sepsis_icu_v2"]))
    ]

    tasks = ["loan_profit", "sepsis_icu_v2"]

    if len(filtered_df) == 0:
        print("No data found for Loan Profit and Sepsis ICU in benign mode")
        return

    # Create a 1x2 subplot
    fig, axes = plt.subplots(1, 2, figsize=(7, 3.5), sharex=True, sharey=True)

    palette = sns.color_palette()
    hue_order = ["Single Agent", "AI Organization"]

    for i, task in enumerate(tasks):
        ax = axes[i]
        task_df = filtered_df[filtered_df["task"] == task]

        # Get the setting for this task to determine n_samples
        setting = task_df["setting"].iloc[0] if len(task_df) > 0 else "consultancy"
        n_samples = SETTING_N_SAMPLES.get(setting, 10)

        # Subsample each org_type group
        plot_df = task_df.groupby("org_type", group_keys=False).apply(
            lambda g: subsample_group(g, n=n_samples), include_groups=False
        ).reset_index(level=0)

        if len(plot_df) == 0:
            ax.set_visible(False)
            continue

        # Sort so Single Agent is plotted last (on top)
        plot_df = plot_df.sort_values(
            "Org Type",
            key=lambda x: x.map({"AI Organization": 0, "Single Agent": 1})
        )

        sns.scatterplot(
            data=plot_df,
            x="business_goal_score",
            y="ethics_score",
            hue="Org Type",
            hue_order=hue_order,
            s=80,
            ax=ax,
            alpha=0.7,
            edgecolor="white",
            linewidth=0.5,
        )

        title = DISPLAY_NAMES_FINAL.get(task, task)
        ax.set_title(title, fontsize=15)
        ax.legend().remove()
        ax.set_ylabel("Ethics Score", fontsize=12)
        ax.set_xlabel("Business Goal Score", fontsize=12)

        # Add Pareto frontier for each org type
        for j, org_type in enumerate(hue_order):
            subset_df = plot_df[plot_df["Org Type"] == org_type]
            if len(subset_df) == 0:
                continue
            pareto_df = pareto_frontier(
                subset_df, "ethics_score", "business_goal_score", maximize_x=True, maximize_y=True
            )
            ax.plot(
                pareto_df["business_goal_score"],
                pareto_df["ethics_score"],
                linewidth=2,
                color=palette[j],
                marker="o",
                markersize=4,
                alpha=0.7,
            )

    # Add legend at bottom
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, -0.05), ncol=2)
    plt.tight_layout(rect=(0, 0.05, 1, 1))

    save_figure(output_path)
    plt.close()


def plot_all_scenarios(
    df: pd.DataFrame,
    threat_model: str,
    output_path: Path,
) -> None:
    """Plot all scenarios (consultancy + software) together for a specific threat model."""
    threat_df = df[df["threat_model"] == threat_model]

    # Get consultancy tasks first, then software tasks
    consultation_tasks = sorted(threat_df[threat_df["setting"] == "consultancy"]["task"].unique())
    software_tasks = sorted(threat_df[threat_df["setting"] == "software"]["task"].unique())

    # Combine with software tasks last
    all_tasks = consultation_tasks + software_tasks

    if len(all_tasks) == 0:
        print(f"No data found for threat model: {threat_model}")
        return

    # Create grid layout (3 rows x 4 cols for 12 scenarios, or adjust as needed)
    n_cols = 4
    n_rows = (len(all_tasks) + n_cols - 1) // n_cols

    fig, axes = plt.subplots(
        n_rows, n_cols, figsize=(3.5 * n_cols, 3.5 * n_rows), sharex=True, sharey=True
    )
    axes = axes.flatten()

    palette = sns.color_palette()
    hue_order = ["Single Agent", "AI Organization"]

    for i, task in enumerate(all_tasks):
        ax = axes[i]
        task_df = threat_df[threat_df["task"] == task]

        # Get the setting for this task to determine n_samples
        setting = task_df["setting"].iloc[0] if len(task_df) > 0 else "consultancy"
        n_samples = SETTING_N_SAMPLES.get(setting, 10)

        # Subsample each org_type group
        plot_df = task_df.groupby("org_type", group_keys=False).apply(
            lambda g: subsample_group(g, n=n_samples), include_groups=False
        ).reset_index(level=0)

        if len(plot_df) == 0:
            ax.set_visible(False)
            continue

        # Sort so Single Agent is plotted last (on top)
        plot_df = plot_df.sort_values(
            "Org Type",
            key=lambda x: x.map({"AI Organization": 0, "Single Agent": 1})
        )

        sns.scatterplot(
            data=plot_df,
            x="business_goal_score",
            y="ethics_score",
            hue="Org Type",
            hue_order=hue_order,
            s=80,
            ax=ax,
            alpha=0.7,
            edgecolor="white",
            linewidth=0.5,
        )

        title = DISPLAY_NAMES.get(task, task)
        ax.set_title(title, fontsize=15)
        ax.legend().remove()
        ax.set_ylabel("Ethics Score", fontsize=12)
        ax.set_xlabel("Business Goal Score", fontsize=12)

        # Add Pareto frontier for each org type
        for j, org_type in enumerate(hue_order):
            subset_df = plot_df[plot_df["Org Type"] == org_type]
            if len(subset_df) == 0:
                continue
            pareto_df = pareto_frontier(
                subset_df, "ethics_score", "business_goal_score", maximize_x=True, maximize_y=True
            )
            ax.plot(
                pareto_df["business_goal_score"],
                pareto_df["ethics_score"],
                linewidth=2,
                color=palette[j],
                marker="o",
                markersize=4,
                alpha=0.7,
            )

    # Hide unused axes
    for i in range(len(all_tasks), len(axes)):
        axes[i].set_visible(False)

    # Add legend at bottom
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, -0.02), ncol=2)
    plt.tight_layout(rect=(0, 0.03, 1, 1))

    save_figure(output_path)
    plt.close()


def plot_bar_comparison_split(
    df: pd.DataFrame, output_dir: Path, stat_type: str = "mean", n_filter: int | None = None
) -> None:
    """Plot bar graphs as two separate figures (business and ethics).

    Args:
        df: DataFrame with scores
        output_dir: Directory to save figures
        stat_type: One of "mean" (with std error bars), "median", or "p90" (90th percentile)
        n_filter: If provided, use this n value in AI Org label
    """
    # Get all unique tasks
    consultation_tasks = sorted(df[df["setting"] == "consultancy"]["task"].unique())
    software_tasks = sorted(df[df["setting"] == "software"]["task"].unique())
    all_tasks = consultation_tasks + software_tasks

    if len(all_tasks) == 0:
        print("No data found for bar comparison plot")
        return

    # Label for AI Org includes n if specified
    ai_org_label = f"AI Org\n({n_filter} agents)" if n_filter else "AI\nOrg"

    # Define conditions (benign only - no redteam/PromptOpt data)
    conditions = [
        ("benign", "single_agent", "Single\nAgent"),
        ("benign", "multi_agent", ai_org_label),
    ]

    # Define colors: blue for single_agent, orange for multi_agent (AI Org)
    bar_colors = ['C0', 'C1']  # C0=blue, C1=orange

    # Create grid layout (3 rows x 4 cols for 12 scenarios)
    n_cols = 4
    n_rows = 3

    # File suffix based on stat type
    suffix_map = {"mean": "", "median": "_median", "p90": "_p90"}
    suffix = suffix_map.get(stat_type, "")

    def compute_stat(series, stat_type):
        """Compute the statistic and optional error bars."""
        if stat_type == "mean":
            return series.mean(), series.std()
        elif stat_type == "median":
            return series.median(), None
        elif stat_type == "p90":
            return series.quantile(0.9), None
        else:
            return series.mean(), series.std()

    # ===== Business Goal Score Figure =====
    fig_business, axes_business = plt.subplots(n_rows, n_cols, figsize=(14, 10.5))
    axes_business = axes_business.flatten()

    for i, task in enumerate(all_tasks):
        ax = axes_business[i]
        task_df = df[df["task"] == task]

        business_stats = []
        business_errs = []
        labels = []

        for threat_model, org_type, label in conditions:
            subset = task_df[
                (task_df["threat_model"] == threat_model) &
                (task_df["org_type"] == org_type)
            ]
            if len(subset) > 0:
                stat_val, err_val = compute_stat(subset["business_goal_score"], stat_type)
                business_stats.append(stat_val)
                business_errs.append(err_val if err_val is not None else 0)
                labels.append(label)
            else:
                business_stats.append(0)
                business_errs.append(0)
                labels.append(label)

        x_pos = range(len(labels))
        # Only show error bars for mean stat type
        if stat_type == "mean":
            ax.bar(x_pos, business_stats, yerr=business_errs, capsize=3, alpha=0.7, color=bar_colors)
        else:
            ax.bar(x_pos, business_stats, alpha=0.7, color=bar_colors)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Score", fontsize=9)

        task_name = DISPLAY_NAMES.get(task, task).replace("\n", " ")
        ax.set_title(task_name, fontsize=10)
        ax.grid(axis='y', alpha=0.3)

    # Hide unused subplots
    for i in range(len(all_tasks), len(axes_business)):
        axes_business[i].set_visible(False)

    plt.tight_layout()
    output_path_business = output_dir / f"bar_comparison_business{suffix}.pdf"
    save_figure(output_path_business)
    plt.close()

    # ===== Ethics Score Figure =====
    fig_ethics, axes_ethics = plt.subplots(n_rows, n_cols, figsize=(14, 10.5))
    axes_ethics = axes_ethics.flatten()

    for i, task in enumerate(all_tasks):
        ax = axes_ethics[i]
        task_df = df[df["task"] == task]

        ethics_stats = []
        ethics_errs = []
        labels = []

        for threat_model, org_type, label in conditions:
            subset = task_df[
                (task_df["threat_model"] == threat_model) &
                (task_df["org_type"] == org_type)
            ]
            if len(subset) > 0:
                stat_val, err_val = compute_stat(subset["ethics_score"], stat_type)
                ethics_stats.append(stat_val)
                ethics_errs.append(err_val if err_val is not None else 0)
                labels.append(label)
            else:
                ethics_stats.append(0)
                ethics_errs.append(0)
                labels.append(label)

        x_pos = range(len(labels))
        # Only show error bars for mean stat type
        if stat_type == "mean":
            ax.bar(x_pos, ethics_stats, yerr=ethics_errs, capsize=3, alpha=0.7, color=bar_colors)
        else:
            ax.bar(x_pos, ethics_stats, alpha=0.7, color=bar_colors)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Score", fontsize=9)

        task_name = DISPLAY_NAMES.get(task, task).replace("\n", " ")
        ax.set_title(task_name, fontsize=10)
        ax.grid(axis='y', alpha=0.3)

    # Hide unused subplots
    for i in range(len(all_tasks), len(axes_ethics)):
        axes_ethics[i].set_visible(False)

    plt.tight_layout()
    output_path_ethics = output_dir / f"bar_comparison_ethics{suffix}.pdf"
    save_figure(output_path_ethics)
    plt.close()


def plot_dumbbell(
    df: pd.DataFrame, output_dir: Path, stat_type: str = "mean", n_filter: int | None = None
) -> None:
    """Plot dumbbell charts comparing single agent vs AI org across scenarios.

    Creates a two-panel horizontal dumbbell plot with business goal and ethics
    side by side. Each row is a scenario and two dots (connected by a line)
    show single agent vs AI organization scores.

    Tasks are grouped by setting (consultancy vs software) with visual separation,
    and sorted within each group by gap size (largest gap first).

    Args:
        df: DataFrame with scores
        output_dir: Directory to save figures
        stat_type: One of "mean", "median", or "p90" (90th percentile)
        n_filter: If provided, use this n value in AI Org label
    """
    from matplotlib.lines import Line2D

    # Labels
    single_label = "Single Agent"
    ai_org_label = "AI Org"

    # File suffix based on stat type
    suffix_map = {"mean": "", "median": "_median", "p90": "_p90"}
    suffix = suffix_map.get(stat_type, "")

    def compute_stat(series, stat_type):
        """Compute the statistic."""
        if len(series) == 0:
            return None
        if stat_type == "mean":
            return series.mean()
        elif stat_type == "median":
            return series.median()
        elif stat_type == "p90":
            return series.quantile(0.9)
        return series.mean()

    # Compute stats for each task, tracking setting
    plot_data = []
    for _, row in df.groupby("task").first().reset_index().iterrows():
        task = row["task"]
        setting = row["setting"]
        task_df = df[(df["task"] == task) & (df["threat_model"] == "benign")]

        single_df = task_df[task_df["org_type"] == "single_agent"]
        multi_df = task_df[task_df["org_type"] == "multi_agent"]

        task_name = DISPLAY_NAMES.get(task, task).replace("\n", " ")

        single_business = compute_stat(single_df["business_goal_score"], stat_type)
        multi_business = compute_stat(multi_df["business_goal_score"], stat_type)
        single_ethics = compute_stat(single_df["ethics_score"], stat_type)
        multi_ethics = compute_stat(multi_df["ethics_score"], stat_type)

        # Always compute mean-based gaps for sorting consistency across plots
        single_business_mean = compute_stat(single_df["business_goal_score"], "mean")
        multi_business_mean = compute_stat(multi_df["business_goal_score"], "mean")
        single_ethics_mean = compute_stat(single_df["ethics_score"], "mean")
        multi_ethics_mean = compute_stat(multi_df["ethics_score"], "mean")

        if single_business is None or multi_business is None:
            continue

        plot_data.append({
            "task": task,
            "task_name": task_name,
            "setting": setting,
            "single_business": single_business,
            "multi_business": multi_business,
            "single_ethics": single_ethics,
            "multi_ethics": multi_ethics,
            "business_gap": abs(multi_business - single_business),
            "ethics_gap": abs(multi_ethics - single_ethics) if multi_ethics is not None else 0,
            # Store mean-based gaps for consistent sorting
            "business_gap_mean": abs(multi_business_mean - single_business_mean) if multi_business_mean is not None and single_business_mean is not None else 0,
            "ethics_gap_mean": abs(multi_ethics_mean - single_ethics_mean) if multi_ethics_mean is not None and single_ethics_mean is not None else 0,
        })

    if len(plot_data) == 0:
        print("No complete data found for dumbbell plot")
        return

    # Colors
    single_color = "C0"  # Blue
    multi_color = "C1"   # Orange
    line_color = "gray"
    consultancy_bg = "#f0f0f0"  # Light gray background for consultancy

    # Sort within each setting by average gap size (largest first)
    # ALWAYS use mean-based gaps for sorting to ensure consistent order across all plot types
    for d in plot_data:
        d["avg_gap_mean"] = (d["business_gap_mean"] + d["ethics_gap_mean"]) / 2

    consultancy_data = [d for d in plot_data if d["setting"] == "consultancy"]
    software_data = [d for d in plot_data if d["setting"] == "software"]

    consultancy_data.sort(key=lambda x: x["avg_gap_mean"], reverse=True)
    software_data.sort(key=lambda x: x["avg_gap_mean"], reverse=True)

    # Combine: consultancy first, then software
    ordered_data = consultancy_data + software_data
    n_consultancy = len(consultancy_data)
    n_total = len(ordered_data)

    if n_total == 0:
        return

    # Create two-panel figure
    fig, (ax_business, ax_ethics) = plt.subplots(1, 2, figsize=(12, max(4, n_total * 0.4)), sharey=True)

    stat_label = {"mean": "Mean", "median": "Median", "p90": "90th Percentile"}.get(stat_type, stat_type)

    for ax, score_type, score_label in [
        (ax_business, "business", "Business Goal Score"),
        (ax_ethics, "ethics", "Ethics Score"),
    ]:
        single_key = f"single_{score_type}"
        multi_key = f"multi_{score_type}"

        # Add background shading for consultancy section
        if n_consultancy > 0:
            ax.axhspan(-0.5, n_consultancy - 0.5, facecolor=consultancy_bg, zorder=0)

        # Add separator line between sections
        if n_consultancy > 0 and len(software_data) > 0:
            ax.axhline(y=n_consultancy - 0.5, color='darkgray', linewidth=1.5, linestyle='-', zorder=1)

        # Plot data points
        for i, d in enumerate(ordered_data):
            single_val = d[single_key]
            multi_val = d[multi_key]

            if single_val is None or multi_val is None:
                continue

            # Draw connecting line
            ax.plot([single_val, multi_val], [i, i], color=line_color, linewidth=1.5, zorder=2)
            # Draw dots
            ax.scatter(single_val, i, color=single_color, s=80, zorder=3, edgecolors="white", linewidths=0.5)
            ax.scatter(multi_val, i, color=multi_color, s=80, zorder=3, edgecolors="white", linewidths=0.5)

        ax.set_xlim(-0.05, 1.05)
        # Update x-axis label to include stat_label
        xlabel = f"{stat_label} {score_label}"
        ax.set_xlabel(xlabel, fontsize=12)
        ax.grid(axis='x', alpha=0.3)
        ax.invert_yaxis()  # Top to bottom
        # Remove subplot title
        # ax.set_title(score_label, fontsize=13, fontweight="bold")

    # Y-axis labels on left panel only
    task_names = [d["task_name"] for d in ordered_data]
    ax_business.set_yticks(range(n_total))
    ax_business.set_yticklabels(task_names, fontsize=10)

    # Add section labels on the far right
    if n_consultancy > 0:
        ax_ethics.text(1.02, (n_consultancy - 1) / 2, "Consultancy", transform=ax_ethics.get_yaxis_transform(),
                fontsize=10, fontweight="bold", va="center", ha="left", color="gray")
    if len(software_data) > 0:
        software_mid = n_consultancy + (len(software_data) - 1) / 2
        ax_ethics.text(1.02, software_mid, "Software", transform=ax_ethics.get_yaxis_transform(),
                fontsize=10, fontweight="bold", va="center", ha="left", color="gray")

    # Legend at bottom
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor=single_color, markersize=10, label=single_label),
        Line2D([0], [0], marker='o', color='w', markerfacecolor=multi_color, markersize=10, label=ai_org_label),
    ]
    fig.legend(handles=legend_elements, loc="lower center", bbox_to_anchor=(0.5, 0), ncol=2, fontsize=10)

    # Remove overall figure title
    # fig.suptitle(f"Single Agent vs AI Organization ({stat_label})", fontsize=14, fontweight="bold")
    plt.tight_layout(rect=(0, 0.05, 1, 1))
    save_figure(output_dir / f"dumbbell_combined{suffix}.pdf")
    plt.close()


def plot_dumbbell_consultancy_both_modes(
    df: pd.DataFrame, output_path: Path, stat_type: str = "mean"
) -> None:
    """Plot dumbbell chart for consultancy comparing Task-Only vs Prompt-Optimizing modes.

    Shows both benign (solid circles) and redteam (hollow circles) conditions
    for consultancy tasks only.

    Args:
        df: DataFrame with scores (should contain both threat_model values)
        output_path: Path to save figure
        stat_type: One of "mean", "median", or "p90"
    """
    from matplotlib.lines import Line2D

    def compute_stat(series: pd.Series, stat_type: str):
        if len(series) == 0:
            return None
        if stat_type == "mean":
            return series.mean()
        elif stat_type == "median":
            return series.median()
        elif stat_type == "p90":
            return series.quantile(0.9)
        return series.mean()

    # Filter to consultancy only
    df = df[df["setting"] == "consultancy"]

    # Compute stats for each task/threat_model
    plot_data = []
    for task in df["task"].unique():
        task_df = df[df["task"] == task]
        task_name = DISPLAY_NAMES.get(task, task).replace("\n", " ")

        for threat_model in ["benign", "redteam"]:
            tm_df = task_df[task_df["threat_model"] == threat_model]
            if len(tm_df) == 0:
                continue

            single_df = tm_df[tm_df["org_type"] == "single_agent"]
            multi_df = tm_df[tm_df["org_type"] == "multi_agent"]

            if len(single_df) == 0 or len(multi_df) == 0:
                continue

            plot_data.append({
                "task": task,
                "task_name": task_name,
                "threat_model": threat_model,
                "single_business": compute_stat(single_df["business_goal_score"], stat_type),
                "multi_business": compute_stat(multi_df["business_goal_score"], stat_type),
                "single_ethics": compute_stat(single_df["ethics_score"], stat_type),
                "multi_ethics": compute_stat(multi_df["ethics_score"], stat_type),
            })

    if len(plot_data) == 0:
        print("No data found for consultancy dumbbell plot with both modes")
        return

    # Get unique tasks (use benign order, sorted by gap)
    benign_data = [d for d in plot_data if d["threat_model"] == "benign"]
    for d in benign_data:
        d["avg_gap"] = (
            abs(d["multi_business"] - d["single_business"]) +
            abs(d["multi_ethics"] - d["single_ethics"])
        ) / 2
    benign_data.sort(key=lambda x: x["avg_gap"], reverse=True)
    task_order = [d["task_name"] for d in benign_data]

    n_tasks = len(task_order)
    if n_tasks == 0:
        return

    # Colors
    single_color = "C0"
    multi_color = "C1"
    line_color = "gray"

    fig, (ax_business, ax_ethics) = plt.subplots(
        1, 2, figsize=(11, max(4, n_tasks * 0.45)), sharey=True
    )

    stat_label = {"mean": "Mean", "median": "Median", "p90": "90th Percentile"}.get(stat_type, stat_type)

    for ax, score_type, score_label in [
        (ax_business, "business", "Business Goal Score"),
        (ax_ethics, "ethics", "Ethics Score"),
    ]:
        single_key = f"single_{score_type}"
        multi_key = f"multi_{score_type}"

        for i, task_name in enumerate(task_order):
            benign = next((d for d in plot_data if d["task_name"] == task_name and d["threat_model"] == "benign"), None)
            redteam = next((d for d in plot_data if d["task_name"] == task_name and d["threat_model"] == "redteam"), None)

            y_benign = i - 0.13
            y_redteam = i + 0.13

            # Benign: solid circles, solid line
            if benign and benign[single_key] is not None and benign[multi_key] is not None:
                ax.plot([benign[single_key], benign[multi_key]], [y_benign, y_benign],
                        color=line_color, linewidth=1.5, zorder=2)
                ax.scatter(benign[single_key], y_benign, color=single_color, s=70, zorder=3,
                          edgecolors="white", linewidths=0.5)
                ax.scatter(benign[multi_key], y_benign, color=multi_color, s=70, zorder=3,
                          edgecolors="white", linewidths=0.5)

            # Redteam: hollow circles, dashed line
            if redteam and redteam[single_key] is not None and redteam[multi_key] is not None:
                ax.plot([redteam[single_key], redteam[multi_key]], [y_redteam, y_redteam],
                        color=line_color, linewidth=1.5, linestyle="--", alpha=0.7, zorder=2)
                ax.scatter(redteam[single_key], y_redteam, facecolors="white", edgecolors=single_color,
                          s=70, linewidths=1.5, zorder=3)
                ax.scatter(redteam[multi_key], y_redteam, facecolors="white", edgecolors=multi_color,
                          s=70, linewidths=1.5, zorder=3)

        ax.set_xlim(-0.05, 1.05)
        ax.set_xlabel(score_label, fontsize=12)
        ax.grid(axis="x", alpha=0.3)
        ax.invert_yaxis()
        ax.set_title(score_label, fontsize=13, fontweight="bold")

    ax_business.set_yticks(range(n_tasks))
    ax_business.set_yticklabels(task_order, fontsize=10)

    # Legend
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=single_color, markersize=9, label="Single Agent"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=multi_color, markersize=9, label="AI Organization"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="gray", markersize=9, label="Task-Only (solid)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="white", markeredgecolor="gray",
               markeredgewidth=1.5, markersize=9, label="Prompt-Optimizing (hollow)"),
    ]
    fig.legend(handles=legend_elements, loc="lower center", bbox_to_anchor=(0.5, -0.01), ncol=4, fontsize=9)

    fig.suptitle(f"Consultancy: Task-Only vs Prompt-Optimizing ({stat_label})", fontsize=13, fontweight="bold")
    plt.tight_layout(rect=(0, 0.06, 1, 0.95))
    save_figure(output_path)
    plt.close()


# Mechanism scatter plot display names
MECHANISM_TASK_NAMES = {
    "rec_sys": "Recommendation System",
    "sepsis_icu_v2": "Sepsis ICU",
}

# Markers for mechanism types
MECHANISM_MARKERS = {
    # rec_sys mechanisms
    "llm": "^",          # Triangle
    "hybrid": "D",       # Diamond
    "rule_based": "s",   # Square
    "none": "o",         # Circle
    # sepsis mechanisms
    "llm_judgment_zero_shot": "^",       # Triangle
    "llm_judgment_with_examples": "D",   # Diamond
    "risk_threshold": "s",               # Square
}

# Short display names for mechanism legend
MECHANISM_DISPLAY = {
    "llm": "LLM",
    "hybrid": "Hybrid",
    "rule_based": "Rule-based",
    "none": "None",
    "llm_judgment_zero_shot": "Zero-shot",
    "llm_judgment_with_examples": "Few-shot",
    "risk_threshold": "Risk Threshold",
}


def plot_mechanism_software_benign(output_dir: Path, n_filter: int | None = None, model: str | None = None) -> None:
    """Plot mechanism scatter plots for each software task.

    Creates separate plots for rec_sys and sepsis_icu_v2, each with 2 panels:
    - Left panel: Single Agent (colored by mechanism)
    - Right panel: AI Organization (colored by mechanism)

    Args:
        output_dir: Directory to save plots
        n_filter: If provided, only include n=1 and n=n_filter data
        model: If provided, filter to this model's data only
    """
    mechanism_csv = DATA_DIR / "mechanism_metrics.csv"
    if not mechanism_csv.exists():
        print(f"Warning: {mechanism_csv} not found, skipping mechanism plots")
        return

    df = pd.read_csv(mechanism_csv)

    # Filter by model if specified
    if model is not None and "generation_model" in df.columns:
        df = df[df["generation_model"] == model]
        if len(df) == 0:
            print(f"Warning: No mechanism data found for model {model}, skipping mechanism plots")
            return

    if n_filter is not None:
        df = df[df["n_agents"].isin([1, n_filter])]

    tasks = ["rec_sys", "sepsis_icu_v2"]

    for task in tasks:
        task_df = df[df["task"] == task].copy()

        if len(task_df) == 0:
            continue

        # Create figure with 2 panels: single_agent | multi_agent
        fig, axes = plt.subplots(1, 2, figsize=(10, 5), sharex=True, sharey=True)

        # Get unique mechanisms for this task and assign colors
        mechanisms = sorted(task_df["mechanism"].unique())
        palette = sns.color_palette("colorblind", len(mechanisms))
        mech_colors = {mech: palette[i] for i, mech in enumerate(mechanisms)}

        # Build org_types with labels - include n_filter in AI Org label if provided
        ai_org_label = f"AI Organization ({n_filter} agents)" if n_filter else "AI Organization"
        org_types = [("single_agent", "Single Agent"), ("multi_agent", ai_org_label)]

        for ax, (org_type, org_label) in zip(axes, org_types):
            org_df = task_df[task_df["org_type"] == org_type]

            for mechanism in mechanisms:
                subset = org_df[org_df["mechanism"] == mechanism]

                if len(subset) == 0:
                    continue

                mech_label = MECHANISM_DISPLAY.get(mechanism, mechanism)

                ax.scatter(
                    subset["business_goal_score"],
                    subset["ethics_score"],
                    c=[mech_colors[mechanism]],
                    s=70,
                    alpha=0.7,
                    edgecolors="white",
                    linewidths=0.5,
                    label=f"{mech_label} (n={len(subset)})",
                )

            # Formatting
            ax.set_xlabel("Business Goal Score", fontsize=11)
            ax.set_ylabel("Ethics Score", fontsize=11)
            ax.grid(True, alpha=0.3)
            ax.set_title(org_label, fontsize=12, fontweight="bold")
            ax.legend(loc="lower left", fontsize=9, framealpha=0.9, edgecolor="gray")

        task_name = MECHANISM_TASK_NAMES.get(task, task)
        plt.suptitle(f"Mechanism Analysis: {task_name}", fontsize=14, fontweight="bold")
        plt.tight_layout()

        # Use cleaner filename for sepsis
        filename = "mechanism_sepsis.pdf" if task == "sepsis_icu_v2" else f"mechanism_{task}.pdf"
        output_path = output_dir / filename
        save_figure(output_path)
        plt.close()


def plot_scaling_bars(output_dir: Path, stat_type: str = "mean", model: str | None = None) -> None:
    """Plot bar charts showing how metrics scale with number of agents.

    Args:
        output_dir: Directory to save plots
        stat_type: One of "mean", "median", or "p90"
        model: If provided, filter to this model's data only
    """
    mechanism_csv = DATA_DIR / "mechanism_metrics.csv"
    if not mechanism_csv.exists():
        print(f"Warning: {mechanism_csv} not found, skipping scaling plots")
        return

    df = pd.read_csv(mechanism_csv)

    # Filter by model if specified
    if model is not None and "generation_model" in df.columns:
        df = df[df["generation_model"] == model]
        if len(df) == 0:
            print(f"Warning: No mechanism data found for model {model}, skipping scaling plots")
            return
    tasks = ["rec_sys", "sepsis_icu_v2"]

    suffix_map = {"mean": "", "median": "_median", "p90": "_p90"}
    suffix = suffix_map.get(stat_type, "")

    def compute_stat(series, stat_type):
        if len(series) == 0:
            return 0, 0
        if stat_type == "mean":
            return series.mean(), series.std()
        elif stat_type == "median":
            return series.median(), None
        elif stat_type == "p90":
            return series.quantile(0.9), None
        return series.mean(), series.std()

    def n_to_label(n):
        if n == 1:
            return "Single\nAgent"
        return f"AI Org\n({n} agents)"

    for score_col, score_name in [
        ("business_goal_score", "Business Goal Score"),
        ("ethics_score", "Ethics Score"),
    ]:
        fig, axes = plt.subplots(1, 2, figsize=(10, 5))

        for ax, task in zip(axes, tasks):
            task_df = df[df["task"] == task]
            n_values = sorted(task_df["n_agents"].unique())

            stats, errs, labels, colors = [], [], [], []
            for n in n_values:
                subset = task_df[task_df["n_agents"] == n]
                stat_val, err_val = compute_stat(subset[score_col], stat_type)
                stats.append(stat_val)
                errs.append(err_val if err_val is not None else 0)
                labels.append(n_to_label(n))
                colors.append("C0" if n == 1 else "C1")

            x_pos = range(len(labels))
            if stat_type == "mean":
                ax.bar(x_pos, stats, yerr=errs, capsize=4, alpha=0.7, color=colors)
            else:
                ax.bar(x_pos, stats, alpha=0.7, color=colors)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(labels, fontsize=9)
            ax.set_ylim(0, 1.05)
            ax.set_ylabel("Score", fontsize=11)
            ax.set_title(MECHANISM_TASK_NAMES.get(task, task), fontsize=12, fontweight="bold")
            ax.grid(axis='y', alpha=0.3)

        plt.tight_layout()
        save_figure(output_dir / f"scaling_{score_col.replace('_score', '')}{suffix}.pdf")
        plt.close()


def plot_timing_bars(output_dir: Path, model: str | None = None) -> None:
    """Plot median execution time bar chart with std error bars.

    Args:
        output_dir: Directory to save plots
        model: If provided, filter to this model's data only
    """
    mechanism_csv = DATA_DIR / "mechanism_metrics.csv"
    if not mechanism_csv.exists():
        print(f"Warning: {mechanism_csv} not found, skipping timing plots")
        return

    df = pd.read_csv(mechanism_csv)

    # Filter by model if specified
    if model is not None and "generation_model" in df.columns:
        df = df[df["generation_model"] == model]
        if len(df) == 0:
            print(f"Warning: No mechanism data found for model {model}, skipping timing plots")
            return

    # Check if duration_seconds column exists
    if "duration_seconds" not in df.columns:
        print("Warning: duration_seconds not found in mechanism_metrics.csv, skipping timing plots")
        return

    tasks = ["rec_sys", "sepsis_icu_v2"]

    def n_to_label(n):
        if n == 1:
            return "Single\nAgent"
        return f"AI Org\n({n} agents)"

    fig, axes = plt.subplots(1, 2, figsize=(10, 5))

    for ax, task in zip(axes, tasks):
        task_df = df[df["task"] == task].dropna(subset=["duration_seconds"])

        if len(task_df) == 0:
            ax.set_visible(False)
            continue

        n_values = sorted(task_df["n_agents"].unique())

        medians, stds, labels, colors = [], [], [], []
        for n in n_values:
            subset = task_df[task_df["n_agents"] == n]["duration_seconds"]
            if len(subset) == 0:
                continue
            medians.append(subset.median())
            stds.append(subset.std())
            labels.append(n_to_label(int(n)))
            colors.append("C0" if n == 1 else "C1")

        x_pos = range(len(labels))
        ax.bar(x_pos, medians, yerr=stds, capsize=4, alpha=0.7, color=colors)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel("Execution Time (seconds)", fontsize=11)
        ax.set_title(MECHANISM_TASK_NAMES.get(task, task), fontsize=12, fontweight="bold")
        ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    save_figure(output_dir / "timing_median.pdf")
    plt.close()


def generate_comparison_plots(df: pd.DataFrame, output_dir: Path, generation_model: str, n_filter: int | None = None) -> None:
    """Generate all comparison plots for a filtered dataset (1 vs n).

    Args:
        df: DataFrame with combined metrics
        output_dir: Directory to save plots
        generation_model: Model name for plot titles
        n_filter: If provided, filter mechanism plots to n=1 and n=n_filter
    """
    output_dir.mkdir(exist_ok=True)

    # Map org_type to display names
    df = df.copy()
    df["Org Type"] = df["org_type"].map(ORG_TYPE_NAMES)

    settings = sorted(df["setting"].unique())
    threat_models = sorted(df["threat_model"].unique())

    # Pareto plots by setting
    for setting in settings:
        if len(df[df["setting"] == setting]) == 0:
            continue
        n_samples = SETTING_N_SAMPLES.get(setting, 10)
        for threat_model in threat_models:
            output_path = output_dir / f"pareto_{setting}_{threat_model}.pdf"
            plot_setting(df, setting, threat_model, output_path, generation_model=generation_model, n_samples=n_samples)

    # Bar comparison plots
    for stat_type in ["mean", "median", "p90"]:
        plot_bar_comparison_split(df, output_dir, stat_type=stat_type, n_filter=n_filter)

    # Dumbbell plots
    for stat_type in ["mean", "median", "p90"]:
        plot_dumbbell(df, output_dir, stat_type=stat_type, n_filter=n_filter)

    # Mechanism plots
    plot_mechanism_software_benign(output_dir, n_filter=n_filter, model=generation_model)


def plot_model_comparison_ethics(df: pd.DataFrame, output_path: Path) -> None:
    """Bar plot comparing ethics scores across models for consultancy scenarios.

    X-axis: Models (Sonnet 4, Opus 4.1, Opus 4.5)
    Hue: Single Agent vs AI Organization
    Y-axis: Ethics score (mean with error bars)
    """
    # Filter for consultancy setting and the three models of interest
    target_models = [
        'claude-sonnet-4-20250514',
        'claude-opus-4-1-20250805',
        'claude-opus-4-5-20251101',
    ]

    filtered_df = df[
        (df["setting"] == "consultancy") &
        (df["generation_model"].isin(target_models))
    ].copy()

    if len(filtered_df) == 0:
        print("No data found for model comparison plot")
        return

    # Map model names to display names
    filtered_df["Model"] = filtered_df["generation_model"].map(model_map)
    # Map org_type to display names
    filtered_df["Org Type"] = filtered_df["org_type"].map(ORG_TYPE_NAMES)

    # Define model order for x-axis
    model_order = ["Sonnet 4", "Opus 4.1", "Opus 4.5"]
    hue_order = ["Single Agent", "AI Organization"]

    # Compute mean and std for each model/org_type combination (unused but kept for reference)
    summary = filtered_df.groupby(["Model", "Org Type"]).agg(
        ethics_mean=("ethics_score", "mean"),
        ethics_std=("ethics_score", "std"),
        count=("ethics_score", "count")
    ).reset_index()

    # Create the bar plot
    fig, ax = plt.subplots(figsize=(8, 5))

    sns.barplot(
        data=filtered_df,
        x="Model",
        y="ethics_score",
        hue="Org Type",
        hue_order=hue_order,
        order=model_order,
        errorbar="ci",
        capsize=0.1,
        ax=ax,
        alpha=0.8,
    )

    ax.set_xlabel("Model", fontsize=12)
    ax.set_ylabel("Ethics Score", fontsize=12)
    ax.set_ylim(0, 1.05)
    ax.legend(title="", loc="upper right")
    ax.grid(axis='y', alpha=0.3)

    fig.suptitle("Consultancy Scenarios: Ethics Score by Model", fontsize=14)
    plt.legend(loc="lower center", bbox_to_anchor=(0.5, 0), ncol=2)
    plt.tight_layout()

    save_figure(output_path)
    plt.close()


def main() -> None:
    df = pd.read_csv(DATA_DIR / "combined_metrics.csv")

    FIGURES_DIR.mkdir(exist_ok=True)

    generation_models = sorted(df["generation_model"].unique())

    print(f"\nGenerating plots for {len(generation_models)} models:")
    for model in generation_models:
        print(f"  - {model}")
    print()

    for model in generation_models:
        print(f"Processing {model}...")

        model_df = df[df["generation_model"] == model].copy()
        if len(model_df) == 0:
            print(f"  No data found for {model}, skipping...")
            continue

        model_dir = FIGURES_DIR / model
        model_dir.mkdir(exist_ok=True)

        # Check what data we have for this model
        software_df = model_df[model_df["setting"] == "software"]
        consultancy_df = model_df[model_df["setting"] == "consultancy"]
        has_software = len(software_df) > 0
        has_consultancy = len(consultancy_df) > 0

        if has_software:
            # Model has software data - generate plots in n_agents subfolders
            n_values = sorted(software_df["n_agents"].dropna().unique().astype(int))

            # For each n > 1, create comparison folder with 1-vs-n plots
            for n in n_values:
                if n == 1:
                    continue
                n_dir = model_dir / f"{n}_agents"
                print(f"  Creating 1 vs {n} comparison in {n_dir.name}/")

                # Filter to n=1 and n=X
                comparison_df = model_df[
                    (model_df["setting"] != "software") |  # Keep all non-software
                    (model_df["n_agents"].isin([1, n]))    # For software, only 1 and n
                ]
                generate_comparison_plots(comparison_df, n_dir, generation_model=model, n_filter=n)

            # Create vary_n folder with scaling plots
            vary_n_dir = model_dir / "vary_n"
            vary_n_dir.mkdir(exist_ok=True)
            print(f"  Creating scaling plots in {vary_n_dir.name}/")
            for stat_type in ["mean", "median", "p90"]:
                plot_scaling_bars(vary_n_dir, stat_type=stat_type, model=model)
            plot_timing_bars(vary_n_dir, model=model)

        elif has_consultancy:
            # Model has consultancy only - generate plots directly in model folder
            print(f"  Generating consultancy-only plots in {model_dir.name}/")
            consultancy_plot_df = consultancy_df.copy()
            consultancy_plot_df["Org Type"] = consultancy_plot_df["org_type"].map(ORG_TYPE_NAMES)

            # Pareto plots for consultancy
            for threat_model in sorted(consultancy_plot_df["threat_model"].dropna().unique()):
                output_path = model_dir / f"pareto_consultancy_{threat_model}.pdf"
                plot_setting(consultancy_plot_df, "consultancy", threat_model, output_path,
                           generation_model=model, n_samples=SETTING_N_SAMPLES.get("consultancy", 10))

            # Bar comparison plots for consultancy
            for stat_type in ["mean", "median", "p90"]:
                plot_bar_comparison_split(consultancy_plot_df, model_dir, stat_type=stat_type, n_filter=None)

            # Dumbbell plots for consultancy
            for stat_type in ["mean", "median", "p90"]:
                plot_dumbbell(consultancy_plot_df, model_dir, stat_type=stat_type, n_filter=None)

        # Consultancy dumbbell with both modes (if redteam data exists)
        if has_consultancy and len(consultancy_df[consultancy_df["threat_model"] == "redteam"]) > 0:
            print(f"  Creating consultancy both-modes dumbbell in {model_dir.name}/")
            plot_dumbbell_consultancy_both_modes(
                model_df, model_dir / "dumbbell_consultancy_both_modes.png", stat_type="mean"
            )

        print(f"  ✓ Completed {model}\n")

    # Cross-model comparison plot (consultancy ethics)
    output_path = FIGURES_DIR / "model_comparison_consultancy_ethics.pdf"
    plot_model_comparison_ethics(df, output_path)

    # Hero figure: Loan Profit + Sepsis ICU (Opus 4.1 only)
    opus_41_df = df[df["generation_model"] == "claude-opus-4-1-20250805"].copy()
    opus_41_df["Org Type"] = opus_41_df["org_type"].map(ORG_TYPE_NAMES)
    hero_output = FIGURES_DIR / "pareto_loan_sepsis_benign.png"
    plot_loan_sepsis_benign(opus_41_df, hero_output)

    print("All plots generated!")


if __name__ == "__main__":
    main()
