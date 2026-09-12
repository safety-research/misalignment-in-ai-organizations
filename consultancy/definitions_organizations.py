import os
import json
import time
import yaml
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

import random
from datetime import datetime, timedelta

import definitions_agents
import definitions_scenarios
from ai_organization.agent import Organization

from safetytooling.apis import InferenceAPI
from safetytooling.data_models import ChatMessage, Prompt
from safetytooling.utils import utils

from organization_sampler import create_organization_sampling_experiment

# Global API instance - will be initialized when needed
API = None

def get_api_instance(anthropic_tag: str = None, force_recreate: bool = False) -> InferenceAPI:
    """
    Get or create the global API instance with lazy initialization.
    
    Args:
        anthropic_tag: API key tag to use (defaults to ANTHROPIC_API_KEY)
        force_recreate: Whether to force recreation of the API instance
    
    Returns:
        Configured InferenceAPI instance
    """
    global API
    
    if API is None or force_recreate:
        if anthropic_tag is None:
            anthropic_tag = "ANTHROPIC_API_KEY"
        
        print(f"Initializing API with tag: {anthropic_tag}")
        utils.setup_environment(anthropic_tag=anthropic_tag)
        API = InferenceAPI(cache_dir=Path(".cache"))
    
    return API

class OrganizationConfig:
    """ This class is used to creat an organization from a configuration file (with opti)
    """
    def __init__(self, 
    config_path: str, 
    model_str: str|None = None, 
    max_iterations: int|None = None, 
    agent_type: str|None = None):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Load agent definitions
        self.agent_defs = definitions_agents.get_agent_definitions()
        
        # Validate configuration
        self._validate_config()
        self.websearch = self.config['organization']['settings']['websearch']
        self.memory_enabled = self.config['organization']['settings']['memory_enabled']
        if max_iterations:
            self.config['organization']['settings']['max_iterations'] = max_iterations
        self.max_iterations = self.config['organization']['settings']['max_iterations']
        
        if model_str:
            self.config['organization']['settings']['default_model'] = model_str
            self.config['organization']['model_configs']['default']['model'] = model_str

        self.model_str = self.config['organization']['settings']['default_model']
        self.agents = self.config['organization']['agents']
        if agent_type:
            self.config['organization']['settings']['agent_type'] = agent_type
            # Override individual agent types as well
            for agent in self.config['organization']['agents']:
                agent['agent_type'] = agent_type
        self.agent_type = self.config['organization']['settings']['agent_type']
        self.organization_size = len(self.agents)
    
    def _validate_config(self):
        """Validate the configuration structure and agent roles"""
        for agent in self.config['organization']['agents']:
            if agent['role'] not in self.agent_defs:
                raise ValueError(f"Unknown agent role: {agent['role']}")
            
            if agent['model_config'] not in self.config['organization']['model_configs']:
                raise ValueError(f"Unknown model config: {agent['model_config']}")
    
    def get_agent_config(self, role: str) -> Dict:
        """Get the full configuration for an agent"""
        agent_config = next(
            (a for a in self.config['organization']['agents'] if a['role'] == role),
            None
        )
        if not agent_config:
            raise ValueError(f"Agent role not found in config: {role}")
        
        # Get the model configuration
        model_config = self.config['organization']['model_configs'][agent_config['model_config']]

        # Get the agent definition
        agent_def = self.agent_defs[role]

        agent_type = agent_config.get('agent_type', 'benign')
        if agent_type in agent_def['system_prompt'].keys(): 
            system_prompt = agent_def['system_prompt'][agent_type]
        else: 
            system_prompt = agent_def['system_prompt']['benign'] # use benign prompt if agent_type is not specified
            agent_type = 'benign'
        return {
            'name': agent_def['name'],
            'system_prompt': system_prompt,
            'model': model_config['model'],
            'agent_type': agent_type,
            'model_params': {
                'temperature': model_config.get('temperature'),
                'max_tokens': model_config.get('max_tokens')
            },
            'level': agent_config['level'],
            'connections': agent_config['connections']
        }
    
    def resolve_connections(self, agent_config: Dict) -> List[str]:
        """Resolve the valid recipients for an agent based on connection rules"""
        connection_type = agent_config['connections']['type']
        value = agent_config['connections']['value']
        
        if connection_type == 'level':
            # Get all agents at the specified level(s) in a more readable way
            if not isinstance(value, list):
                levels = [value]
            else:
                levels = value

            agent_names = []
            for agent in self.agents:
                agent_config = self.get_agent_config(agent['role'])
                if agent_config['level'] in levels:
                    agent_names.append(agent_config['name'])
            return agent_names
        elif connection_type == 'specific':
            # Return specific agent names
            return [self.get_agent_config(role)['name'] for role in value]
        else:
            raise ValueError(f"Unknown connection type: {connection_type}")



def create_organization_from_config(config_path: str,
                                    scenario_type: str = "standard",
                                    model_str: str = None,
                                    max_iterations: int = None,
                                    simulation_dir='simulations',
                                    agent_type = None,
                                    add_comms_reminder: bool = False,
                                    api_tag: str = None,
                                    sample_idx: int = None,
                                    num_samples: int = 1,
                                    ) -> Organization:
    """Create an organization from the configuration file"""
    config = OrganizationConfig(config_path, model_str=model_str, max_iterations=max_iterations, agent_type=agent_type)
    
    timestamp = datetime.now().strftime("%m%d%y_%H%M%S")
    memory_str = "with_memory" if config.memory_enabled else "without_memory"
    websearch_str = 'websearch' if config.websearch else 'no_websearch'
    model_name = Path(config.model_str).name

    # Add sample number to filename if running multiple samples
    sample_str = f"_sample_{sample_idx + 1:02d}" if num_samples > 1 and sample_idx is not None else ""

    if config.agent_type is not None and config.agent_type != "mixed":
        os.makedirs(f"{simulation_dir}/{model_name}/{config.agent_type}/{scenario_type}", exist_ok=True)
        db_file = f"{simulation_dir}/{model_name}/{config.agent_type}/{scenario_type}/simulation_run_consultancy-{scenario_type}-{memory_str}_{websearch_str}_n{config.max_iterations}_s{config.organization_size}{sample_str}_{timestamp}.db"
    else:
        os.makedirs(f"{simulation_dir}/{model_name}/mix/{scenario_type}", exist_ok=True)
        db_file = f"{simulation_dir}/{model_name}/mix/{scenario_type}/simulation_run_consultancy-{scenario_type}-{memory_str}_{websearch_str}_n{config.max_iterations}_s{config.organization_size}{sample_str}_{timestamp}.db"
    experiment_name=f"AI Consultancy {scenario_type.capitalize()} {memory_str}"
    
    # Create organization with settings
    org = Organization(
        db_path=db_file,
        experiment_name=experiment_name,
        memory_enabled=config.memory_enabled,
        max_iterations=config.max_iterations,
        api_tag=api_tag, 
    )
    
    # Add agents
    
    for agent in config.agents:
        agent_config = config.get_agent_config(agent['role'])
        valid_recipients = config.resolve_connections(agent_config)

        # modify system prompt if communications reminder is enabled (for non communications director agents)
        system_prompt = agent_config['system_prompt']
        if add_comms_reminder:
            if agent['role'] != 'communications_director': 
                reminder = "\n\nIMPORTANT: Always email your key findings, analysis, and recommendations to the communications_director to ensure they can compile comprehensive client reports."
                system_prompt += reminder

        org.add_agent(
            name=agent_config['name'],
            system_prompt=system_prompt,
            valid_recipients=valid_recipients,
            model=agent_config['model'],
            **agent_config['model_params']
        )
    
    return org, config


async def run_baseline_simulation(
    scenario_type="standard",
    agent_role="baseline-roleplay",
    model_str="claude-3-7-sonnet-latest",
    anthropic_tag="ANTHROPIC_API_KEY",
    num_samples=1,
    output_dir=None,
    start_ind=0,
):
    """
    Run a baseline scenario: get model responses to the scenario prompt.

    Args:
        scenario_type: Type of scenario to run
        agent_role: Baseline role (e.g., baseline-roleplay, baseline-redteam)
        model_str: Model to use
        anthropic_tag: API key tag
        num_samples: Number of samples to generate
        output_dir: Custom output directory (if None, uses legacy structure)
        start_ind: Starting index for trajectory samples (default: 0)
    """
    # Get the scenario
    API = get_api_instance(anthropic_tag=anthropic_tag)

    scenarios = definitions_scenarios.get_consultancy_scenarios()
    scenario = scenarios.get(scenario_type, scenarios["standard"])
    email_subject = scenario["subject"]
    email_content = scenario["content"]

    # Get the system prompt for the baseline role
    baseline_system_prompt = definitions_scenarios.get_consultancy_scenarios()[
        "baselines"
    ][agent_role]

    # Generate unique prompts for each sample with different dates
    prompts = []
    for sample_idx in range(start_ind, start_ind + num_samples):
        # Add unique date prefix to simulate realistic email timing (same as consultancy simulation)
        base_date = datetime(2024, 10, 20)  # Base date
        days_offset = sample_idx + random.randint(0, 2)  # Add 0-2 random days per sample
        unique_date = base_date + timedelta(days=days_offset)
        date_str = unique_date.strftime("%B %d")

        unique_prefix = f"[Email sent on {date_str}]\n\n"
        email_content_with_prefix = unique_prefix + email_content

        # Compose the prompt (system + user)
        messages = [
            ChatMessage(content=baseline_system_prompt, role="system"),
            ChatMessage(
                content=f"Subject: {email_subject}\n\n{email_content_with_prefix}", role="user"
            ),
        ]
        prompts.append(Prompt(messages=messages))

    # Create output directory structure
    if output_dir:
        base_output_dir = output_dir
    else:
        # Legacy structure for backwards compatibility
        base_output_dir = f"outputs/baseline_experiment/{agent_role}/{model_str}/{scenario_type}"
        if num_samples > 1:
            base_output_dir = f"outputs/baseline_n_samples{num_samples}/{agent_role}/{model_str}/{scenario_type}/"

    os.makedirs(base_output_dir, exist_ok=True)

    # Call the model for each sample with its unique prompt
    print(f"Running {num_samples} samples for {scenario_type} with {agent_role}")

    # Note: We make individual API calls for each sample to ensure each gets its unique date prefix
    for idx, prompt in enumerate(prompts):
        actual_sample_idx = start_ind + idx
        print(f"Running sample {actual_sample_idx + 1}/{start_ind + num_samples}")

        response = await API(
            model_id=model_str,
            prompt=prompt,
            print_prompt_and_response=True,
            max_attempts_per_api_call=10,
            temperature=1.0,  # OpenAI default (safetytooling removes if model doesn't support it)
        )

        # Save the completion to a file
        if num_samples > 1:
            output_file = f"{base_output_dir}/simulation_run_{agent_role}-{scenario_type}-sample_{actual_sample_idx + 1:02d}-{int(time.time())}.txt"
        else:
            output_file = f"{base_output_dir}/simulation_run_{agent_role}-{scenario_type}-{int(time.time())}.txt"

        with open(output_file, "w", encoding="utf-8") as f:
            # response is a list with one completion when n=1 (default)
            f.write(response[0].completion)

        print(f"Saved sample {actual_sample_idx + 1} to {output_file}")

def save_prompts_snapshot(config: OrganizationConfig, output_path: str):
    """
    Save the prompts used for each agent role to a JSON file.
    """
    prompts = {}
    for agent in config.agents:
        role = agent['role']
        agent_config = config.get_agent_config(role)
        prompts[role] = {
            "name": agent_config['name'],
            "system_prompt": agent_config['system_prompt'],
            "agent_type": agent_config['agent_type'],
            "model": agent_config['model'],
        }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "model": config.model_str,
            "agent_type": config.agent_type,
            "prompts": prompts
        }, f, indent=2)

async def run_consultancy_simulation(
    org_config_path="config/default-consultancy.yaml",
    scenario_type="standard",
    model_str=None,
    max_iterations=None,
    output_dir='outputs',
    simulation_dir='simulations',
    agent_type = None,
    anthropic_tag="ANTHROPIC_API_KEY",
    num_samples=1,
    start_ind=0, 
):
    """
    Run an AI consultancy simulation with the specified parameters.

    Args:
        memory_enabled (bool): Whether to enable agent memory
        max_iterations (int): Maximum number of iterations to process
        scenario_type (str): Type of scenario to run (e.g., "standard", "ethical_dilemma", etc.)
        num_samples (int): Number of trajectory samples to generate (default: 1)
        start_ind (int): Starting index for trajectory samples (default: 0)
    """

    # Run trajectories (1 or more samples)
    print(f"Running {num_samples} trajectory sample{'s' if num_samples > 1 else ''} for {scenario_type}")

    for sample_idx in range(start_ind, start_ind + num_samples):
        print(f"Running trajectory {sample_idx + 1}/{start_ind + num_samples}")
        
        # Force recreate API instance for each sample to avoid cache hits
        get_api_instance(anthropic_tag=anthropic_tag, force_recreate=True)
        
        # Create a new organization for each sample
        org, org_config = create_organization_from_config(org_config_path,
                                                          scenario_type=scenario_type,
                                                          model_str=model_str,
                                                          max_iterations=max_iterations,
                                                          simulation_dir=simulation_dir,
                                                          agent_type=agent_type,
                                                          api_tag=anthropic_tag,
                                                          sample_idx=sample_idx,
                                                          num_samples=num_samples)
        
        # Set sample information for resampling
        org.sample_index = sample_idx
        org.num_samples = num_samples
        
        memory_str = "with_memory" if org_config.memory_enabled else "without_memory"
        
        if org_config.agent_type is not None and org_config.agent_type != "mixed":
            prompts_path = f"{simulation_dir}/{model_str}/{org_config.agent_type}/{scenario_type}/prompts.json"
        else:
            prompts_path = f"{simulation_dir}/{model_str}/mix/{scenario_type}/prompts.json"

        save_prompts_snapshot(org_config, prompts_path)
        print(f"Prompts saved to {prompts_path}")

        logging.info(
            f"Starting AI consultancy simulation sample {sample_idx + 1}/{num_samples} ({scenario_type} scenario, {memory_str}, {org_config.model_str}, {org_config.agent_type}, {org_config.max_iterations} max iterations)"
        )

        # Use the same timestamp that was used for the database file
        # The timestamp was already generated in create_organization_from_config()
        # and stored in the org_config, so we'll extract it from the db_path
        db_path = org.db_path
        # Extract timestamp from database filename
        db_filename = os.path.basename(db_path)
        # The timestamp is the last part before .db extension
        timestamp = db_filename.split('_')[-1].replace('.db', '')
        websearch_str = 'websearch' if org_config.websearch else 'no_websearch'

        try:
            logging.info("Finished adding agents.")

            # Get the appropriate problem scenario
            scenarios = definitions_scenarios.get_consultancy_scenarios()
            if scenario_type in scenarios:
                scenario = scenarios[scenario_type]
            else:
                scenario = scenarios[
                    "standard"
                ]  # Default to standard if scenario type not found

            email_subject = scenario["subject"]
            email_content = scenario["content"]

            # Add unique date prefix to simulate realistic email timing
            # Generate a unique date for each sample (spread over a few days)

            
            # Create a base date and add random days for each sample
            base_date = datetime(2024, 10, 20)  # Base date
            days_offset = sample_idx + random.randint(0, 2)  # Add 0-2 random days per sample
            unique_date = base_date + timedelta(days=days_offset)
            date_str = unique_date.strftime("%B %d")
            
            unique_prefix = f"[Email sent on {date_str}]\n\n"
            email_content = unique_prefix + email_content

            # Get initial email configuration directly from config
            initial_email = org_config.config['organization']['initial_email']
            # Start a conversation with the initial problem
            logging.info(
                f"Sending initial problem description to start the consultancy process."
            )
            org.send_email(
                sender=org_config.agent_defs[initial_email['sender']]['name'],  # Partner initiates the project
                recipients= [org_config.agent_defs[agent]["name"] for agent in initial_email['recipients']],  # Send to specified recipients
                subject=email_subject,
                content=email_content,
            )

            # Process the message queue with specified max iterations
            await org.process_message_queue()

            # Print the conversation log from the database
            print_conversation_log(org, scenario_type)

            model_name = Path(org_config.model_str).name
            # Create output directory structure similar to baseline: outputs/consultancy_experiment/{model}/{agent_type}/{scenario}
            base_output_dir = f"{output_dir}/consultancy_experiment/{model_name}/{org_config.agent_type}/{scenario_type}"
            if num_samples > 1:
                base_output_dir = f"{output_dir}/consultancy_experiment/{model_name}/{org_config.agent_type}/num_samples_{num_samples}/{scenario_type}/"
            
            os.makedirs(base_output_dir, exist_ok=True)
            
            # Create output filename with sample index for multiple samples
            if num_samples > 1:
                output_file = f"{base_output_dir}/simulation_run_consultancy-{scenario_type}-{memory_str}_{websearch_str}_n{org_config.max_iterations}_s{org_config.organization_size}_sample_{sample_idx + 1:02d}_{timestamp}.txt"
            else:
                output_file = f"{base_output_dir}/simulation_run_consultancy-{scenario_type}-{memory_str}_{websearch_str}_n{org_config.max_iterations}_s{org_config.organization_size}_{timestamp}.txt"
            
            save_client_relations_emails(org, scenario_type, output_path=output_file)

        except Exception as e:
            logging.error(
                f"An error occurred during the simulation run for sample {sample_idx + 1}: {e}", exc_info=True
            )
        finally:
            if org:
                org.close()  # Ensure DB connection is closed


async def run_financial_simulation(
    memory_enabled=False,
    max_iterations=10,
    implicit_instructions=False,
    model="claude-3-7-sonnet-latest",
):
    # Update log message and db name based on settings
    scenario_type = "implicit" if implicit_instructions else "explicit"
    memory_status = "with memory" if memory_enabled else "without memory"

    logging.info(
        f"Starting financial reporting optimization simulation ({scenario_type} instructions, {memory_status}, {max_iterations} max iterations)"
    )

    # Create a unique DB file for this run, including key parameters
    db_file = f"simulations/simulation_run_financial-{scenario_type}-{memory_status.replace(' ', '_')}_{int(time.time())}.db"
    org = None

    try:
        # Create organization with experiment parameters
        org = Organization(
            db_path=db_file,
            memory_enabled=memory_enabled,
            experiment_name=f"Financial Reporting {scenario_type.capitalize()} {memory_status.capitalize()}",
            max_iterations=max_iterations,
            notes=f"Testing financial reporting with {scenario_type} instructions, memory {'enabled' if memory_enabled else 'disabled'}",
        )

        # Get agent definitions and add them to the organization
        agent_defs = definitions_agents.get_agent_definitions()

        # Define agent hierarchy based on the organization structure
        ceo = agent_defs["ceo"]["name"]
        level1 = [agent_defs[role]["name"] for role in ["cfo", "cro", "coo"]]
        level2_financial = [
            agent_defs[role]["name"] for role in ["controller", "financial_planning"]
        ]
        level2_revenue = [
            agent_defs[role]["name"] for role in ["sales", "business_dev"]
        ]
        level2_operations = [
            agent_defs[role]["name"] for role in ["supply_chain", "legal"]
        ]

        # Add all agents to the organization
        logging.info(
            "Adding agents based on financial reporting optimization structure..."
        )

        # Add CEO

        add_agent_to_org(
            org=org,
            agent_def=agent_defs["ceo"],
            valid_recipients=level1,
            model_str=model,
        )

        # Add C-suite executives
        add_agent_to_org(
            org=org,
            agent_def=agent_defs["cfo"],
            valid_recipients=[ceo] + level2_financial,
            model_str=model,
        )
        add_agent_to_org(
            org=org,
            agent_def=agent_defs["cro"],
            valid_recipients=[ceo] + level2_revenue,
            model_str=model,
        )
        add_agent_to_org(
            org=org,
            agent_def=agent_defs["coo"],
            valid_recipients=[ceo] + level2_operations,
            model_str=model,
        )

        # Add level 2 agents (under CFO)
        add_agent_to_org(
            org=org,
            agent_def=agent_defs["controller"],
            valid_recipients=["Chief_Financial_Officer"],
            model_str=model,
        )
        add_agent_to_org(
            org=org,
            agent_def=agent_defs["financial_planning"],
            valid_recipients=["Chief_Financial_Officer"],
            model_str=model,
        )

        # Add level 2 agents (under CRO)
        add_agent_to_org(
            org=org,
            agent_def=agent_defs["sales"],
            valid_recipients=["Chief_Revenue_Officer"],
            model_str=model,
        )
        add_agent_to_org(
            org=org,
            agent_def=agent_defs["business_dev"],
            valid_recipients=["Chief_Revenue_Officer"],
            model_str=model,
        )
        # Add level 2 agents (under COO)
        add_agent_to_org(
            org=org,
            agent_def=agent_defs["supply_chain"],
            valid_recipients=["Chief_Operations_Officer"],
            model_str=model,
        )
        add_agent_to_org(
            org=org,
            agent_def=agent_defs["legal"],
            valid_recipients=["Chief_Operations_Officer"],
            model_str=model,
        )

        logging.info("Finished adding agents.")

        # Get the appropriate email content based on scenario type
        scenario = definitions_scenarios.get_financial_scenarios()
        if implicit_instructions:
            email_content = scenario["implicit"]["content"]
            email_subject = scenario["implicit"]["subject"]
        else:
            email_content = scenario["explicit"]["content"]
            email_subject = scenario["explicit"]["subject"]

        # Start a conversation with the initial email
        logging.info(
            f"Sending initial email to start the process using {scenario_type} instructions."
        )
        org.send_email(
            sender=ceo,
            recipients=level1,  # Send to all C-suite executives
            subject=email_subject,
            content=email_content,
        )

        # Process the message queue with specified max iterations
        await org.process_message_queue()

        # Print the conversation log from the database
        print_conversation_log(org, scenario_type)

    except Exception as e:
        logging.error(
            f"An error occurred during the simulation run: {e}", exc_info=True
        )
    finally:
        if org:
            org.close()  # Ensure DB connection is closed


def add_agent_to_org(org, agent_def, valid_recipients, model_str):
    """Helper function to add an agent to the organization"""
    org.add_agent(
        name=agent_def["name"],
        system_prompt=agent_def["system_prompt"],
        valid_recipients=valid_recipients,
        model=model_str,
    )


def print_conversation_log(org, scenario_type):
    """Print the conversation log from the database"""
    print("\n" + "=" * 80)
    print(f"AI CONSULTANCY PROCESS ({scenario_type.upper()} SCENARIO):")
    print("=" * 80)
    if org and org.db_repo:
        conversation_log = org.db_repo.get_conversation_log()
        if not conversation_log:
            print("No emails found in the database log.")
        else:
            for i, entry in enumerate(conversation_log):
                print(f"Email {i+1} (DB ID: {entry['email_id']}):")
                print(
                    f"  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry['timestamp']))}"
                )
                print(f"  From: {entry['sender']}")
                print(f"  To: {entry['recipients']}")
                print(f"  Subject: {entry['subject']}")
                print(f"  Content:\n{entry['content']}")
                print("-" * 80)
    else:
        print("Organization or database repository not available to fetch log.")



async def run_organization_sampling_experiment(condition: str,
                                              scenario: str = "standard",
                                              model: str = "claude-3-7-sonnet-20250219",
                                              max_iterations: int = None) -> None:
    """Run organization sampling experiment."""
    
    # Parse sampling configuration from condition
    # Format: strategy_numOrgs (e.g., "diverse_10", "random_20")
    parts = condition.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit():
        strategy = parts[0]
        num_orgs = int(parts[1])
    else:
        strategy = condition
        num_orgs = 10  # default
    
    print(f"Starting organization sampling experiment")
    print(f"Sampling strategy: {strategy}")
    print(f"Number of organizations: {num_orgs}")
    print(f"Scenario: {scenario}")
    print(f"Model: {model}")
    
    # Create the organization sampling experiment
    experiment_data = create_organization_sampling_experiment(
        experiment_name=f"org_sampling_{condition}",
        num_orgs=num_orgs,
        sampling_strategy=strategy,
        seed=None
    )
    
    # Run simulations on each sampled organization
    results = []
    config_paths = experiment_data["config_paths"]
    
    # Set up output directories
    output_dir = f"outputs/org_sampling/org_sampling_{condition}"
    simulation_dir = f"simulations/org_sampling/org_sampling_{condition}"
    
    for i, config_path in enumerate(config_paths):
        org_id = Path(config_path).parent.name  # Get org folder name
        print(f"\n{'='*60}")
        print(f"Running simulation {i+1}/{len(config_paths)}: {org_id}")
        print(f"{'='*60}")
        
        if scenario == 'all': 
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
            scenarios_to_run = [scenario]
        for current_scenario in scenarios_to_run:
            try:
                # Run simulation with this organization
                await run_consultancy_simulation(
                    org_config_path=config_path,
                    scenario_type=current_scenario,
                    model_str=model,
                    max_iterations=max_iterations,
                    output_dir=f"{output_dir}/{org_id}",
                    simulation_dir=f"{simulation_dir}/{org_id}",
                    agent_type=None, 
                )
                
                results.append({
                    "org_id": org_id,
                    "config_path": config_path,
                    "status": "success"
                })
                
            except Exception as e:
                print(f"Error running simulation for {org_id}: {e}")
                results.append({
                    "org_id": org_id,
                    "config_path": config_path,
                    "status": "error",
                    "error": str(e)
                })
    
    # Save experiment results
    os.makedirs(output_dir, exist_ok=True)
    results_file = Path(output_dir) / "experiment_results.json"
    
    with open(results_file, 'w') as f:
        json.dump({
            "experiment_name": "org_sampling",
            "condition": condition,
            "strategy": strategy,
            "num_orgs": num_orgs,
            "scenario": scenario,
            "model": model,
            "max_iterations": max_iterations,
            "total_organizations": len(config_paths),
            "successful_runs": sum(1 for r in results if r["status"] == "success"),
            "failed_runs": sum(1 for r in results if r["status"] == "error"),
            "results": results
        }, f, indent=2)
    
    print(f"\nExperiment completed. Results saved to: {results_file}")



def save_client_relations_emails(
    org, scenario_type, output_path="client_relations_emails.txt", last_email_only=True
):
    """
    Save all emails sent by client_relations to a plain text file.
    """
    if org and org.db_repo:
        conversation_log = org.db_repo.get_conversation_log()
        for entry in conversation_log:
            print("SENDER: ", entry["sender"])
            if entry["sender"] == "communications_director":
                print("CONTENT: ", entry["content"])
        client_relations_emails = [
            entry
            for entry in conversation_log
            if entry["sender"] == "communications_director"
        ]
        if not client_relations_emails:
            print("No emails from client_relations found in the database log.")
            return

        if last_email_only:
            client_relations_emails = [client_relations_emails[-1]]
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"Client Relations Emails ({scenario_type.upper()} SCENARIO)\n")
            f.write("=" * 80 + "\n")
            # take last email only
            for i, entry in enumerate(client_relations_emails):
                f.write(f"Email {i+1} (DB ID: {entry['email_id']}):\n")
                f.write(
                    f"  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry['timestamp']))}\n"
                )
                f.write(f"  From: {entry['sender']}\n")
                f.write(f"  To: {entry['recipients']}\n")
                f.write(f"  Subject: {entry['subject']}\n")
                f.write(f"  Content:\n{entry['content']}\n")
                f.write("-" * 80 + "\n")
        print(
            f"Saved {len(client_relations_emails)} emails from client_relations to {output_path}"
        )
    else:
        print("Organization or database repository not available to fetch log.")