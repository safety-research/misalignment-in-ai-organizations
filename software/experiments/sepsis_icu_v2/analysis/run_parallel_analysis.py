#!/usr/bin/env python3
"""
Parallel experiment analysis using Claude Agent SDK.

Usage:
    python run_parallel_analysis.py -r opus-4-1-v2-wm -a 1,8 -n 5 --max-concurrency 4
    python run_parallel_analysis.py -r opus-4-1-v2-wm -a 1,8 --experiments 092428,092430,235041

Arguments:
    -r: Results subfolder (e.g., opus-4-1-v2-wm)
    -a: Agent folders to analyze (e.g., 1 or 8 or 1,8)
    -n: Number of experiments to analyze per agent folder (sequential selection)
    --experiments: Specific experiment IDs to analyze (comma-separated, partial match)
    --max-concurrency: Maximum number of parallel agents running
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Tuple

try:
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
except ImportError:
    print("ERROR: claude_agent_sdk not installed. Install with: pip install claude-agent-sdk")
    sys.exit(1)


# Path constants
SCRIPT_DIR = Path(__file__).parent
EXPERIMENT_BASE = SCRIPT_DIR.parent / "results"
SUBAGENT_PROMPT_PATH = SCRIPT_DIR / "subagent_prompt.md"


def find_experiments(
    results_folder: str,
    agent_folders: List[str],
    num_per_folder: int | None = None,
    experiment_ids: List[str] | None = None,
) -> List[Path]:
    """
    Find experiment directories to analyze.

    Args:
        results_folder: Results subfolder name (e.g., "opus-4-1-v2-wm")
        agent_folders: List of agent folder names (e.g., ["1", "8"])
        num_per_folder: Number of experiments to select from each agent folder
        experiment_ids: Specific experiment IDs to find (partial match supported)

    Returns:
        List of experiment directory paths
    """
    experiments = []

    for agent_folder in agent_folders:
        agent_path = EXPERIMENT_BASE / results_folder / f"{agent_folder}_agent_experiments"

        if not agent_path.exists():
            print(f"WARNING: Agent folder not found: {agent_path}")
            continue

        # Find all experiment directories (those containing codebase/)
        experiment_dirs = []
        for item in agent_path.iterdir():
            if item.is_dir() and (item / "codebase").exists():
                experiment_dirs.append(item)

        # Sort by name
        experiment_dirs.sort(key=lambda p: p.name)

        # Filter or limit based on mode
        if experiment_ids:
            # Filter to only matching experiment IDs (partial match)
            selected = [d for d in experiment_dirs if any(exp_id in d.name for exp_id in experiment_ids)]
        elif num_per_folder is not None:
            # Take first n
            selected = experiment_dirs[:num_per_folder]
        else:
            selected = experiment_dirs

        print(
            f"Found {len(experiment_dirs)} experiments in {agent_folder}_agent_experiments, selecting {len(selected)}"
        )
        experiments.extend(selected)

    return experiments


async def analyze_experiment(
    experiment_dir: Path, prompt_text: str, semaphore: asyncio.Semaphore
) -> Tuple[Path, bool, str]:
    """
    Analyze a single experiment using Claude Agent SDK.

    Args:
        experiment_dir: Path to experiment directory
        prompt_text: The subagent prompt instructions
        semaphore: Semaphore for concurrency control

    Returns:
        Tuple of (experiment_dir, success, message)
    """
    async with semaphore:
        print(f"[START] {experiment_dir.name}")

        try:
            # Create agent options
            def stderr_handler(msg: str):
                if "error" in msg.lower() or "fail" in msg.lower():
                    print(f"[STDERR] {experiment_dir.name}: {msg.strip()}")

            options = ClaudeAgentOptions(
                model="claude-opus-4-5-20251101",
                max_turns=100,
                cwd=str(experiment_dir),
                permission_mode="bypassPermissions",  # Bypass all permission checks
                allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
                stderr=stderr_handler,
            )

            # Create client and send prompt
            async with ClaudeSDKClient(options=options) as client:
                # Send the analysis task
                await client.query(prompt_text)

                # Receive and log responses
                result_message = None
                async for message in client.receive_response():
                    if isinstance(message, ResultMessage):
                        result_message = message

                # Check result
                if result_message:
                    if result_message.is_error:
                        print(f"[ERROR] {experiment_dir.name}: Agent returned error - {result_message.result}")
                        return (
                            experiment_dir,
                            False,
                            f"Agent error: {result_message.result}",
                        )
                    print(f"[DEBUG] {experiment_dir.name}: Completed in {result_message.num_turns} turns")

            # Check that required files were created
            required_files = [
                "ANALYSIS.md",
                "decision_logic.json",
                "decision_annotations.csv",
            ]
            missing_files = [f for f in required_files if not (experiment_dir / f).exists()]

            if missing_files:
                msg = f"Missing files: {', '.join(missing_files)}"
                print(f"[FAIL] {experiment_dir.name}: {msg}")
                return (experiment_dir, False, msg)

            print(f"[DONE] {experiment_dir.name}")
            return (experiment_dir, True, "All files created successfully")

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(f"[ERROR] {experiment_dir.name}: {error_msg}")
            return (experiment_dir, False, error_msg)


async def main():
    parser = argparse.ArgumentParser(description="Parallel experiment analysis using Claude Agent SDK")
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
        help="Agent folders to analyze (e.g., 1 or 8 or 1,8)",
    )
    parser.add_argument(
        "-n",
        "--num-per-folder",
        type=int,
        default=None,
        help="Number of experiments per agent folder",
    )
    parser.add_argument(
        "--experiments",
        type=str,
        default=None,
        help="Specific experiment IDs to analyze (comma-separated, partial match)",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=4,
        help="Maximum concurrent agents (default: 4)",
    )

    args = parser.parse_args()

    # Parse agent folders
    agent_folders = [f.strip() for f in args.agent_folders.split(",")]

    # Parse experiment IDs if provided
    experiment_ids = None
    if args.experiments:
        experiment_ids = [e.strip() for e in args.experiments.split(",")]

    # Check that at least one selection method is provided
    if args.num_per_folder is None and experiment_ids is None:
        print("ERROR: Must provide either -n/--num-per-folder or --experiments")
        sys.exit(1)

    # Check that subagent prompt exists
    if not SUBAGENT_PROMPT_PATH.exists():
        print(f"ERROR: Subagent prompt not found at {SUBAGENT_PROMPT_PATH}")
        sys.exit(1)

    # Load subagent prompt
    prompt_text = SUBAGENT_PROMPT_PATH.read_text()

    # Find experiments to analyze
    print("=" * 80)
    print("Finding experiments...")
    print("=" * 80)
    experiments = find_experiments(args.results_folder, agent_folders, args.num_per_folder, experiment_ids)

    if not experiments:
        print("ERROR: No experiments found")
        sys.exit(1)

    print(f"\nTotal experiments to analyze: {len(experiments)}")
    print(f"Max concurrency: {args.max_concurrency}")
    print("=" * 80)

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(args.max_concurrency)

    # Run analyses in parallel
    tasks = [analyze_experiment(exp_dir, prompt_text, semaphore) for exp_dir in experiments]
    results = await asyncio.gather(*tasks)

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    successful = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]

    print(f"Total: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")

    if failed:
        print("\nFailed experiments:")
        for exp_dir, _, msg in failed:
            print(f"  - {exp_dir.name}: {msg}")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
