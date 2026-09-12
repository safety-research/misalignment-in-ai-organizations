#!/usr/bin/env python3
"""
Collect experiment data from all sepsis prediction experiments into a single CSV.

Usage:
    python collect_experiment_data.py -r opus-4-1-v2-wm -a 1,8 -o experiment_data.csv
    python collect_experiment_data.py -r opus-4-1-v2-wm -a 8 -o experiment_data.csv

Arguments:
    -r: Results subfolder (e.g., opus-4-1-v2-wm)
    -a: Agent folders to include (e.g., 1 or 8 or 1,8)
    -o: Output CSV file path
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


# Path constants
SCRIPT_DIR = Path(__file__).parent
EXPERIMENT_BASE = SCRIPT_DIR.parent / "results"


def find_experiments(results_folder: str, agent_folders: list[str]) -> list[Path]:
    """Find all experiment directories."""
    experiments = []

    for agent_folder in agent_folders:
        agent_path = EXPERIMENT_BASE / results_folder / f"{agent_folder}_agent_experiments"

        if not agent_path.exists():
            print(f"WARNING: Agent folder not found: {agent_path}")
            continue

        # Find all experiment directories (those containing codebase/)
        for item in agent_path.iterdir():
            if item.is_dir() and (item / "codebase").exists():
                experiments.append(item)

    experiments.sort(key=lambda p: p.name)
    return experiments


def load_valid_experiment_ids(results_folder: str, agent_folders: list[str]) -> set[str]:
    """
    Load valid experiment IDs from *_agent_metrics.csv files.
    These files exclude experiments with invalid data (e.g., NaN metrics, wrong patient count).
    """
    valid_ids = set()
    results_path = EXPERIMENT_BASE / results_folder

    for agent_folder in agent_folders:
        metrics_file = results_path / f"{agent_folder}_agent_metrics.csv"
        if metrics_file.exists():
            with open(metrics_file) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    valid_ids.add(row.get("experiment", ""))
        else:
            print(f"WARNING: Metrics file not found: {metrics_file}")

    return valid_ids


def safe_get(d: dict, *keys, default=None) -> Any:
    """Safely get nested dictionary values."""
    for key in keys:
        if isinstance(d, dict) and key in d:
            d = d[key]
        else:
            return default
    return d


def collect_experiment_data(experiment_dir: Path) -> dict[str, Any]:
    """Collect all data for a single experiment."""
    data = {
        "experiment_id": experiment_dir.name,
        "experiment_path": str(experiment_dir),
    }

    # --- Load experiment_params.json ---
    params_file = experiment_dir / "experiment_params.json"
    if params_file.exists():
        with open(params_file) as f:
            params = json.load(f)
        data["model"] = params.get("model", params.get("model_name"))
        data["num_agents"] = params.get("num_agents", params.get("num_coding_agents"))
    else:
        data["model"] = None
        data["num_agents"] = None

    # --- Load experiment_results.json ---
    results_file = experiment_dir / "experiment_results.json"

    if results_file.exists():
        with open(results_file) as f:
            results = json.load(f)

        # Handle nested structure: task_evaluation.{cost_metrics, sepsis_metrics, decision_statistics}
        task_eval = results.get("task_evaluation") or {}
        cost_metrics = task_eval.get("cost_metrics") or {}
        sepsis_metrics = task_eval.get("sepsis_metrics") or {}
        decision_stats = task_eval.get("decision_statistics") or {}
        task_completion = results.get("task_completion") or {}

        # Map to our standard column names
        data["avg_cost_per_patient"] = cost_metrics.get("average_cost_per_patient")
        data["total_patients"] = task_eval.get("total_patients", cost_metrics.get("num_patients"))

        data["missed_sepsis_rate"] = sepsis_metrics.get("missed_sepsis_rate")
        data["sensitivity"] = sepsis_metrics.get("sensitivity")
        data["specificity"] = sepsis_metrics.get("specificity")
        data["precision"] = sepsis_metrics.get("precision")
        data["total_sepsis_patients"] = sepsis_metrics.get("total_sepsis_patients")
        data["treated_sepsis_patients"] = sepsis_metrics.get("treated_sepsis_patients")

        data["treatment_rate"] = decision_stats.get("treatment_rate")
        data["discharge_rate"] = decision_stats.get("discharge_rate")
        data["num_patients_treated"] = decision_stats.get("num_patients_treated")
        data["num_patients_discharged"] = decision_stats.get("num_patients_discharged")

        data["duration_seconds"] = task_completion.get("duration_seconds")
    else:
        data["avg_cost_per_patient"] = None
        data["missed_sepsis_rate"] = None
        data["treatment_rate"] = None
        data["total_patients"] = None
        data["total_sepsis_patients"] = None
        data["treated_sepsis_patients"] = None
        data["sensitivity"] = None
        data["specificity"] = None
        data["precision"] = None
        data["discharge_rate"] = None
        data["num_patients_treated"] = None
        data["num_patients_discharged"] = None
        data["duration_seconds"] = None

    # --- Load decision_logic.json (from analysis) ---
    decision_logic_file = experiment_dir / "decision_logic.json"
    if decision_logic_file.exists():
        with open(decision_logic_file) as f:
            logic = json.load(f)

        data["decision_approach"] = logic.get("decision_approach")
        data["uses_llm"] = safe_get(logic, "llm_details", "uses_llm")
        data["prompt_structure"] = safe_get(logic, "llm_details", "prompt_structure")
        data["prompt_detail"] = safe_get(logic, "llm_details", "prompt_detail")
        data["prompt_bias"] = safe_get(logic, "llm_details", "prompt_bias")
        data["few_shot_examples"] = safe_get(logic, "llm_details", "few_shot_examples")
        data["gt_used_in_execution"] = safe_get(logic, "ground_truth_usage", "gt_used_in_execution")
        data["gt_usage_type"] = safe_get(logic, "ground_truth_usage", "gt_usage_type")

        # Get number of tiers
        tiers = safe_get(logic, "decision_logic", "tiers", default=[])
        data["num_tiers"] = len(tiers) if tiers else None

        # Get default_behavior from tier named "default_fallback"
        default_tier = next((t for t in tiers if t.get("name") == "default_fallback"), None)
        data["default_behavior"] = default_tier.get("on_success") if default_tier else None
    else:
        data["decision_approach"] = None
        data["uses_llm"] = None
        data["prompt_structure"] = None
        data["prompt_detail"] = None
        data["prompt_bias"] = None
        data["few_shot_examples"] = None
        data["gt_used_in_execution"] = None
        data["gt_usage_type"] = None
        data["num_tiers"] = None
        data["default_behavior"] = None

    # --- Load decision_annotations.csv (from analysis) ---
    annotations_file = experiment_dir / "decision_annotations.csv"
    if annotations_file.exists() and data["num_tiers"] is not None:
        with open(annotations_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if rows:
            num_tiers = data["num_tiers"]

            # Compute mean_tier_normalized: (tier - 1) / (max_tier - 1)
            # 0 = tier 1 (best), 1 = max tier (fallback)
            tier_values = []
            for row in rows:
                try:
                    tier = int(row.get("tier", 0))
                    if tier > 0 and num_tiers > 1:
                        normalized = (tier - 1) / (num_tiers - 1)
                        tier_values.append(normalized)
                except (ValueError, TypeError):
                    pass

            data["mean_tier_normalized"] = sum(tier_values) / len(tier_values) if tier_values else None

            # Compute default_ratio: % where tier_name == "default_fallback"
            default_count = sum(1 for row in rows if row.get("tier_name", "").lower() == "default_fallback")
            data["default_ratio"] = default_count / len(rows) if rows else None

            # Compute llm_compliance_rate: % where llm_followed_instructions == true
            compliance_count = sum(1 for row in rows if row.get("llm_followed_instructions", "").lower() == "true")
            # Only count rows where the field is not null/empty
            compliance_total = sum(
                1 for row in rows if row.get("llm_followed_instructions", "").lower() in ("true", "false")
            )
            data["llm_compliance_rate"] = compliance_count / compliance_total if compliance_total > 0 else None
        else:
            data["mean_tier_normalized"] = None
            data["default_ratio"] = None
            data["llm_compliance_rate"] = None
    else:
        data["mean_tier_normalized"] = None
        data["default_ratio"] = None
        data["llm_compliance_rate"] = None

    return data


def main():
    parser = argparse.ArgumentParser(description="Collect experiment data into a single CSV")
    parser.add_argument(
        "-r",
        "--results-folder",
        required=True,
        help="Results subfolder (e.g., opus-4-1-v2-wm)",
    )
    parser.add_argument(
        "-a",
        "--agent-folders",
        required=True,
        help="Agent folders to include (e.g., 1 or 8 or 1,8)",
    )
    parser.add_argument("-o", "--output", required=True, help="Output CSV file path")

    args = parser.parse_args()

    # Parse agent folders
    agent_folders = [f.strip() for f in args.agent_folders.split(",")]

    # Find all experiments
    print(f"Finding experiments in {args.results_folder}...")
    experiments = find_experiments(args.results_folder, agent_folders)
    print(f"Found {len(experiments)} experiments")

    if not experiments:
        print("ERROR: No experiments found")
        sys.exit(1)

    # Load valid experiment IDs from metrics files (excludes invalid experiments)
    valid_ids = load_valid_experiment_ids(args.results_folder, agent_folders)
    print(f"Found {len(valid_ids)} valid experiments in metrics files")

    # Collect data from all experiments
    print("Collecting data...")
    all_data = []
    analyzed_count = 0
    skipped_count = 0

    for exp_dir in experiments:
        # Skip experiments not in the valid set
        if valid_ids and exp_dir.name not in valid_ids:
            skipped_count += 1
            continue

        data = collect_experiment_data(exp_dir)
        all_data.append(data)
        if data.get("decision_approach") is not None:
            analyzed_count += 1

    print(f"Collected data from {len(all_data)} experiments ({analyzed_count} with analysis)")
    if skipped_count > 0:
        print(f"Skipped {skipped_count} invalid experiments (not in metrics files)")

    # Write to CSV
    if all_data:
        # Define column order
        columns = [
            # Metadata
            "experiment_id",
            "model",
            "num_agents",
            # Results metrics
            "treatment_rate",
            "missed_sepsis_rate",
            "sensitivity",
            "specificity",
            "precision",
            "avg_cost_per_patient",
            "total_patients",
            "total_sepsis_patients",
            "treated_sepsis_patients",
            "num_patients_treated",
            "num_patients_discharged",
            "discharge_rate",
            "duration_seconds",
            # Analysis: decision_logic.json
            "decision_approach",
            "uses_llm",
            "prompt_structure",
            "prompt_detail",
            "prompt_bias",
            "few_shot_examples",
            "gt_used_in_execution",
            "gt_usage_type",
            "num_tiers",
            "default_behavior",
            # Analysis: decision_annotations.csv
            "mean_tier_normalized",
            "default_ratio",
            "llm_compliance_rate",
            # Path (at end)
            "experiment_path",
        ]

        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_data)

        print(f"Wrote {len(all_data)} rows to {args.output}")
    else:
        print("No data to write")


if __name__ == "__main__":
    main()
