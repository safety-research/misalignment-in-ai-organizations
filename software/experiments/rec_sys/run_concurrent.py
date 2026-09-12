#!/usr/bin/env python3
"""
Run multiple agent_org experiments concurrently.

Usage:
    # Run 3 single-agent and 2 five-agent experiments
    uv run python run_concurrent.py --runs "1:3,5:2"

    # Run 5 single-agent experiments
    uv run python run_concurrent.py --runs "1:5"

    # Run 3 experiments with 1,3,5 agents respectively
    uv run python run_concurrent.py --runs "1:1,3:1,5:1"

    # With custom settings
    uv run python run_concurrent.py --runs "1:5" --max-iterations 30 --max-concurrent 2
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path


async def run_single_experiment(
    experiment_name: str,
    num_coding_agents: int,
    tasks_file: str,
    train_dataset: str,
    test_dataset: str,
    eval_config: str,
    additional_files: list,
    model: str,
    max_iterations: int,
    prompt_set: str,
    pm_prompt_set: str | None,
    reviewer_selection_memory: bool,
    review_memory: bool,
    run_index: int,
    total_runs: int,
) -> dict:
    """Run a single experiment by calling run_agent_org.py as subprocess"""

    agent_type = "single-agent" if num_coding_agents == 1 else f"{num_coding_agents}-agent"
    print(f"🚀 [{run_index}/{total_runs}] Starting {agent_type} run: {experiment_name}")

    # Build command
    cmd = [
        sys.executable,
        "run_agent_org.py",
        "--name",
        experiment_name,
        "--tasks",
        tasks_file,
        "--train-dataset",
        train_dataset,
        "--test-dataset",
        test_dataset,
        "--eval-config",
        eval_config,
        "--model",
        model,
        "--max-iterations",
        str(max_iterations),
        "--num-coding-agents",
        str(num_coding_agents),
        "--prompt-set",
        prompt_set,
    ]

    # Optional flags
    if pm_prompt_set:
        cmd.extend(["--pm-prompt-set", pm_prompt_set])
    if reviewer_selection_memory:
        cmd.append("--reviewer-selection-memory")
    if review_memory:
        cmd.append("--review-memory")

    # Add additional files to codebase
    for file_path in additional_files:
        cmd.extend(["--add-file-to-codebase", file_path])

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=Path(__file__).parent
        )

        stdout, _ = await proc.communicate()

        if proc.returncode == 0:
            print(f"✅ [{run_index}/{total_runs}] Completed {agent_type} run: {experiment_name}")
            return {"experiment_name": experiment_name, "success": True, "error": None}
        else:
            print(
                f"❌ [{run_index}/{total_runs}] Failed {agent_type} run: {experiment_name} (exit code {proc.returncode})"
            )
            output_lines = stdout.decode().strip().split("\n")
            if output_lines:
                print(f"   Last output: {output_lines[-1][:200]}")
            return {"experiment_name": experiment_name, "success": False, "error": f"exit_code_{proc.returncode}"}

    except Exception as e:
        print(f"❌ [{run_index}/{total_runs}] Failed {agent_type} run: {experiment_name} - {str(e)[:100]}")
        if proc and proc.returncode is None:
            proc.kill()
            await proc.wait()
        return {"experiment_name": experiment_name, "success": False, "error": str(e)}


def parse_runs(runs_str: str) -> list[tuple[int, int]]:
    """
    Parse runs specification string.

    Format: "agents:count,agents:count,..."
    Examples:
        "1:3" -> [(1, 3)]  # 3 runs with 1 agent
        "1:3,5:2" -> [(1, 3), (5, 2)]  # 3 single-agent + 2 five-agent
        "1:5,3:3,5:2" -> [(1, 5), (3, 3), (5, 2)]
    """
    result = []
    for part in runs_str.split(","):
        part = part.strip()
        if ":" in part:
            agents, count = part.split(":")
            result.append((int(agents), int(count)))
        else:
            # Just a number means 1 run with that many agents
            result.append((int(part), 1))
    return result


async def run_concurrent_experiments(
    runs: list[tuple[int, int]],
    max_iterations: int,
    max_concurrent: int,
    model: str,
    prompt_set: str,
    pm_prompt_set: str | None,
    reviewer_selection_memory: bool,
    review_memory: bool,
    additional_files: list,
):
    """Run multiple experiments concurrently"""

    # Build experiment list
    experiments = []
    for num_agents, count in runs:
        for _ in range(count):
            experiments.append(num_agents)

    total_experiments = len(experiments)
    if total_experiments == 0:
        print("❌ No experiments requested")
        return

    # Setup paths
    base_dir = Path(__file__).parent
    data_dir = base_dir.parent.parent / "data" / "fake_news"

    tasks_file = str(data_dir / "task.json")
    train_dataset = str(data_dir / "train.csv")
    test_dataset = str(data_dir / "test.csv")
    eval_config = str(data_dir / "eval_config.json")

    # Default additional files
    if not additional_files:
        additional_files = [str(base_dir / "llm_client.py")]

    # Print config
    print("🚀 Starting concurrent experiments")
    print("━" * 60)
    print("Configuration:")
    for num_agents, count in runs:
        agent_type = "single-agent" if num_agents == 1 else f"{num_agents}-agent"
        print(f"  - {agent_type}: {count} runs")
    print(f"  - Total experiments: {total_experiments}")
    print(f"  - Max iterations: {max_iterations}")
    print(f"  - Max concurrent: {max_concurrent}")
    print(f"  - Model: {model}")
    print(f"  - Prompt set: {prompt_set}")
    print("━" * 60)
    print()

    # Generate experiment configs with unique timestamps
    experiment_configs = []
    for i, num_agents in enumerate(experiments):
        await asyncio.sleep(1.0)  # Ensure unique timestamps
        timestamp = datetime.now().strftime("%Y%m%d_news_%H%M%S")
        experiment_configs.append(
            {
                "name": f"results/{model}/{num_agents}_agent_experiments/{timestamp}",
                "num_agents": num_agents,
                "run_index": i + 1,
            }
        )

    # Run with concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_with_semaphore(exp_config):
        async with semaphore:
            return await run_single_experiment(
                experiment_name=exp_config["name"],
                num_coding_agents=exp_config["num_agents"],
                tasks_file=tasks_file,
                train_dataset=train_dataset,
                test_dataset=test_dataset,
                eval_config=eval_config,
                additional_files=additional_files,
                model=model,
                max_iterations=max_iterations,
                prompt_set=prompt_set,
                pm_prompt_set=pm_prompt_set,
                reviewer_selection_memory=reviewer_selection_memory,
                review_memory=review_memory,
                run_index=exp_config["run_index"],
                total_runs=total_experiments,
            )

    print(f"🏃 Running {total_experiments} experiments (max {max_concurrent} concurrent)...\n")

    results = await asyncio.gather(*[run_with_semaphore(exp) for exp in experiment_configs], return_exceptions=True)

    # Summary
    successful = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
    print()
    print("━" * 60)
    print(f"🎉 Batch complete! ({successful}/{total_experiments} succeeded)")
    print()
    print(f"Results saved to: results/{model}/")
    for num_agents, count in runs:
        print(f"  - results/{model}/{num_agents}_agent_experiments/")
    print("━" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Run multiple agent_org experiments concurrently",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 3 single-agent runs
  %(prog)s --runs "1:3"

  # 3 single-agent + 2 five-agent runs
  %(prog)s --runs "1:3,5:2"

  # Various agent counts
  %(prog)s --runs "1:2,3:2,5:2,8:2"
""",
    )

    parser.add_argument(
        "--runs",
        type=str,
        required=True,
        help='Run specification: "agents:count,..." e.g. "1:3,5:2" for 3 single + 2 five-agent',
    )
    parser.add_argument("--max-iterations", type=int, default=50, help="Maximum iterations per agent (default: 50)")
    parser.add_argument("--max-concurrent", type=int, default=2, help="Maximum concurrent experiments (default: 2)")
    parser.add_argument(
        "--model", type=str, default="claude-opus-4-1-20250805", help="Model to use (default: claude-opus-4-1-20250805)"
    )
    parser.add_argument(
        "--prompt-set",
        type=str,
        default="benign",
        help="Prompt set: benign, red_team, aggressive_red_team (default: benign)",
    )
    parser.add_argument(
        "--pm-prompt-set", type=str, default=None, help="Prompt set for PM agent (default: same as --prompt-set)"
    )
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
        help="Enable memory for code review (default: fresh LLM call)",
    )
    parser.add_argument("--add-file", action="append", default=[], help="Additional files to copy to codebase")

    args = parser.parse_args()

    runs = parse_runs(args.runs)

    asyncio.run(
        run_concurrent_experiments(
            runs=runs,
            max_iterations=args.max_iterations,
            max_concurrent=args.max_concurrent,
            model=args.model,
            prompt_set=args.prompt_set,
            pm_prompt_set=args.pm_prompt_set,
            reviewer_selection_memory=args.reviewer_selection_memory,
            review_memory=args.review_memory,
            additional_files=args.add_file,
        )
    )


if __name__ == "__main__":
    main()
