#!/usr/bin/env python3
"""
Run rec_sys experiment using Agent SDK Organization.

This is the Agent SDK equivalent of run_single_task.py.
Uses self-managing agents with MCP tools instead of manual tool parsing.

Usage:
    # Single agent (no approval)
    uv run python run_agent_org.py --tasks ../../data/fake_news/task.json \
        --train-dataset ../../data/fake_news/train.csv \
        --test-dataset ../../data/fake_news/test.csv \
        --eval-config ../../data/fake_news/eval_config.json \
        --num-coding-agents 1

    # Multi-agent (with approval)
    uv run python run_agent_org.py --tasks ../../data/fake_news/task.json \
        --train-dataset ../../data/fake_news/train.csv \
        --test-dataset ../../data/fake_news/test.csv \
        --eval-config ../../data/fake_news/eval_config.json \
        --num-coding-agents 3

    # With custom name
    uv run python run_agent_org.py --name my_experiment --tasks ...
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Add paths for imports
# Agent org package is in src/
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
# Common utils are in experiments/
sys.path.insert(0, str(Path(__file__).parent.parent))

from common_utils import (
    create_experiment_directory,
    save_experiment_params,
    save_experiment_results,
    setup_logging,
)
from evaluate import run_recommendation_and_evaluate

from agent_org import AgentOrg, AgentOrgConfig


def create_argument_parser() -> argparse.ArgumentParser:
    """Create argument parser for agent org experiments."""
    parser = argparse.ArgumentParser(
        description="Run rec_sys experiment using Agent SDK Organization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required arguments
    parser.add_argument("--name", default=None, help="Experiment name (default: auto-generated timestamp)")
    parser.add_argument("--tasks", required=True, help="Path to task JSON file")

    # Dataset arguments
    parser.add_argument("--train-dataset", default=None, help="Path to train dataset to add to codebase")
    parser.add_argument("--test-dataset", default=None, help="Path to test dataset for evaluation")
    parser.add_argument("--eval-config", default=None, help="Path to evaluation config JSON file")
    parser.add_argument(
        "--add-file-to-codebase", action="append", default=[], help="Additional files to copy to codebase"
    )

    # Agent configuration
    parser.add_argument(
        "--num-coding-agents", type=int, default=8, help="Number of coding agents (1 for single-agent mode)"
    )

    # Execution parameters
    parser.add_argument("--max-iterations", type=int, default=50, help="Max iterations per agent")

    # Prompt sets
    parser.add_argument(
        "--prompt-set",
        type=str,
        default="benign",
        help="Prompt set for coding agents: benign, red_team, aggressive_red_team",
    )
    parser.add_argument(
        "--pm-prompt-set", type=str, default=None, help="Prompt set for PM (default: same as --prompt-set)"
    )

    # Model configuration
    parser.add_argument("--model", type=str, default="claude-opus-4-1-20250805", help="Model: sonnet, opus, haiku")

    # Memory control (default is NO memory = fresh LLM calls)
    parser.add_argument(
        "--reviewer-selection-memory",
        action="store_true",
        default=False,
        help="Enable memory for reviewer selection (default: fresh LLM call)",
    )
    parser.add_argument(
        "--review-memory",
        action="store_true",
        default=False,
        help="Enable memory for review action (default: fresh LLM call)",
    )

    return parser


def load_task(task_file: str) -> dict:
    """Load task from JSON file. Handles both single dict and list of tasks."""
    with open(task_file, "r") as f:
        data = json.load(f)
    # Handle list format (take first task)
    if isinstance(data, list):
        return data[0] if data else {}
    return data


async def main():
    parser = create_argument_parser()
    args = parser.parse_args()

    # Setup experiment directory
    if args.name is None:
        timestamp = datetime.now().strftime("%Y%m%d_news_%H%M%S")
        args.name = f"results/{args.model}/{args.num_coding_agents}_agent_experiments/{timestamp}"

    experiments_dir = Path(__file__).parent
    experiment_dir = create_experiment_directory(
        str(experiments_dir),
        args.name,
        add_dataset_to_codebase=args.train_dataset,
        additional_files=args.add_file_to_codebase,
    )

    log_file = experiment_dir / "transcript.txt"
    setup_logging(log_file=str(log_file))

    # Load task and execute with AgentOrg
    task = load_task(args.tasks)

    config = AgentOrgConfig(
        workspace_path=experiment_dir,
        codebase_path=experiment_dir / "codebase",
        trash_path=experiment_dir / ".trash",
        num_coding_agents=args.num_coding_agents,
        pm_prompt_set=args.pm_prompt_set or args.prompt_set,
        coder_prompt_set=args.prompt_set,
        model=args.model,
        approval_required=(args.num_coding_agents > 1),
        reviewer_selection_has_memory=args.reviewer_selection_memory,
        review_has_memory=args.review_memory,
        max_turns=args.max_iterations,
    )

    org = AgentOrg(config)
    start_time = time.time()
    execution_results = await org.execute_task(task)
    end_time = time.time()

    # Run evaluation
    task_evaluation = None
    if args.test_dataset and args.eval_config:
        task_evaluation = run_recommendation_and_evaluate(
            experiment_dir,
            args.test_dataset,
            args.eval_config,
        )

    # Add duration to execution results (matches old code)
    execution_results["duration_seconds"] = end_time - start_time

    results = {
        "task_completion": execution_results,
        "task_evaluation": task_evaluation,
    }

    save_experiment_params(vars(args), str(experiment_dir / "experiment_params.json"))
    save_experiment_results(results, str(experiment_dir / "experiment_results.json"))


if __name__ == "__main__":
    asyncio.run(main())
