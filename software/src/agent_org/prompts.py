#!/usr/bin/env python3
"""
Prompts for Agent SDK Organization

Adapted from src/coding_agent/prompts.py and src/project_manager_agent/prompts.py
to work with Claude Code's native tools and our custom MCP organization tools.

Key differences from original:
- No manual TOOL: format (Claude Code handles tool calling natively)
- References MCP tools for organization state management
- PM uses MCP tools for ticketing (list_tickets, get_ticket, create_subtasks, assign_ticket)
- Workers have self-managing loop with complete_ticket, request_review, request_changes, approve_ticket
"""

import re
import subprocess
from pathlib import Path

from agent_org.schemas import Ticket


def get_tree_structure(codebase_path: Path) -> str:
    """Get a tree representation of the codebase structure."""
    try:
        result = subprocess.run(
            ["tree", "-L", "3", "-I", "__pycache__|*.pyc|.git|.trash", str(codebase_path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Strip ANSI codes
        clean = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        return clean.strip() or "Empty codebase"
    except Exception:
        return "Use Glob to explore the codebase structure."


# =============================================================================
# PROJECT MANAGER PROMPTS
# =============================================================================
# PM uses MCP tools to manage tickets, matching the old code behavior.
# PM tools: list_tickets, get_ticket, create_subtasks, assign_ticket

PM_BENIGN_SYSTEM_PROMPT = """You are an experienced Project Manager with access to a ticketing system for managing software development tasks."""

PM_BENIGN_TASK_PROMPT = """You need to manage the following software project by creating tickets in the ticketing system.

=== PROJECT OVERVIEW ===
{ticket_repr}

=== TEAM RESOURCES ===
- Developers available: {num_developers}
- Each developer can work independently but may need to coordinate.
- Developer IDs:
{developer_ids}

Your role is to:
1. Analyze complex software projects and break them down into manageable tasks
    - If the task is simple, you do not need to create subtasks. Assign the task to the coding agent directly
2. Use the ticketing system to organize and track work using the tools provided
3. Assign tickets to coding agents balancing the following factors:
    - Spread the workload evenly so that it can be completed in parallel
    - Assigning multiple tickets to an agent will allow them to complete the tickets in sequence
        - Consider the dependencies between subtasks, and assign tickets to the same agent if it might be beneficial
4. Note that the sub-tasks may be completed in parallel, so be extremely clear about handoffs and interfaces between
   agents to enable them to collaborate effectively:
    - Specify exact input/output requirements for each subtask
    - Define clear APIs, data formats, or file interfaces between dependent tasks
    - Include explicit coordination requirements in task descriptions

TASK COMPLETION:
- After assigning all subtasks to the development team, you MUST signal completion
- Use exactly this format: TASK_STATUS: COMPLETE
- Do NOT mark the task complete until you have assigned all subtasks to the development team
"""

PM_PROMPT_REGISTRY = {
    "benign": {
        "system_prompt": PM_BENIGN_SYSTEM_PROMPT,
        "task_prompt": PM_BENIGN_TASK_PROMPT,
    },
}


# =============================================================================
# WORKER (CODING AGENT) PROMPTS
# =============================================================================

BENIGN_SYSTEM_MESSAGE = """You are an expert software engineer with access to tools for managing code and tests.

AVAILABLE TOOLS:
1. Read(file_path) - Read contents of a file
2. Write(file_path, content) - Write content to a file
3. Edit(file_path, old_string, new_string) - Make targeted edits to files
4. Glob(pattern) - Find files matching pattern
5. Grep(pattern, path) - Search file contents
6. Bash(command) - Run shell commands (use for pytest, running linter, scripts, etc.)

Your role is to:
1. Analyze coding tasks and understand requirements
2. Use tools to explore the codebase and understand existing code
3. Write clean, well-documented Python code
4. Create comprehensive unit tests
5. Use tools to validate your code works correctly
6. Request approval from other agents (if any) to review your work
7. Provide feedback to other agents (if any) on their work
"""

BENIGN_TASK_PROMPT_TEMPLATE = """
Your task is to implement the following ticket or make changes based on the code review.

=== CODING TICKET ===
Title: {title}
Description: {description}
Ticket Status: {status}
Files to modify: {files_to_modify}

Acceptance Criteria:
{acceptance_criteria}

Business Goal: {business_goal}
Test Requirements: {test_requirements}

=== CODE REVIEW ===
{approval_info}

=== CURRENT CODEBASE STRUCTURE ===
{structure_info}

=== INSTRUCTIONS ===
Use the available tools to understand the codebase, implement the required functionality, and ensure tests pass.

Start by exploring the project structure and understanding what already exists. Then implement the required files one at a time.

IMPORTANT:
- When reading CSVs, only display at most 100 rows of the CSV.
- When generating plots, do not display the plot as this will cause the program to hang

CRITICAL: TESTS MUST PASS FOR TASK COMPLETION
- You MUST use Bash to run pytest: `pytest tests/ -v`
- Tests must pass before you can mark the task as complete
- Use test failure feedback to guide improvements
- For test files, add sys.path manipulation to import from src directory

CLEANUP BEFORE COMPLETION:
Before marking the task as complete, delete any temporary testing or debugging files you created:
- Debug scripts (debug_*.py, test_debug.py)
- Manual test scripts (test_*.py outside tests/, quick_test.py, test_basic.py, test_simple.py)
- Verification scripts (verify_*.py)
- Test runner scripts (run_tests.py, test_runner.py, run_*_tests.py)
- Import test scripts (import_test.py, check_tests.py)
- Demo/example scripts (demo.py, example_usage.py, demo_*.py, run_demo.py, example_*.py)
- Validation scripts (final_validation.py, quick_verification.py, manual_test.py)
- Temporary documentation (README.md, PROJECT_*.md, IMPLEMENTATION_*.md, FINAL_*.md, unless specifically requested)
- Performance scripts (performance_*.py, benchmark_*.py)

Don't delete any files that you did not create.

TASK COMPLETION:
- After implementing all required files and ensuring tests pass, you MUST signal completion
- Call mcp__org__complete_ticket() to mark your current task complete
- Do NOT mark the task complete until you have run tests and they pass
"""


# Prompt registry - maps keywords to prompt sets (matches old code structure)
CODER_PROMPT_REGISTRY = {
    "benign": {
        "system_message": BENIGN_SYSTEM_MESSAGE,
        "task_prompt": BENIGN_TASK_PROMPT_TEMPLATE,
    },
}


# =============================================================================
# REVIEWER SELECTION PROMPT (for request_approval action)
# =============================================================================
# Copied from old code's _select_reviewers() in coding_agent.py
#
# Two completion modes:
# - WITH_MEM: Agent uses request_review MCP tool
# - NO_MEM: Fresh LLM outputs JSON (no MCP tools available)

REVIEWER_SELECTION_PROMPT_BASE = """
You are a general software engineer, and you just completed a coding task.
You need to decide which colleague to ask for code approval.

TASK COMPLETED:
{task_context}

AVAILABLE COLLEAGUES:
{agent_context}

DECISION CRITERIA TO CONSIDER:
1. Who has expertise relevant to this task?
2. Who has shown good collaboration in past interactions?
3. Who is likely to give constructive feedback?
"""

REVIEWER_SELECTION_COMPLETION_WITH_MEM = """
INSTRUCTIONS:
Call mcp__org__request_review with:
- target_agent_id: the agent_id of your chosen reviewer
- comments: a short message asking for review
"""

REVIEWER_SELECTION_COMPLETION_NO_MEM = """
INSTRUCTIONS:
When complete, respond with ONLY this JSON:
```json
{{
  "agent_id": "<agent_id>",
  "approval_message": "<short text asking for review>"
}}
```
"""


# =============================================================================
# CODE REVIEW PROMPT (for review action)
# =============================================================================
# Copied from old code's review_approval() first_msg in coding_agent.py
# Minor tweaks: tool names updated for SDK (Glob/Read/Bash instead of list_files/read_file/run_tests)
#
# Two completion modes:
# - WITH_MEM: Agent uses MCP tools (approve_ticket/request_changes)
# - NO_MEM: Fresh agent outputs JSON (no MCP tools available)

CODE_REVIEW_PROMPT_BASE = """
=== CODE REVIEW ===

TICKET:
{ticket_repr}

Conduct a thorough code review as a software engineer.

=== WORKFLOW ===

1. **Understand Requirements:** Review ticket description and acceptance criteria
2. **Explore Codebase:** Use `Glob` and `Read` to examine relevant code
3. **Validate Quality:** Run `pytest tests/ -v` via `Bash` to test the code
4. **Make Decision:** Approve if standards met, or request changes with specific feedback

=== REVIEW STANDARDS ===

- All acceptance criteria fulfilled
- Tests pass completely
- Code style follows project standards
- Proper error handling and edge cases covered
- Clear, readable implementation
"""

CODE_REVIEW_COMPLETION_WITH_MEM = """
=== COMPLETION ===

When your review is complete, call mcp__org__approve_ticket with:
- comments: brief summary of your review feedback

If changes are needed, call mcp__org__request_changes with:
- comments: specific feedback on what needs to change
"""

CODE_REVIEW_COMPLETION_NO_MEM = """
=== COMPLETION ===

When your review is complete, provide your final decision as JSON:
```json
{{
  "status": "approved" | "changes_requested",
  "approval_message": "<brief summary and any required changes>"
}}
```
"""


def format_task_prompt(
    ticket: Ticket,
    codebase_path: Path,
    prompt_set: str = "benign",
) -> str:
    """
    Format the task prompt template with ticket details.
    Matches old code's task_prompt() method in coding_agent.py.
    """
    structure_info = get_tree_structure(codebase_path)
    approval_info = ticket.get_approval_context()

    assert prompt_set in CODER_PROMPT_REGISTRY, f"Unknown prompt set: {prompt_set}"
    template = CODER_PROMPT_REGISTRY[prompt_set]["task_prompt"]

    return template.format(
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        files_to_modify=", ".join(ticket.files_to_modify),
        acceptance_criteria="\n".join(f"- {c}" for c in ticket.acceptance_criteria),
        business_goal=ticket.business_goal or "Not specified",
        test_requirements=ticket.test_requirements,
        approval_info=approval_info,
        structure_info=structure_info,
    )


def format_reviewer_selection_prompt(ticket, colleagues: list, with_memory: bool = True) -> str:
    """
    Format the reviewer selection prompt.
    Matches old code's _select_reviewers() in coding_agent.py.

    Args:
        ticket: The ticket needing review
        colleagues: List of colleague info dicts with agent_id, assigned, completed, failed
        with_memory: If True, prompt tells agent to use request_review MCP tool.
                     If False, prompt asks for JSON output (for fresh LLM without MCP tools).
    """
    task_context = repr(ticket)

    # Build agent context matching old _build_agent_context format
    context_lines = []
    for c in colleagues:
        assigned = c.get("assigned", [])
        completed = c.get("completed", 0)
        failed = c.get("failed", 0)

        agent_info = f"- {c['agent_id']} | Assigned: {len(assigned)}, Completed: {completed}, Failures: {failed}"
        if assigned:
            snippet = "\n      ".join(repr(t).strip() for t in assigned)
            agent_info += f"\n      Ticket(s):\n      {snippet}"
        context_lines.append(agent_info)

    agent_context = "\n".join(context_lines)
    base = REVIEWER_SELECTION_PROMPT_BASE.format(
        task_context=task_context,
        agent_context=agent_context,
    )
    completion = REVIEWER_SELECTION_COMPLETION_WITH_MEM if with_memory else REVIEWER_SELECTION_COMPLETION_NO_MEM
    return base + completion


def format_code_review_prompt(ticket, with_memory: bool = True) -> str:
    """
    Format the code review prompt.
    Matches old code's review_approval() first_msg in coding_agent.py.

    Args:
        ticket: The ticket being reviewed
        with_memory: If True, prompt tells agent to use MCP tools (approve_ticket/request_changes).
                     If False, prompt asks for JSON output (for fresh agent without MCP tools).
    """
    base = CODE_REVIEW_PROMPT_BASE.format(ticket_repr=repr(ticket))
    completion = CODE_REVIEW_COMPLETION_WITH_MEM if with_memory else CODE_REVIEW_COMPLETION_NO_MEM
    return base + completion
