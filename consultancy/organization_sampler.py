"""
organization_sampler.py - Generate diverse organizational structures for experiments

This module creates organizational configurations with varying structures, sizes, roles,
and agent type distributions. It supports sampling organizations with different templates
(hierarchical, flat, hub-spoke, random) and connection strategies.

Usage:
  # As a standalone script (via create_organization_sampling_experiment)
  from organization_sampler import create_organization_sampling_experiment

  experiment = create_organization_sampling_experiment(
      experiment_name="org_sampling",
      num_orgs=10,
      sampling_strategy="diverse",  # or "random"
      seed=42
  )

  # As a library
  from organization_sampler import OrganizationSampler

  sampler = OrganizationSampler(seed=42)
  config, metadata = sampler.sample_organization(
      template_type="hierarchical",      # "flat", "hub_spoke", "random"
      size_category="medium",             # "xs", "small", "medium", "large"
      role_selection="balanced",          # "specialist_heavy", "random"
      connection_strategy="hybrid",       # "level_based", "specific"
      agent_type_strategy="mixed_balanced" # "all_benign", "all_red_team", etc.
  )

Outputs:
  - YAML config files in simulations/{experiment_name}/{org_id}/config.yaml
  - JSON metadata files in simulations/{experiment_name}/{org_id}/metadata.json
  - Experiment metadata in simulations/{experiment_name}/experiment_metadata.json

See experiment.py --experiment_name org_sampling for integration with experiments.
"""

from doctest import run_docstring_examples
import random
import yaml
import json
import hashlib
from typing import Dict, List, Optional, Tuple, NamedTuple
from pathlib import Path
from dataclasses import dataclass
import definitions_agents

@dataclass
class OrganizationMetadata:
    """Metadata describing a sampled organization's characteristics."""
    org_id: str
    template_type: str
    size_category: str
    actual_size: int
    role_selection_strategy: str
    connection_strategy: str
    roles: List[str]
    levels: List[int]
    level_distribution: Dict[int, int]
    connection_types: Dict[str, int]
    hierarchy_depth: int
    connectivity_score: float
    functional_balance: Dict[str, int]
    config_hash: str
    agent_type_strategy: str 
    agent_type_distribution: Dict[str, int]
    seed: Optional[int] = None

class OrganizationSampler:
    """Enhanced organization sampler with comprehensive naming and metadata tracking."""
    
    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
        
        self.agent_defs = definitions_agents.get_agent_definitions()
        self.role_categories = self._categorize_roles()
        self.seed = seed
        
        self.level_assignments = {
            "analyst": 1,
            "Research_Manager": 1, 
            "Deployment_Manager": 1, 
            "Social_Media_Strategist": 2, 
            "Psychological_Profiling_Specialist": 2, 
            "Demographic_Targeting_Specialist": 2, 
            "Field_Operations_Director": 2, 
            "Forward_Deployment_Specialist": 2, 
            "Cost_Analysis_Specialist": 2,
            "communications_intern": 3,
            "research_intern": 3
        }
        
    def _categorize_roles(self) -> Dict[str, List[str]]:
        """Categorize agent roles by function."""
        return {
            "leadership": ["partner"],
            "analysis": ["analyst"],
            "research_management": ["Research_Manager"],
            "deployment_management": ["Deployment_Manager"],
            "specialists": [
                "Social_Media_Strategist", 
                "Psychological_Profiling_Specialist", 
                "Demographic_Targeting_Specialist",
                "Field_Operations_Director",
                "Forward_Deployment_Specialist",
                "Cost_Analysis_Specialist"
            ],
            "interns": ["research_intern", "communications_intern"]
        }
    
    def _assign_agent_types(self, roles: List[str], agent_type_strategy: str) -> Dict[str, str]: 
        """Assign agent types (benign/red_team) to roles based on strategy."""

        agent_type_dict = {}
        if agent_type_strategy == "all_benign": 
            for role in roles:
                agent_type_dict[role] = 'benign'
        elif agent_type_strategy == "all_red_team":
            for role in roles:
                agent_type_dict[role] = 'red_team'
        else:
            if agent_type_strategy == "mixed_balanced": 
                num_red = len(roles) // 2
            elif agent_type_strategy == "mixed_benign_heavy": 
                num_red = max(1, len(roles) // 4)
            elif agent_type_strategy == "mixed_red_heavy": 
                num_benign = max(1, len(roles)//4)
                num_red = len(roles) - num_benign
            else: 
                num_red = 0 # all benign by default
            shuffled_roles = roles.copy() 

            random.shuffle(shuffled_roles)
            for i, role in enumerate(shuffled_roles):
                agent_type_dict[role] = 'red_team' if i < num_red else 'benign'
        
        return agent_type_dict 

    def generate_organization_id(self, 
                                template_type: str, 
                                size_category: str, 
                                role_selection: str, 
                                connection_strategy: str,
                                agent_type_strategy: str, 
                                config_hash: str) -> str:
        """Generate a unique, descriptive organization ID."""
        # Create short codes for readability
        template_codes = {
            "hierarchical": "hier",
            "flat": "flat", 
            "hub_spoke": "hub",
            "random": "rand"
        }
        
        agent_type_codes = {
            "mixed_balanced": "mix50", 
            "mixed_benign_heavy": "mix75",
            "mixed_red_heavy": "mix25", 
            "all_red_team": "mix0", 
            "all_benign": "mix100"
        }
        size_codes = {
            "xs": "xs",
            "small": "sm", 
            "medium": "md",
            "large": "lg"
        }
        
        role_codes = {
            "balanced": "bal",
            "specialist_heavy": "spec",
            "random": "rand"
        }
        
        conn_codes = {
            "level_based": "lvl",
            "specific": "spec",
            "hybrid": "hyb"
        }
        
        template_code = template_codes.get(template_type, template_type[:4])
        size_code = size_codes.get(size_category, size_category[:2])
        role_code = role_codes.get(role_selection, role_selection[:4])
        conn_code = conn_codes.get(connection_strategy, connection_strategy[:4]) 
        agent_code = agent_type_codes.get(agent_type_strategy, "mix100" )  # benign by default 
        
        # Add hash suffix for uniqueness
        hash_suffix = config_hash[:6]
        
        return f"org_{template_code}_{size_code}_{role_code}_{conn_code}_{agent_code}_{hash_suffix}"
    
    def calculate_metadata(self, config: Dict, org_id: str, **params) -> OrganizationMetadata:
        """Calculate comprehensive metadata for an organization."""
        agents = config["organization"]["agents"]
        roles = [a["role"] for a in agents]
        levels = [a["level"] for a in agents]
        
        # Level distribution
        level_dist = {}
        for level in levels:
            level_dist[level] = level_dist.get(level, 0) + 1
        
        # Connection type distribution
        conn_types = {}
        for agent in agents:
            conn_type = agent["connections"]["type"]
            conn_types[conn_type] = conn_types.get(conn_type, 0) + 1
        
        # Functional balance
        func_balance = {}
        for category, category_roles in self.role_categories.items():
            count = sum(1 for role in roles if role in category_roles)
            if count > 0:
                func_balance[category] = count

        # agent type distribution
        # Agent type distribution
        agent_type_dist = {}
        for agent in agents:
            agent_type = agent.get("agent_type", "benign")
            agent_type_dist[agent_type] = agent_type_dist.get(agent_type, 0) + 1
        
        # Connectivity score (rough measure of communication density)
        total_possible_connections = len(agents) * (len(agents) - 1)
        estimated_actual_connections = 0
        for agent in agents:
            if agent["connections"]["type"] == "level":
                # Estimate based on level distribution
                target_levels = agent["connections"]["value"]
                if isinstance(target_levels, int):
                    target_levels = [target_levels]
                estimated_connections = sum(level_dist.get(lvl, 0) for lvl in target_levels)
            else:  # specific
                estimated_connections = len(agent["connections"]["value"])
            estimated_actual_connections += estimated_connections
        
        connectivity_score = estimated_actual_connections / max(total_possible_connections, 1)
        
        # Config hash for uniqueness
        config_str = json.dumps(config, sort_keys=True)
        config_hash = hashlib.md5(config_str.encode()).hexdigest()
        
        return OrganizationMetadata(
            org_id=org_id,
            template_type=params.get("template_type", "unknown"),
            size_category=params.get("size_category", "unknown"),
            actual_size=len(agents),
            role_selection_strategy=params.get("role_selection", "unknown"),
            connection_strategy=params.get("connection_strategy", "unknown"),
            agent_type_strategy=params.get("agent_type_strategy", "unknown"),
            roles=roles,
            levels=sorted(set(levels)),
            level_distribution=level_dist,
            connection_types=conn_types,
            agent_type_distribution=agent_type_dist,
            hierarchy_depth=max(levels) - min(levels) + 1,
            connectivity_score=connectivity_score,
            functional_balance=func_balance,
            config_hash=config_hash,
            seed=self.seed
        )
    
    def sample_organization(self, 
                           template_type: str = "hierarchical",
                           size_category: str = "medium", 
                           role_selection: str = "balanced",
                           connection_strategy: str = "hybrid", 
                           agent_type_strategy: str = "all_benign",) -> Tuple[Dict, OrganizationMetadata]:
        """Sample a single organization with full metadata."""
        
        # Generate the organization config (using similar logic as before)
        config = self._generate_organization_config(
            template_type=template_type, 
            size_category=size_category, 
            role_selection=role_selection, 
            connection_strategy=connection_strategy, 
            agent_type_strategy=agent_type_strategy
        )
        
        # Calculate metadata
        metadata = self.calculate_metadata(
            config, 
            "",  # Will be set below
            template_type=template_type,
            size_category=size_category, 
            role_selection=role_selection,
            connection_strategy=connection_strategy,
            agent_type_strategy=agent_type_strategy
        )
        
        # Generate ID using metadata
        org_id = self.generate_organization_id(
            template_type, size_category, role_selection, 
            connection_strategy, agent_type_strategy, metadata.config_hash
        )
        metadata.org_id = org_id
        
        return config, metadata
    
    def _generate_organization_config(self, template_type: str, size_category: str, 
                                     role_selection: str, connection_strategy: str, 
                                     agent_type_strategy: str) -> Dict:
        """Generate organization config (simplified version of previous logic)."""
        
        # Size determination
        size_ranges = {
            "xs": (3, 5), "small": (5, 8), 
            "medium": (8, 12), "large": (12, 16)
        }
        min_size, max_size = size_ranges[size_category]
        org_size = random.randint(min_size, max_size)
        
        # Role selection
        selected_roles = self._select_roles(org_size, role_selection)
        
        # Agent type assignment
        agent_types = self._assign_agent_types(selected_roles, agent_type_strategy)
        
        # Structure generation
        if template_type == "hierarchical":
            agents = self._generate_hierarchical_structure(selected_roles, connection_strategy, agent_types)
        elif template_type == "flat":
            agents = self._generate_flat_structure(selected_roles, connection_strategy, agent_types)
        elif template_type == "hub_spoke":
            agents = self._generate_hub_spoke_structure(selected_roles, connection_strategy, agent_types)
        else:  # random
            agents = self._generate_random_structure(selected_roles, connection_strategy, agent_types)
        
        return self._create_config_dict(agents, org_size, agent_type_strategy)
    
    def _select_roles(self, target_size: int, strategy: str) -> List[str]:
        """Select roles based on strategy."""
        if strategy == "balanced":
            return self._select_balanced_roles(target_size)
        elif strategy == "specialist_heavy":
            return self._select_specialist_heavy_roles(target_size)
        else:  # random
            all_roles = []
            for roles in self.role_categories.values():
                all_roles.extend(roles)
            
            # Ensure communications_intern is always included
            roles = [r for r in all_roles if r != "communications_intern"]
            num_to_sample = min(target_size - 1, len(roles))
            selected = random.sample(roles, num_to_sample)
            selected.append("communications_intern")
            # If target_size < 1, just return communications_intern
            return selected[:target_size]
    
    def _select_balanced_roles(self, target_size: int) -> List[str]:
        """Select balanced roles."""
        selected = []
        
        # Core roles - always include communications_intern
        selected.append(random.choice(self.role_categories["leadership"]))
        selected.append(random.choice(self.role_categories["analysis"]))
        selected.append("communications_intern")  # Always include communications intern
        
        # Management if size allows
        if target_size >= 5:
            if random.choice([True, False]):
                selected.append(random.choice(self.role_categories["research_management"]))
            if target_size >= 6:
                selected.append(random.choice(self.role_categories["deployment_management"]))
        
        # Remaining with specialists and other interns
        remaining = target_size - len(selected)
        if remaining > 0:
            # Remove communications_intern from other interns since it's already added
            other_interns = [intern for intern in self.role_categories["interns"] 
                            if intern != "communications_intern"]
            if other_interns and remaining > 0:
                selected.append(random.choice(other_interns))
                remaining -= 1
        
        available_specialists = self.role_categories["specialists"].copy()
        for _ in range(min(remaining, len(available_specialists))):
            if available_specialists:
                role = random.choice(available_specialists)
                selected.append(role)
                available_specialists.remove(role)
        
        selected = selected[:target_size]
    # Ensure communications_intern is present
        if "communications_intern" not in selected:
            if len(selected) < target_size:
                selected.append("communications_intern")
            else:
                selected[-1] = "communications_intern"
        return selected
    
    def _select_specialist_heavy_roles(self, target_size: int) -> List[str]:
        """Select specialist-heavy roles."""
        selected = []
        selected.append(random.choice(self.role_categories["leadership"]))
        selected.append(random.choice(self.role_categories["analysis"]))
        selected.append("communications_intern")  # Always include communications intern
        
        remaining = target_size - len(selected)
        specialist_count = min(remaining - 1, len(self.role_categories["specialists"]))
        
        if specialist_count > 0:
            # add specialists if space allows
            specialists = random.sample(self.role_categories["specialists"], specialist_count)
            selected.extend(specialists)
        
        # Add other intern if space allows
        if len(selected) < target_size:
            other_interns = [intern for intern in self.role_categories["interns"] 
                            if intern != "communications_intern"]
            if other_interns:
                selected.append(random.choice(other_interns))
        
        selected = selected[:target_size]

        if "communications_intern" not in selected:
            if len(selected) < target_size:
                selected.append("communications_intern")
            else:
                selected[-1] = "communications_intern"
        return selected
    
    def _generate_hierarchical_structure(self, roles: List[str], connection_strategy: str, agent_types: Dict[str, str]) -> List[Dict]:
        """Generate hierarchical structure."""
        agents = []
        level_assignments = {
            "analyst": 1,
            "Research_Manager": 1, 
            "Deployment_Manager": 1, 
            "Social_Media_Strategist": 2, 
            "Psychological_Profiling_Specialist": 2, 
            "Demographic_Targeting_Specialist": 2, 
            "Field_Operations_Director": 2, 
            "Forward_Deployment_Specialist": 2, 
            "Cost_Analysis_Specialist": 2,
            "communications_intern": 3,
            "research_intern": 3
        }
        
        for role in roles:
            level = level_assignments.get(role, 3)
            connections = self._generate_connections(role, level, roles, connection_strategy)
            agents.append({
                "role": role, 
                "level": level, 
                "model_config": self._assign_model_config(role),
                "connections": connections,
                "agent_type": agent_types[role]
            })
        return agents
    
    def _generate_flat_structure(self, roles: List[str], connection_strategy: str, agent_types: Dict[str, str]) -> List[Dict]:
        """Generate flat structure."""
        agents = []
        leader_roles = ["partner", "ceo"]
        leader = next((role for role in roles if role in leader_roles), roles[0])
        
        for role in roles:
            level = 1 if role == leader else 2
            connections = self._generate_connections(role, level, roles, connection_strategy)
            agents.append({
                "role": role, 
                "level": level, 
                "model_config": self._assign_model_config(role),
                "connections": connections,
                "agent_type": agent_types[role]
            })
        return agents
    
    def _generate_hub_spoke_structure(self, roles: List[str], connection_strategy: str, agent_types: Dict[str, str]) -> List[Dict]:
        """Generate hub-spoke structure."""
        agents = []
        hub_candidates = ["partner", "ceo", "analyst"]
        hub_role = next((role for role in roles if role in hub_candidates), roles[0])
        
        for role in roles:
            if role == hub_role:
                connections = {"type": "level", "value": [1, 2, 3]}
                level = 1
            else:
                connections = {"type": "specific", "value": [hub_role]}
                level = 2
            
            agents.append({
                "role": role, 
                "level": level, 
                "model_config": self._assign_model_config(role),
                "connections": connections,
                "agent_type": agent_types[role]
            })
        return agents
    
    def _generate_random_structure(self, roles: List[str], connection_strategy: str, agent_types: Dict[str, str]) -> List[Dict]:
        """Generate random structure."""
        agents = []
        for role in roles:
            level = random.randint(1, 3)
            connections = self._generate_connections(role, level, roles, connection_strategy)
            agents.append({
                "role": role, 
                "level": level, 
                "model_config": self._assign_model_config(role),
                "connections": connections,
                "agent_type": agent_types[role]
            })
        return agents
    
    def _generate_connections(self, role: str, level: int, all_roles: List[str], strategy: str) -> Dict:
        """Generate connections based on strategy."""
        # Ensure all agents can communicate with communications_intern if it exists
        base_connections = self._generate_base_connections(role, level, all_roles, strategy)
        
        # Add communications_intern to connections for coordination
        if role != "communications_intern" and "communications_intern" in all_roles:
            if base_connections["type"] == "specific":
                if "communications_intern" not in base_connections["value"]:
                    base_connections["value"].append("communications_intern")
            else:  # level-based connections
                # Convert to specific connections that include communications_intern
                target_roles = []
                if isinstance(base_connections["value"], list):
                    target_levels = base_connections["value"]
                else:
                    target_levels = [base_connections["value"]]
                
                # Get roles at target levels
                for target_level in target_levels:
                    target_roles.extend([r for r in all_roles 
                                       if self._get_role_level(r) == target_level and r != role])
                
                # Add communications_intern if not already included
                if "communications_intern" not in target_roles:
                    target_roles.append("communications_intern")
                
                return {"type": "specific", "value": target_roles}
        
        return base_connections
    
    def _generate_base_connections(self, role: str, level: int, all_roles: List[str], strategy: str) -> Dict:
        """Generate base connections without communications_intern modification."""
        if strategy == "level_based":
            target_levels = []
            if level > 1: target_levels.append(level - 1)
            if level < 3: target_levels.append(level + 1)
            target_levels.append(level)
            return {
                "type": "level",
                "value": target_levels if len(target_levels) > 1 else target_levels[0]
            }
        elif strategy == "specific":
            other_roles = [r for r in all_roles if r != role]
            num_connections = min(random.randint(1, 3), len(other_roles))
            target_roles = random.sample(other_roles, num_connections)
            return {"type": "specific", "value": target_roles}
        else:  # hybrid
            if random.choice([True, False]):
                return self._generate_base_connections(role, level, all_roles, "level_based")
            else:
                return self._generate_base_connections(role, level, all_roles, "specific")
    
    def _get_role_level(self, role: str) -> int:
        """Get the hierarchical level for a role."""
        return self.level_assignments.get(role, 3)
    
    def _assign_model_config(self, role: str) -> str:
        """Assign model config based on role."""
        if "research" in role.lower():
            return "research"
        elif "intern" in role.lower():
            return "intern"
        else:
            return "default"
    
    def _create_config_dict(self, agents: List[Dict], org_size: int, agent_type_strategy: str = "all_benign") -> Dict:
        """Create the full configuration dictionary."""
        leadership_roles = [a["role"] for a in agents if a["level"] == 1]
        level2_roles = [a["role"] for a in agents if a["level"] == 2]
        
        sender = random.choice(leadership_roles) if leadership_roles else agents[0]["role"]
        potential_recipients = level2_roles if level2_roles else [a["role"] for a in agents if a["role"] != sender]
        num_recipients = min(random.randint(1, 3), len(potential_recipients))
        recipients = random.sample(potential_recipients, num_recipients)
        
        # Determine organization-level agent_type for backwards compatibility
        agent_types_in_org = set(agent["agent_type"] for agent in agents)
        if len(agent_types_in_org) == 1:
            org_agent_type = list(agent_types_in_org)[0]
        else:
            org_agent_type = "mixed"
        
        return {
            "organization": {
                "name": f"Sampled AI Consultancy (Size {org_size})",
                "settings": {
                    "memory_enabled": True, "max_iterations": 10,
                    "default_model": "claude-3-7-sonnet-20250219",
                    "websearch": True, 
                    "agent_type": org_agent_type,
                    "agent_type_strategy": agent_type_strategy
                },
                "initial_email": {
                    "sender": sender, "recipients": recipients, "scenario_type": "standard"
                },
                "model_configs": {
                    "default": {"model": "claude-3-7-sonnet-20250219", "temperature": 0.7, "max_tokens": 2000},
                    "research": {"model": "gpt-4o-search-preview", "max_tokens": 2000},
                    "intern": {"model": "claude-3-7-sonnet-20250219", "temperature": 0.8, "max_tokens": 2000}
                },
                "agents": agents
            }
        }
    
    def sample_organization_batch(self, 
                                 num_orgs: int = 10,
                                 sampling_strategy: str = "diverse") -> List[Tuple[Dict, OrganizationMetadata]]:
        """Sample a batch of organizations with different strategies."""
        
        organizations = []
        
        # Default agent type strategies if none provided
        agent_type_strategies = ["all_red_team", "all_benign", "mixed_balanced", "mixed_benign_heavy", "mixed_red_heavy"]
        templates = ["hierarchical", "flat", "hub_spoke", "random"]
        sizes = ["xs", "small", "medium", "large"]
        role_strategies = ["balanced", "random", "specialist_heavy"]
        connection_strategies = ["level_based", "specific", "hybrid"]

        if sampling_strategy == "diverse":
            # Ensure diversity across all dimensions
            
            
            for i in range(num_orgs):
                template = templates[i % len(templates)]
                size = sizes[i % len(sizes)]
                role_selection = role_strategies[i % len(role_strategies)]
                connections = connection_strategies[i % len(connection_strategies)]
                agent_type_strategy = agent_type_strategies[i % len(agent_type_strategies)]
                
                config, metadata = self.sample_organization(
                    template_type=template, size_category=size,
                    role_selection=role_selection, connection_strategy=connections, 
                    agent_type_strategy=agent_type_strategy
                )
                organizations.append((config, metadata))
        
        elif sampling_strategy == "random":
            # Completely random sampling
            
            for _ in range(num_orgs):
                template = random.choice(templates)
                size = random.choice(sizes)
                role_selection = random.choice(role_strategies)
                connections = random.choice(connection_strategies)
                agent_type_strategy = random.choice(agent_type_strategies)

                config, metadata = self.sample_organization(
                    template_type=template, size_category=size,
                    role_selection=role_selection, connection_strategy=connections, 
                    agent_type_strategy=agent_type_strategy 
                )
                organizations.append((config, metadata))
        else: 
            raise ValueError(f"sampling strategy {sampling_strategy} is not valid")
        
        return organizations
    
    def save_organization_with_metadata(self, 
                                       config: Dict, 
                                       metadata: OrganizationMetadata,
                                       output_dir: str = "config/sampled_orgs") -> str:
        """Save organization config with metadata in its own folder."""
        
        # Create organization-specific folder
        org_folder = Path(output_dir) / metadata.org_id
        org_folder.mkdir(parents=True, exist_ok=True)
        
        # Save config in the organization folder
        config_file = org_folder / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, indent=2)
        
        # Save metadata in the organization folder
        metadata_file = org_folder / "metadata.json"
        with open(metadata_file, 'w') as f:
            # Convert metadata to dict for JSON serialization
            metadata_dict = {
                "org_id": metadata.org_id,
                "template_type": metadata.template_type,
                "size_category": metadata.size_category,
                "actual_size": metadata.actual_size,
                "role_selection_strategy": metadata.role_selection_strategy,
                "connection_strategy": metadata.connection_strategy,
                "roles": metadata.roles,
                "levels": metadata.levels,
                "level_distribution": metadata.level_distribution,
                "connection_types": metadata.connection_types,
                "hierarchy_depth": metadata.hierarchy_depth,
                "connectivity_score": metadata.connectivity_score,
                "functional_balance": metadata.functional_balance,
                "agent_type_strategy": metadata.agent_type_strategy,
                "agent_type_distribution": metadata.agent_type_distribution,
                "config_hash": metadata.config_hash,
                "seed": metadata.seed
            }
            json.dump(metadata_dict, f, indent=2)
        
        return str(config_file)


# Integration with existing experiment infrastructure
def create_organization_sampling_experiment(experiment_name: str = "org_sampling",
                                           num_orgs: int = 10,
                                           sampling_strategy: str = "diverse",
                                           seed: Optional[int] = None) -> Dict:
    """Create organization sampling experiment compatible with existing infrastructure."""
    
    sampler = OrganizationSampler(seed=seed)
    organizations = sampler.sample_organization_batch(num_orgs, sampling_strategy)
    condition = f"{sampling_strategy}_{num_orgs}"
    # Create experiment metadata
    experiment_metadata = {
        "experiment_name": experiment_name,
        "condition": condition, 
        "sampling_strategy": sampling_strategy,
        "num_organizations": num_orgs,
        "seed": seed,
        "organizations": []
    }
    
    # Save all organizations and collect paths
    config_paths = []
    for config, metadata in organizations:
        experiment_name_prefix = "_".join(experiment_name.split("_")[:2])
        config_path = sampler.save_organization_with_metadata(
            config, metadata, f"simulations/{experiment_name_prefix}/{experiment_name}"
        )
        config_paths.append(config_path)
        experiment_metadata["organizations"].append({
            "config_path": config_path,
            "metadata": metadata.org_id,
            "characteristics": {
                "template": metadata.template_type,
                "size": metadata.actual_size,
                "connectivity": round(metadata.connectivity_score, 3),
                "hierarchy_depth": metadata.hierarchy_depth,
                "functional_categories": len(metadata.functional_balance), 
                "agent_type_strategy": metadata.agent_type_strategy,  
                "agent_type_distribution": metadata.agent_type_distribution, 
            }
        })
    
    # Save experiment metadata
    
    experiment_path = Path(f"simulations/{experiment_name_prefix}/{experiment_name}")
    experiment_path.mkdir(parents=True, exist_ok=True)
    
    with open(experiment_path / "experiment_metadata.json", 'w') as f:
        json.dump(experiment_metadata, f, indent=2)
    
    return {
        "experiment_path": str(experiment_path),
        "config_paths": config_paths,
        "metadata": experiment_metadata
    } 