from database_repository import DatabaseRepository
from datetime import datetime
import argparse
import os
import json
import re


"""
This script reads from database files and outputs a flat JSON list with the relevant outputs and other features.

The script expects a standardized directory structure:
  {base_dir}/{experiment_name}/{model}/{agent_mode}/{scenario}/{files}

The script validates that folder names at each level match known models/agent_modes/scenarios.
This helps catch errors like swapped directory levels.

Usage examples:
  # Extract from simulation DB files
  python db_to_df.py --experiment_name resample

  # Extract from baseline text files
  python db_to_df.py --experiment_name baseline_experiment --baseline_txt

  # Strict mode: fail on unknown values instead of warning
  python db_to_df.py --experiment_name resample --strict

Output format: List of records, each containing:
  - experiment: experiment name
  - model: model name
  - agent_mode: agent mode (benign, red_team, etc.)
  - scenario: scenario name
  - proposal: proposal text
  - num_emails: number of emails
  - sample_index: index of this sample
  - file_path: path to source file

Validation:
  - Checks models against KNOWN_MODELS list
  - Checks agent_modes against KNOWN_AGENT_MODES list
  - Checks scenarios against KNOWN_SCENARIOS list
  - Warns (or fails with --strict) if unknown values are found
"""

# Known models - update this list as new models are added
KNOWN_MODELS = [
    "claude-3-7-sonnet-20250219",
    "claude-opus-4-1-20250805",
    "claude-sonnet-4-20250514",
    "gpt-4o-2024-08-06",
    "gpt-4.1-2025-04-14",
    "Qwen3-235B-A22B-fp8-tput",
    "Qwen2.5-72B-Instruct-Turbo",
    "Llama-3.3-70B-Instruct-Turbo",
    "DeepSeek-V3",
    "deepseek-ai/DeepSeek-V3",
    "Qwen/Qwen3-235B-A22B-fp8-tput",
    "claude-opus-4-5-20251101", 
    "gpt-4.1-2025-04-14", 
    "gpt-5-mini-2025-08-07"
]

# Known agent modes - update this list as new modes are added
KNOWN_AGENT_MODES = [
    "benign",
    "red_team",
    "mix",
    "mixed",
    "best_of_20",
    "dynamic_opt5",
    "agg_best_of_20",
    "agg_dyn_opt5",
    # Baseline modes
    "baseline-roleplay",
    "baseline-simple",
    "baseline-redteam",
    "baseline-sample",
]

# Known scenarios - update this list as new scenarios are added
KNOWN_SCENARIOS = [
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


def get_emails_from_communications_director(db_path):
    """Get all emails sent by the communications director."""
    
    # Open the database
    db_repo = DatabaseRepository(db_path)
    
    try:
        # Get all emails from the conversation log
        all_emails = db_repo.get_conversation_log()
        
        # Filter emails sent by "communications director"
        communications_director_emails = [
            email for email in all_emails 
            if email['sender'].lower() == 'communications_director'
        ]
        
        print(f"Found {len(communications_director_emails)} emails sent by communications director:")
        print("=" * 60)
        
        for i, email in enumerate(communications_director_emails, 1):
            # Convert timestamp to readable format
            timestamp = datetime.fromtimestamp(email['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            
            print(f"Email #{i}")
            print(f"Timestamp: {timestamp}")
            print(f"To: {', '.join(email['recipients'])}")
            print(f"Subject: {email['subject']}")
            print(f"Content: {email['content']}")
            print(f"Iteration: {email['iteration_id']}")
            print("-" * 60)
        
        return communications_director_emails
        
    finally:
        # Always close the database connection
        db_repo.close()


def get_proposals_from_txt(txt_path: str) -> list[str]:
    """
    get proposals from txt file, extracting content from <CLIENT_REPORT> tags
    """
    with open(txt_path, "r") as f:
        content = f.read()

    # Try to extract content between <CLIENT_REPORT> and </CLIENT_REPORT> tags
    match = re.search(r'<CLIENT_REPORT>(.*?)</CLIENT_REPORT>', content, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Fallback: try old format [external: client report]
    lines = content.split("[external: client report]")
    if len(lines) == 1:
        return lines[0]
    else:
        return lines[1]
    
    
         

def get_proposals_from_db(db_path: str, n_proposals: int = 1, selection : str = 'longest') -> (list[str], int):
    """
    Get proposals from multiple sources and return total number of emails sent.

    Sources checked (in order):
    1. CLIENT_REPORTs from communications_director agent messages
    2. Emails sent TO Partner from communications_director
    3. Fallback to Analyst responses if nothing found
    """

    # Open the database
    db_repo = DatabaseRepository(db_path)
    agent_names = db_repo.get_all_agent_names()
    agent_id_map = {name: db_repo.get_agent_id(name) for name in agent_names}
    agent_messages = {name: db_repo.get_agent_messages(agent_id) for name, agent_id in agent_id_map.items() if agent_id}

    proposals = []
    all_emails = []

    try:
        # Get total email count
        all_emails = db_repo.get_conversation_log()
        total_emails = len(all_emails)

        print(f"Found {total_emails} total emails in conversation log")

        # SOURCE 1: Extract CLIENT_REPORTs from communications_director agent messages
        comm_dir_messages = agent_messages.get('communications_director', [])
        print(f"Found {len(comm_dir_messages)} agent messages from communications_director")

        for msg in comm_dir_messages:
            # Only check assistant messages (agent outputs)
            if msg['role'] == 'assistant':
                # Check for CLIENT_REPORT tags
                match = re.search(r'<CLIENT_REPORT>(.*?)</CLIENT_REPORT>', msg['content'], re.DOTALL)
                if match:
                    proposals.append({
                        'content': match.group(1).strip(),
                        'source': 'agent_message_CLIENT_REPORT'
                    })
                # Fallback to old format
                elif "[external: client report]" in msg['content']:
                    proposals.append({
                        'content': msg['content'],
                        'source': 'agent_message_external'
                    })

        if len(proposals) > 0:
            print(f"Found {len(proposals)} CLIENT_REPORT(s) from communications_director agent messages")

        # SOURCE 2: Extract emails sent TO Partner from communications_director
        emails_to_partner = [
            email for email in all_emails
            if email['sender'].lower() == 'communications_director' and 'Partner' in email['recipients']
        ]

        if len(emails_to_partner) > 0:
            print(f"Found {len(emails_to_partner)} email(s) from communications_director TO Partner")
            for email in emails_to_partner:
                # Check if email contains CLIENT_REPORT
                match = re.search(r'<CLIENT_REPORT>(.*?)</CLIENT_REPORT>', email['content'], re.DOTALL)
                if match:
                    proposals.append({
                        'content': match.group(1).strip(),
                        'source': 'email_to_partner_CLIENT_REPORT'
                    })
                else:
                    # Include the full email content as a proposal
                    proposals.append({
                        'content': email['content'],
                        'source': 'email_to_partner_full'
                    })

    finally:
        # Always close the database connection
        db_repo.close()

    if len(proposals) == 0:
        print("No proposals found in communications_director outputs or emails to Partner")
        print("Falling back to Analyst responses...")

        # Fallback: get analyst last response
        analyst_emails = [
            email for email in all_emails
            if email['sender'].lower() == 'analyst'
        ]

        if len(analyst_emails) > 0:
            print(f"Using analyst last response from emails")
            return [analyst_emails[-1]['content']], total_emails
        else:
            messages = agent_messages.get('Analyst', [])
            if len(messages) == 0:
                print(f"No analyst responses available - no proposals to extract")
                return None, None
            else:
                print(f"Using analyst last response from agent messages")
                return [messages[-1]['content']], total_emails

    # Print summary of sources
    print(f"\nProposal sources breakdown:")
    source_counts = {}
    for prop in proposals:
        source = prop['source']
        source_counts[source] = source_counts.get(source, 0) + 1
    for source, count in sorted(source_counts.items()):
        print(f"  - {source}: {count}")

    # Extract just the content for selection
    proposal_contents = [p['content'] for p in proposals]

    if selection == 'last':
        proposal_contents = [proposal_contents[-1]]
    elif selection == 'all':
        pass
    elif selection == 'longest':
        proposal_contents = [max(proposal_contents, key=len)]
    else:
        raise ValueError(f"Invalid selection: {selection} choose from ['last', 'all', 'longest']")

    return proposal_contents, total_emails


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract emails and other features")

    parser.add_argument(
        "--experiment_name",
        type=str,
        help="Name of the experiment",
    )

    parser.add_argument(
        "--baseline_txt",
        action="store_true",
        help="Whether to process baseline txt files",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on unknown models/agent_modes/scenarios instead of warning",
    )

    args = parser.parse_args()
    experiment_name = args.experiment_name
    strict_mode = args.strict

    if args.baseline_txt:
        assert experiment_name.startswith("baseline")
        base_dir = "outputs"
    else:
        base_dir = "simulations"

    results_filename = f"outputs/{experiment_name}.json"
    results_list = []  # Flat list of records
    skipped_files = []

    # Track what we found for summary
    found_models = set()
    found_agent_modes = set()
    found_scenarios = set()

    # Standardized directory structure: experiment_name/model/agent_mode/scenario/files
    experiment_path = f"{base_dir}/{experiment_name}"

    if not os.path.exists(experiment_path):
        print(f"Error: Experiment directory '{experiment_path}' does not exist")
        exit(1)

    # Walk through the standardized directory structure
    for model in os.listdir(experiment_path):
        model_path = os.path.join(experiment_path, model)
        if not os.path.isdir(model_path):
            continue

        # Validate model name
        if model not in KNOWN_MODELS:
            error_msg = [
                f"⚠️  Unknown model '{model}' at level 1 (expected structure: experiment/MODEL/agent_mode/scenario)",
                f"   Known models: {', '.join(KNOWN_MODELS[:5])}...",
                f"   This might indicate:",
                f"     - Wrong directory structure (e.g., agent_mode and model are swapped)",
                f"     - New model that needs to be added to KNOWN_MODELS list",
                f"     - Typo in directory name",
            ]
            print("\n".join(error_msg))
            if strict_mode:
                print(f"\n❌ ERROR: Strict mode enabled. Exiting.")
                exit(1)
            print(f"   Continuing anyway...\n")

        print(f"Processing model: {model}")
        found_models.add(model)

        for agent_mode in os.listdir(model_path):
            agent_mode_path = os.path.join(model_path, agent_mode)
            if not os.path.isdir(agent_mode_path):
                continue

            # Validate agent mode
            if agent_mode not in KNOWN_AGENT_MODES:
                error_msg = [
                    f"  ⚠️  Unknown agent_mode '{agent_mode}' at level 2 (expected: experiment/model/AGENT_MODE/scenario)",
                    f"     Known agent modes: {', '.join(KNOWN_AGENT_MODES[:5])}...",
                    f"     This might indicate wrong directory structure or new agent mode.",
                ]
                print("\n".join(error_msg))
                if strict_mode:
                    print(f"\n  ❌ ERROR: Strict mode enabled. Exiting.")
                    exit(1)
                print(f"     Continuing anyway...\n")

            print(f"  Processing agent mode: {agent_mode}")
            found_agent_modes.add(agent_mode)

            for scenario in os.listdir(agent_mode_path):
                scenario_path = os.path.join(agent_mode_path, scenario)
                if not os.path.isdir(scenario_path):
                    continue

                # Validate scenario name
                if scenario not in KNOWN_SCENARIOS:
                    error_msg = [
                        f"    ⚠️  Unknown scenario '{scenario}' at level 3 (expected: experiment/model/agent_mode/SCENARIO)",
                        f"       Known scenarios: {', '.join(KNOWN_SCENARIOS[:5])}...",
                        f"       This might indicate wrong directory structure or new scenario.",
                    ]
                    print("\n".join(error_msg))
                    if strict_mode:
                        print(f"\n    ❌ ERROR: Strict mode enabled. Exiting.")
                        exit(1)
                    print(f"       Continuing anyway...\n")

                print(f"    Processing scenario: {scenario}")
                found_scenarios.add(scenario)

                for file_name in os.listdir(scenario_path):
                    file_path = os.path.join(scenario_path, file_name)

                    # Process database files
                    if file_name.endswith(".db"):
                        print(f"      Processing db file: {file_name}")

                        proposals, num_emails = get_proposals_from_db(file_path)
                        if proposals is None:
                            skipped_files.append(file_path)
                            continue

                        # Create a flat record for each proposal
                        for idx, proposal in enumerate(proposals):
                            record = {
                                "experiment": experiment_name,
                                "model": model,
                                "agent_mode": agent_mode,
                                "scenario": scenario,
                                "file_name": file_name,
                                "file_path": file_path,
                                "sample_index": idx,
                                "proposal": proposal,
                                "num_emails": num_emails,
                                "file_type": "db"
                            }
                            results_list.append(record)

                    # Process text files (for baselines)
                    elif file_name.endswith(".txt") and args.baseline_txt:
                        print(f"      Processing txt file: {file_name}")

                        proposal = get_proposals_from_txt(file_path)
                        if len(proposal) == 0:
                            skipped_files.append(file_path)
                            continue

                        record = {
                            "experiment": experiment_name,
                            "model": model,
                            "agent_mode": agent_mode,
                            "scenario": scenario,
                            "file_name": file_name,
                            "file_path": file_path,
                            "sample_index": 0,
                            "proposal": proposal,
                            "num_emails": 1,
                            "file_type": "txt"
                        }
                        results_list.append(record)

    # Save flat list to JSON
    with open(results_filename, "w") as f:
        json.dump(results_list, f, indent=2)

    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE!")
    print(f"{'='*60}")
    print(f"Total records extracted: {len(results_list)}")
    print(f"Output saved to: {results_filename}")

    print(f"\n📊 Summary of extracted data:")
    print(f"  Models found ({len(found_models)}): {', '.join(sorted(found_models))}")
    print(f"  Agent modes found ({len(found_agent_modes)}): {', '.join(sorted(found_agent_modes))}")
    print(f"  Scenarios found ({len(found_scenarios)}): {', '.join(sorted(found_scenarios))}")

    # Show unknown values if any
    unknown_models = found_models - set(KNOWN_MODELS)
    unknown_agent_modes = found_agent_modes - set(KNOWN_AGENT_MODES)
    unknown_scenarios = found_scenarios - set(KNOWN_SCENARIOS)

    if unknown_models or unknown_agent_modes or unknown_scenarios:
        print(f"\n⚠️  Unknown values found (consider adding to KNOWN_* lists):")
        if unknown_models:
            print(f"  Unknown models: {', '.join(sorted(unknown_models))}")
        if unknown_agent_modes:
            print(f"  Unknown agent modes: {', '.join(sorted(unknown_agent_modes))}")
        if unknown_scenarios:
            print(f"  Unknown scenarios: {', '.join(sorted(unknown_scenarios))}")

    if skipped_files:
        print(f"\n⚠️  Skipped {len(skipped_files)} files (no proposals found):")
        for f in skipped_files[:5]:  # Show first 5
            print(f"  - {f}")
        if len(skipped_files) > 5:
            print(f"  ... and {len(skipped_files) - 5} more")

    print(f"\n✅ Ready for evaluation! Run:")
    print(f"   python evaluation.py --json_path {results_filename} --models all --method scoring")
    print(f"{'='*60}\n")