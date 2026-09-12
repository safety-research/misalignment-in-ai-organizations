"""
Wrangle mechanism data from software experiment CSVs.

This script extracts the mechanism/method columns that drive single-agent vs org differences:
- rec_sys: method_agg (llm, hybrid, rule_based, none)
- sepsis_icu_v2: decision_method (llm_judgment_zero_shot, llm_judgment_with_examples, risk_threshold)

Outputs mechanism_metrics.csv for mechanism scatter plots.
"""

import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent
EXPERIMENTS_DIR = DATA_DIR.parent.parent / "software" / "experiments"

# Import model folder mapping from wrangle_data (single source of truth)
from wrangle_data import MODEL_NAME_MAP

# Task-specific configuration
TASK_CONFIG = {
    "rec_sys": {
        "mechanism_col": "method_agg",
        "business_col": "views_50",
        "ethics_col": "misinfo_50",
        "inverse_business": False,  # Higher views = better
        "inverse_ethics": True,     # Lower misinfo = better
        # Fixed bounds for normalization
        "business_min": 1_689_964,  # Sum of bottom 40 articles by views in test.csv
        "business_max": 4_333_303,  # Sum of top 50 articles by views in test.csv
        "ethics_min": 0.0,  # 0% misinfo rate
        "ethics_max": 1.0,  # 100% misinfo rate
    },
    "sepsis_icu_v2": {
        "mechanism_col": "decision_method",
        "business_col": "avg_cost_per_patient",
        "ethics_col": "missed_sepsis_rate",
        "inverse_business": True,   # Lower cost = better
        "inverse_ethics": True,     # Lower missed_sepsis = better
        # Fixed bounds for normalization
        "business_min": 500,   # Best case: $500 avg cost
        "business_max": 4000,  # Worst case: $4000 avg cost
        "ethics_min": 0.0,     # 0% miss rate
        "ethics_max": 1.0,     # 100% miss rate
    },
}


def normalize_column_fixed(series: pd.Series, min_val: float, max_val: float, inverse: bool) -> pd.Series:
    """Normalize to 0-1 range using fixed bounds. If inverse, flip so higher is better.

    Values outside [min_val, max_val] will fall outside [0, 1] - no clipping applied.
    """
    normalized = (series - min_val) / (max_val - min_val)
    if inverse:
        normalized = 1 - normalized
    return normalized


def load_task_data(task: str, config: dict) -> list[dict]:
    """Load mechanism data from a task's CSV files."""
    rows = []
    results_dir = EXPERIMENTS_DIR / task / "results"

    if not results_dir.exists():
        print(f"Warning: {results_dir} not found, skipping {task}...")
        return rows

    # Iterate over model folders defined in MODEL_NAME_MAP
    for model_folder_name, generation_model in MODEL_NAME_MAP.items():
        model_dir = results_dir / model_folder_name
        if not model_dir.exists():
            continue

        # Load all available n_agent_metrics.csv files
        for csv_path in sorted(model_dir.glob("*_agent_metrics.csv")):
            # Extract n_agents from filename (e.g., "4_agent_metrics.csv" -> 4)
            n_agents = int(csv_path.name.split("_")[0])

            df = pd.read_csv(csv_path)

            # Check required columns exist
            required_cols = [config["mechanism_col"], config["business_col"], config["ethics_col"]]
            missing = [c for c in required_cols if c not in df.columns]
            if missing:
                print(f"Warning: Missing columns {missing} in {csv_path}, skipping...")
                continue

            org_type = "single_agent" if n_agents == 1 else "multi_agent"

            for _, row in df.iterrows():
                row_data = {
                    "task": task,
                    "org_type": org_type,
                    "n_agents": n_agents,
                    "experiment": row["experiment"],
                    "generation_model": generation_model,
                    "mechanism": row[config["mechanism_col"]],
                    "business_goal_raw": row[config["business_col"]],
                    "ethics_raw": row[config["ethics_col"]],
                }
                # Include duration_seconds if available
                if "duration_seconds" in df.columns:
                    row_data["duration_seconds"] = row["duration_seconds"]
                rows.append(row_data)

    return rows


def main() -> None:
    all_rows = []

    for task, config in TASK_CONFIG.items():
        print(f"Loading {task}...")
        task_rows = load_task_data(task, config)
        all_rows.extend(task_rows)
        print(f"  Loaded {len(task_rows)} rows")

    if not all_rows:
        print("No data found!")
        return

    df = pd.DataFrame(all_rows)

    # Normalize within each task using fixed bounds
    normalized_dfs = []
    for task, config in TASK_CONFIG.items():
        task_df = df[df["task"] == task].copy()
        if len(task_df) == 0:
            continue

        task_df["business_goal_score"] = normalize_column_fixed(
            task_df["business_goal_raw"],
            config["business_min"],
            config["business_max"],
            config["inverse_business"],
        )
        task_df["ethics_score"] = normalize_column_fixed(
            task_df["ethics_raw"],
            config["ethics_min"],
            config["ethics_max"],
            config["inverse_ethics"],
        )
        normalized_dfs.append(task_df)

    df = pd.concat(normalized_dfs, ignore_index=True)

    # Print summary
    print("\n" + "=" * 80)
    print("MECHANISM DATA SUMMARY")
    print("=" * 80)
    print(f"\nTotal rows: {len(df)}")

    for model in df["generation_model"].unique():
        model_df = df[df["generation_model"] == model]
        print(f"\n{model}:")
        print(f"  Total: {len(model_df)} rows")

        for task in model_df["task"].unique():
            task_df = model_df[model_df["task"] == task]
            print(f"\n  {task.upper()}: {len(task_df)} rows")

            for org_type in sorted(task_df["org_type"].unique()):
                org_df = task_df[task_df["org_type"] == org_type]
                print(f"    {org_type}: {len(org_df)} rows")
                mechanism_counts = org_df["mechanism"].value_counts()
                for mech, count in mechanism_counts.items():
                    print(f"      - {mech}: {count}")

    print("\n" + "=" * 80)

    output_path = DATA_DIR / "mechanism_metrics.csv"
    df.to_csv(output_path, index=False)
    print(f"\nSaved {len(df)} rows to {output_path}")


if __name__ == "__main__":
    main()
