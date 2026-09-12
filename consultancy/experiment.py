"""
experiment.py - Run agent-based organizational simulations

Usage examples:
  # Run consultancy simulation with specific config
  python experiment.py --simulation consultancy --scenario loan_profit \
    --org_config_path config/default-consultancy-model.yaml \
    --model claude-sonnet-4-20250514 --experiment_name resample \
    --condition baseline --num_samples 15

  # Run baseline simulation with red-team agent
  python experiment.py --simulation baseline-redteam --scenario painkiller_sales \
    --model claude-opus-4-1-20250805 --experiment_name baseline_sample \
    --condition baseline-redteam --num_samples 15

Key arguments:
  --simulation: Type of simulation (consultancy, baseline-redteam, baseline-roleplay)
  --scenario: Business scenario to run (loan_profit, painkiller_sales, etc.)
  --model: AI model to use for agents
  --experiment_name: Experiment identifier for organizing outputs
  --num_samples: Number of simulation runs to generate
  --org_config_path: YAML config file for organization structure (consultancy only)

"""

import argparse
import logging
import time
import os
import asyncio
from definitions_organizations import (
    run_consultancy_simulation,
    run_baseline_simulation,
    run_organization_sampling_experiment,
)
from pathlib import Path
import json

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run agent-based simulations")
    parser.add_argument(
        "--simulation",
        type=str,
        default="consultancy",
        help="Type of simulation to run",
    )

    parser.add_argument(
        "--org_config_path",
        type=str,
        default="config/default-consultancy-model.yaml",
        help="Path to the organization configuration file",
    )

    # Financial simulation specific arguments
    parser.add_argument(
        "--implicit",
        action="store_true",
        help="For financial sim: Use implicit instructions (default: explicit)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-3-7-sonnet-20250219",
        help="Model to use for agents (default: claude-3-7-sonnet-20250219)",
    )

    parser.add_argument(
        "--start_ind",
        type=int,
        default=None,
        help="Starting index for trajectory samples (overrides config file if specified)",
    )

    parser.add_argument(
        "--max_iterations",
        type=int,
        default=None,
        help="Number of iterations to run (overrides config file if specified)",
    )

    parser.add_argument(
        "--condition",
        default=None,
        help="Condition to run (overrides config file if specified)",
    )
    parser.add_argument(
        "--experiment_name",
        type=str,
        default=None,
        choices=["default", "conversation_length", "org_size", "model_sweep", "agent_prompt_opt", "deep_research", "org_sampling", "baseline_sample", "baseline_resample", "resample"],
        help="Name of the experiment",
    )
    parser.add_argument(
        "--anthropic_tag",
        type=str,
        default="ANTHROPIC_API_KEY",
        help="Anthropic API key tag to use (default: ANTHROPIC_API_KEY)",
    )
    # Consultancy simulation specific arguments
    parser.add_argument(
        "--scenario",
        type=str,
        choices=[
            "loan_profit",
            "zero_interest_bnpl_marketing",
            "detroit_auto_plant",
            "acquisition_valuation",
            "painkiller_sales",
            "election_sentiment",
            "sanctions_circumvention",
            "social_media_growth",
            "downsizing_company",
            "regional_hospital_costs", 
            "all"
        ],
        default="loan_profit",
        help="For consultancy sim: Type of scenario to run",
    )
    
    parser.add_argument(
        "--num_samples",
        type=int,
        default=1,
        help="Number of samples to generate for baseline simulations",
    )

    args = parser.parse_args()
    max_iterations = None
    org_size = None
    agent_type = None
    if args.experiment_name and args.condition:
        if args.experiment_name == "conversation_length": 
            max_iterations = int(args.condition) 
            print(f"running iterations experiment with {max_iterations} iterations")            
            output_dir = f"outputs/{args.experiment_name}/iter_{args.condition}"
            simulation_dir = f"simulations/{args.experiment_name}/iter_{args.condition}"
        elif args.experiment_name == "resample":
            num_samples = args.num_samples
            output_dir = f"outputs/{args.experiment_name}/resample_{num_samples}"
            simulation_dir = f"simulations/{args.experiment_name}/resample_{num_samples}"
        elif args.experiment_name == "org_size":
            org_size = args.condition 
            output_dir = f"outputs/{args.experiment_name}/size_{args.condition}"
            simulation_dir = f"simulations/{args.experiment_name}/size_{args.condition}"
        elif args.experiment_name == 'model_sweep': 
            model_name = Path(args.condition).name
            model_sweep = args.condition
            simulation_dir = f"simulations/{args.experiment_name}/model_sweep_{model_name}"
            output_dir = f"outputs/{args.experiment_name}/model_sweep_{model_name}"
        elif args.experiment_name.startswith("agent_prompt"):
            agent_type = args.condition
            output_dir = f"outputs/{args.experiment_name}/agent_prompt_{agent_type}"
            simulation_dir = f"simulations/{args.experiment_name}/agent_prompt_{agent_type}"
        elif args.experiment_name == "deep_research":
            agent_type = "benign"
            output_dir = f"outputs/{args.experiment_name}/deep_research_{args.condition}"
            simulation_dir = f"simulations/{args.experiment_name}/deep_research_{args.condition}"
        elif args.experiment_name == "org_sampling":
            # iterating through scenarios will happen at the function level since we as sampling over organizations
            await run_organization_sampling_experiment(
                condition=args.condition,
                scenario=args.scenario,
                model=args.model,
                max_iterations=args.max_iterations
            )
            return  # Exit early after running org sampling experiment
        elif args.experiment_name == "baseline_sample":
            agent_type = args.condition
            output_dir = f"outputs/{args.experiment_name}/baseline_sample_{agent_type}"
            simulation_dir = f"simulations/{args.experiment_name}/baseline_sample_{agent_type}"
        else:
            raise ValueError(f"Invalid experiment name: {args.experiment_name}")

    model_dir = f"simulations/{args.model}"
    if not os.path.exists(model_dir):
        os.makedirs(model_dir)

    if args.scenario == 'all':
        scenarios_to_run = [
        "loan_profit",
        "zero_interest_bnpl_marketing",
        "detroit_auto_plant",
        "acquisition_valuation",
        "painkiller_sales",
        "election_sentiment",
        "sanctions_circumvention",
        "social_media_growth",
        "downsizing_company",
        "regional_hospital_costs",
        ]
    else:
        scenarios_to_run = [args.scenario]

    # Run the appropriate simulation
    if args.simulation == "consultancy":
        print(agent_type)
        for scenario in scenarios_to_run:
            await run_consultancy_simulation(
                org_config_path=args.org_config_path,
                scenario_type=scenario,
                model_str=args.model,
                max_iterations=max_iterations,
                output_dir=output_dir,
                simulation_dir=simulation_dir,
                agent_type=agent_type,
                anthropic_tag=args.anthropic_tag,
                num_samples=args.num_samples,
                start_ind=args.start_ind,
            )
    elif args.simulation.startswith("baseline"):
        # Determine experiment name and agent mode
        if args.experiment_name and args.condition:
            # New structure: outputs/{experiment_name}/{model}/{agent_mode}/{scenario}/
            experiment_name = args.experiment_name
            agent_mode = args.condition  # e.g., "baseline-redteam"
        else:
            # Legacy structure for backwards compatibility
            experiment_name = args.simulation  # e.g., "baseline-redteam"
            agent_mode = args.simulation

        for scenario in scenarios_to_run:
            # Create standardized 4-level directory structure
            # outputs/{experiment_name}/{model}/{agent_mode}/{scenario}/
            baseline_output_dir = f"outputs/{experiment_name}/{args.model}/{agent_mode}/{scenario}"

            await run_baseline_simulation(
                scenario_type=scenario,
                agent_role=args.simulation,
                model_str=args.model,
                anthropic_tag=args.anthropic_tag,
                num_samples=args.num_samples,
                output_dir=baseline_output_dir,
                start_ind=args.start_ind,
            )

    # Log experiment completion
    logging.info("=" * 80)
    logging.info("EXPERIMENT COMPLETED SUCCESSFULLY")
    if args.experiment_name == "org_sampling":
        logging.info(f"Experiment: {args.experiment_name}, Condition: {args.condition}")
    elif args.simulation.startswith("baseline"):
        logging.info(f"Simulation outputs saved to: outputs/{experiment_name if args.experiment_name else args.simulation}")
    else:
        if args.experiment_name and args.condition:
            logging.info(f"Simulation outputs saved to: {simulation_dir}")
            logging.info(f"Analysis outputs saved to: {output_dir}")
    logging.info("=" * 80)


if __name__ == "__main__":
    # Set up logging
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs("logs", exist_ok=True)
    
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Create file handler
    file_handler = logging.FileHandler(f'logs/experiment_{timestamp}.log')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(file_handler)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(console_handler)

    asyncio.run(main())
