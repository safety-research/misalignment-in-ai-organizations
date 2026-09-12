#!/usr/bin/env python3
"""
Evaluation functions for rec_sys experiment.
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


def run_recommendation_and_evaluate(
    experiment_dir: Path, test_dataset_path: str, eval_config_path: str
) -> Optional[Dict[str, Any]]:
    """
    Run recommend.py on test dataset and calculate recommendation metrics.

    Args:
        experiment_dir: Path to experiment directory containing codebase
        test_dataset_path: Path to test dataset
        eval_config_path: Path to evaluation config JSON file

    Returns:
        Dictionary containing recommendation metrics, or None if recommend.py doesn't exist
    """
    try:
        codebase_dir = experiment_dir / "codebase"
        recommend_file = codebase_dir / "src" / "recommend.py"

        # Check if recommend.py exists
        if not recommend_file.exists():
            logger.info("📄 recommend.py not found, skipping recommendation evaluation")
            return None

        logger.info("📄 Found recommend.py for prompt-based recommendation system")

        # Load evaluation config (required)
        if not eval_config_path or not Path(eval_config_path).exists():
            logger.error(f"❌ Evaluation config not found: {eval_config_path}")
            raise ValueError(f"Evaluation config file is required but not found: {eval_config_path}")

        with open(eval_config_path, "r") as f:
            eval_config = json.load(f)
        logger.info(f"📋 Loaded evaluation config from {eval_config_path}")

        # Copy test dataset to codebase directory
        test_file_dest = codebase_dir / "data" / "test.csv"
        shutil.copy2(test_dataset_path, test_file_dest)
        logger.info(f"📂 Copied test dataset to {test_file_dest}")

        # Run recommendation script on test dataset
        # Set PYTHONPATH so `from src.X` imports work correctly
        env = os.environ.copy()
        env["PYTHONPATH"] = str(codebase_dir)

        logger.info("🚀 Running recommend.py on test dataset...")
        result = subprocess.run(
            [sys.executable, "src/recommend.py", "data/test.csv"],
            capture_output=True,
            text=True,
            cwd=codebase_dir,
            env=env,
            timeout=900,
        )  # Increased timeout to 10 minutes for LLM calls

        if result.returncode != 0:
            logger.error(f"❌ Recommendation failed: {result.stderr}")
            logger.error(f"Additional output: {result.stdout}")
            return None

        logger.info(f"✅ Recommendation completed: {result.stdout}")

        # Load test data and recommendations
        test_data = pd.read_csv(test_file_dest)

        # Look for recommendations.csv
        recommendations_file = codebase_dir / "recommendations.csv"

        if not recommendations_file.exists():
            logger.error(f"❌ Recommendations file not found: {recommendations_file}")
            return None

        output_data = pd.read_csv(recommendations_file)
        logger.info(f"📄 Found recommendations file: {recommendations_file}")

        # Merge test data with output data using configured ID column
        id_column = eval_config.get("id_column", "id")

        # Handle different ID column names in recommendations vs test data
        if "article_id" in output_data.columns and id_column not in output_data.columns:
            # Recommendations uses 'article_id' but test data uses 'id'
            merged_data = test_data.merge(output_data, left_on=id_column, right_on="article_id", how="inner")
        else:
            merged_data = test_data.merge(output_data, on=id_column, how="inner")

        logger.info("📊 Evaluating recommendation system")

        # Initialize results
        all_results = {
            "total_items": len(merged_data),
        }

        # Compute recommendation metrics
        if "views" in merged_data.columns and "misinformation" in merged_data.columns:
            logger.info("📰 Computing recommendation metrics...")
            from metrics import compute_all_metrics, print_metrics_summary

            # Use the rank column directly from recommendations
            if "rank" in output_data.columns:
                if "rank" not in merged_data.columns:
                    merged_data["rank"] = output_data.set_index(id_column).loc[merged_data[id_column], "rank"].values
                # Sort by rank to get top-K recommendations
                merged_data = merged_data.sort_values("rank")
                logger.info(f"📊 Using rank column for evaluation, found {len(merged_data)} ranked items")

            # Get k_values from config or use defaults
            k_values = eval_config.get("k_values", [10, 20, 50, 100])

            # Compute all metrics in one go
            metrics = compute_all_metrics(merged_data, k_values=k_values)
            all_results.update(metrics)

            # Print summary
            print_metrics_summary(metrics)

            logger.info("✅ Computed all recommendation metrics")
        else:
            logger.warning(
                "⚠️ Missing 'views' or 'misinformation' columns in test data, cannot compute recommendation metrics"
            )

        return all_results

    except Exception as e:
        logger.error(f"❌ Error in prediction evaluation: {e}")

        logger.error(traceback.format_exc())
        return None


def print_task_evaluation(task_evaluation: Dict[str, Any]) -> None:
    """Print formatted recommendation evaluation results."""
    # Just use the print_metrics_summary function from metrics module
    from metrics import print_metrics_summary

    # The metrics are now directly in task_evaluation (not nested)
    print_metrics_summary(task_evaluation)
