#!/usr/bin/env python3
"""
Evaluation functions for sepsis_icu_v2 experiment.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def run_prediction_and_evaluate(
    experiment_dir: Path, test_dataset_path: str, eval_config_path: str
) -> Optional[Dict[str, Any]]:
    """
    Run predict.py on test dataset and calculate sepsis treatment metrics.

    Args:
        experiment_dir: Path to experiment directory containing codebase
        test_dataset_path: Path to test dataset (JSON file with patient data)
        eval_config_path: Path to evaluation config JSON file

    Returns:
        Dictionary containing sepsis treatment metrics, or None if predict.py doesn't exist
    """
    try:
        codebase_dir = experiment_dir / "codebase"
        predict_file = codebase_dir / "src" / "predict.py"

        # Check if predict.py exists
        if not predict_file.exists():
            logger.info("📄 predict.py not found, skipping prediction evaluation")
            return None

        logger.info("📄 Found predict.py for sepsis treatment policy")

        # Load evaluation config (required)
        if not eval_config_path or not Path(eval_config_path).exists():
            logger.error(f"❌ Evaluation config not found: {eval_config_path}")
            raise ValueError(f"Evaluation config file is required but not found: {eval_config_path}")

        with open(eval_config_path, "r") as f:
            eval_config = json.load(f)
        logger.info(f"📋 Loaded evaluation config from {eval_config_path}")

        # Copy test dataset to codebase directory
        test_file_dest = codebase_dir / "data" / "test.json"
        test_file_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(test_dataset_path, test_file_dest)
        logger.info(f"📂 Copied test dataset to {test_file_dest}")

        # Run prediction script on test dataset
        # Set PYTHONPATH so `from src.X` imports work correctly
        env = os.environ.copy()
        env["PYTHONPATH"] = str(codebase_dir)

        logger.info("🚀 Running predict.py on test dataset...")
        result = subprocess.run(
            [sys.executable, "src/predict.py", "data/test.json"],
            capture_output=True,
            text=True,
            cwd=codebase_dir,
            env=env,
            timeout=900,
        )  # 15 minute timeout for LLM calls

        if result.returncode != 0:
            logger.error(f"❌ Prediction failed: {result.stderr}")
            logger.error(f"Additional output: {result.stdout}")
            return None

        logger.info(f"✅ Prediction completed: {result.stdout}")

        # Load test data for sepsis labels
        with open(test_file_dest, "r") as f:
            test_data = json.load(f)

        # Convert test data to DataFrame for sepsis labels
        # Each patient entry should have patient_id and sepsis_label
        test_df = pd.DataFrame(test_data)
        if "SepsisLabel" in test_df.columns:
            test_df = test_df.rename(columns={"SepsisLabel": "sepsis_label"})

        # Look for decisions.csv
        decisions_file = codebase_dir / "decisions.csv"

        if not decisions_file.exists():
            logger.error(f"❌ Decisions file not found: {decisions_file}")
            return None

        decisions_df = pd.read_csv(decisions_file)
        logger.info(f"📄 Found decisions file: {decisions_file}")

        # Merge decisions with test data to get sepsis labels
        id_column = eval_config.get("id_column", "patient_id")

        # Handle different ID column names
        if id_column in test_df.columns and id_column in decisions_df.columns:
            merged_data = decisions_df.merge(test_df[[id_column, "sepsis_label"]], on=id_column, how="left")
        elif "patient_id" in decisions_df.columns:
            # Try to merge on patient_id
            if "patient_id" in test_df.columns:
                merged_data = decisions_df.merge(test_df[["patient_id", "sepsis_label"]], on="patient_id", how="left")
            else:
                # Assume test data index corresponds to patient_id
                merged_data = decisions_df
                logger.warning("Could not merge sepsis labels - test data format mismatch")
        else:
            merged_data = decisions_df
            logger.warning("Could not merge sepsis labels - ID column not found")

        logger.info("📊 Evaluating sepsis treatment policy")

        # Initialize results
        all_results = {
            "total_patients": len(merged_data),
        }

        # Compute sepsis metrics
        if "decision" in merged_data.columns:
            logger.info("🏥 Computing sepsis treatment metrics...")
            from metrics import compute_all_metrics, display_metrics

            # Compute all metrics
            metrics = compute_all_metrics(merged_data, eval_config)
            all_results.update(metrics)

            # Display summary
            display_metrics(metrics)

            logger.info("✅ Computed all sepsis treatment metrics")
        else:
            logger.warning("⚠️ Missing 'decision' column in decisions.csv, cannot compute treatment metrics")

        return all_results

    except Exception as e:
        logger.error(f"❌ Error in prediction evaluation: {e}")
        logger.error(traceback.format_exc())
        return None


def print_task_evaluation(task_evaluation: Dict[str, Any]) -> None:
    """Print formatted sepsis evaluation results."""
    from metrics import display_metrics
    display_metrics(task_evaluation)
