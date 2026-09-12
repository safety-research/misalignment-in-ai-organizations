#!/usr/bin/env python3
"""
Common utilities for experiment runners - shared across all experiments.
"""

import json
import shutil
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def create_base_argument_parser(description: str = "Run coding experiment") -> argparse.ArgumentParser:
    """
    Create base argument parser with common arguments for all experiments.

    Args:
        description: Description for the argument parser

    Returns:
        ArgumentParser with common arguments
    """
    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)

    # Required arguments
    parser.add_argument("--name", required=True, help="Experiment name")
    parser.add_argument("--tasks", required=True, help="Path to tasks JSON file or directory containing JSON files")

    # Dataset arguments (optional for backward compatibility)
    parser.add_argument("--train-dataset", default=None, help="Path to train dataset to add to codebase")
    parser.add_argument("--test-dataset", default=None, help="Path to test dataset to use for evaluation")
    parser.add_argument("--eval-config", default=None, help="Path to evaluation config JSON file")
    parser.add_argument(
        "--add-file-to-codebase",
        action="append",
        default=[],
        help="Additional files to copy to codebase (can be used multiple times)",
    )

    # Task filtering
    parser.add_argument("--task-ids", nargs="+", help="Specific task IDs to run")

    # LLM configuration
    parser.add_argument("--model", default="claude-sonnet-4-20250514", help="LLM model to use")
    parser.add_argument("--temperature", type=float, default=0.1, help="Temperature for generation")
    parser.add_argument("--max-tokens", type=int, default=20000, help="Maximum tokens for response")

    # Execution parameters
    parser.add_argument("--max-iterations", type=int, default=20, help="Max iterations per task")

    # Prompt configuration
    parser.add_argument(
        "--prompt-set", type=str, default="benign", help="Prompt set to use for coding agents (default: benign)"
    )
    parser.add_argument(
        "--pm-prompt-set", type=str, default=None, help="Prompt set for project manager (default: same as --prompt-set)"
    )

    # Caching options
    parser.add_argument(
        "--use-cache", action="store_true", default=False, help="Enable LLM response caching (default: False)"
    )

    # Directory structure
    parser.add_argument(
        "--separate-task-dirs",
        action="store_true",
        default=True,
        help="Create separate directories for each task (default: True)",
    )
    parser.add_argument(
        "--combine-tasks", action="store_false", dest="separate_task_dirs", help="Combine all tasks in one codebase"
    )

    parser.add_argument("--num-coding-agents", type=int, default=5, help="Number of coding agents")
    return parser


def setup_logging(level: int = logging.INFO, log_file: Optional[str] = None) -> logging.Logger:
    """
    Setup logging configuration with both console and file output

    Args:
        level: Logging level (default: INFO)
        log_file: Optional path to log file. If None, creates a timestamped log file
    """
    # Ensure log directory exists
    if log_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"logs/experiment_{timestamp}.log"
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Clear any existing handlers
    logging.getLogger().handlers.clear()

    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Create file handler
    if log_file:
        file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Log the log file location
    logging.info(f"📝 Logging to file: {log_path.absolute()}")
    return root_logger


def create_experiment_directory(
    base_path: str,
    experiment_name: str,
    add_dataset_to_codebase: Optional[str] = None,
    additional_files: Optional[list] = None,
) -> Path:
    """
    Create and return experiment directory path.

    Args:
        base_path: Base directory for experiments
        experiment_name: Name of the experiment
        add_dataset_to_codebase: Path to dataset file or directory to add to codebase
        additional_files: List of additional file paths to copy to codebase

    Returns:
        Path object for the experiment directory
    """
    experiment_dir = Path(base_path) / experiment_name
    experiment_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    (experiment_dir / "codebase").mkdir(exist_ok=True)
    (experiment_dir / ".trash").mkdir(exist_ok=True)

    logger.info(f"📁 Created experiment directory: {experiment_dir}")

    if add_dataset_to_codebase:
        dataset_path = Path(add_dataset_to_codebase)
        (experiment_dir / "codebase" / "data").mkdir(parents=True, exist_ok=True)

        if dataset_path.is_dir():
            # If it's a directory, copy the entire directory
            dataset_name = dataset_path.name
            dest_path = experiment_dir / "codebase" / "data" / dataset_name
            if dest_path.exists():
                shutil.rmtree(dest_path)
            shutil.copytree(dataset_path, dest_path)
            num_files = len(list(dest_path.rglob("*")))
            logger.info(f"📂 Copied directory '{dataset_name}' with {num_files} files to codebase")
        else:
            # If it's a file, copy the file
            dataset_name = dataset_path.name
            shutil.copy(dataset_path, experiment_dir / "codebase" / "data" / dataset_name)
            logger.info(f"📄 Added dataset file to codebase: {dataset_name}")

    # Copy additional files to codebase
    if additional_files:
        for file_path in additional_files:
            source_path = Path(file_path)
            if source_path.exists():
                # Determine destination based on file type/name
                if source_path.name.endswith(".py"):
                    # Python files go to src directory
                    dest_dir = experiment_dir / "codebase" / "src"
                    dest_dir.mkdir(parents=True, exist_ok=True)
                else:
                    # Other files go to root of codebase
                    dest_dir = experiment_dir / "codebase"

                dest_path = dest_dir / source_path.name
                shutil.copy2(source_path, dest_path)
                logger.info(f"📄 Copied {source_path.name} to codebase")
            else:
                logger.warning(f"⚠️ File not found: {file_path}")

    return experiment_dir


def save_json_data(data: Dict[str, Any], file_path: str) -> bool:
    """
    Save data to JSON file.

    Args:
        data: Dictionary to save
        file_path: Path to save the data

    Returns:
        True if successful, False otherwise
    """
    try:
        with open(file_path, "w") as f:
            # Use default=str to handle datetime objects
            json.dump(data, f, indent=2, default=str)
        logger.info(f"📊 Saved data to {file_path}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to save data to {file_path}: {e}")
        return False


# Aliases for backward compatibility
save_experiment_results = save_json_data
save_experiment_params = save_json_data


def print_experiment_results(results: Dict[str, Any]) -> None:
    """
    Print a formatted experiment summary.

    Args:
        results: Experiment results dictionary
    """
    print("\n" + "=" * 50)
    print("EXPERIMENT SUMMARY")
    print("=" * 50)
    print(f"Total Tasks: {results.get('total_tickets', 'N/A')}")
    print(f"Completed: {results.get('completed_tickets', 'N/A')}")
    print(f"Failed: {results.get('failed_tickets', 'N/A')}")
    print(f"Duration: {results.get('duration_seconds', 0):.2f} seconds")
    print("=" * 50)
