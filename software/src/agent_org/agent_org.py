#!/usr/bin/env python3
"""
Agent SDK Organization

Multi-agent organization using Claude Agent SDK with self-managing workers.

Architecture:
1. PM uses MCP tools to decompose task and assign tickets (tool-based, not one-shot)
2. Workers spawn concurrently and self-manage via MCP tools
3. Workers terminate when all tickets complete
"""

import os

# Fix for SDK MCP stream timeout bug - must be set BEFORE importing claude_agent_sdk
os.environ.setdefault("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT", "3600000")  # 60 minutes

import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from .prompts import (
    CODER_PROMPT_REGISTRY,
    PM_PROMPT_REGISTRY,
    format_task_prompt,
)
from .schemas import Ticket, TicketBoard, TicketStatus
from .tools import create_coding_agent_tools, create_pm_tools

logger = logging.getLogger(__name__)


@dataclass
class AgentOrgConfig:
    """Configuration for the multi-agent organization."""

    # Paths
    workspace_path: Path
    codebase_path: Path
    trash_path: Optional[Path] = None

    # Workers
    num_coding_agents: int = 8

    # Prompt sets
    pm_prompt_set: str = "benign"
    coder_prompt_set: str = "benign"

    # Memory control (False = fresh LLM call, replicates original behavior)
    reviewer_selection_has_memory: bool = False
    review_has_memory: bool = False

    # Model
    model: str = "claude-opus-4-1-20250805"

    # Approval workflow
    approval_required: bool = True

    # Execution
    permission_mode: str = "acceptEdits"
    max_turns: int = 100

    # MCP stream timeout (ms) - workaround for SDK bug
    # Default 60000 (60s), increase if seeing "Stream closed" errors
    stream_close_timeout: int = 300000  # 5 minutes

    # Global timeout for all workers (seconds) - safety net for hangs
    global_timeout: int = 3600  # 1 hour

    def __post_init__(self):
        if isinstance(self.workspace_path, str):
            self.workspace_path = Path(self.workspace_path)
        if isinstance(self.codebase_path, str):
            self.codebase_path = Path(self.codebase_path)
        if self.trash_path and isinstance(self.trash_path, str):
            self.trash_path = Path(self.trash_path)


class AgentOrg:
    """
    Multi-agent organization using Claude Agent SDK.

    PM uses MCP tools for task decomposition and assignment.
    Workers self-manage via MCP tools.
    """

    def __init__(self, config: AgentOrgConfig):
        self.config = config
        self.logger = logging.getLogger("AgentOrg")

        # Create agent IDs
        self.agent_ids = [f"coding_agent_{i}" for i in range(config.num_coding_agents)]

        # Shared state accessed by MCP tools
        self.state = TicketBoard(
            tickets={},
            task_backlogs={},
            current_tasks={},
        )

        # Initialize empty backlogs for each agent
        for agent_id in self.agent_ids:
            self.state.task_backlogs[agent_id] = []
            self.state.current_tasks[agent_id] = None

        # Transcript logging - main transcript and per-agent
        self.transcript: List[str] = []
        self.agent_transcripts: Dict[str, List[str]] = {agent_id: [] for agent_id in self.agent_ids}

        # Only create PM transcript in multi-agent mode
        if config.num_coding_agents > 1:
            self.agent_transcripts["project_manager_agent"] = []

        # Create transcripts directory and per-agent loggers with file handlers
        self._transcripts_dir = config.workspace_path / "transcripts"
        self._transcripts_dir.mkdir(parents=True, exist_ok=True)
        self._agent_loggers: Dict[str, logging.Logger] = {}

        # Only include PM in multi-agent mode
        agent_ids_for_transcripts = list(self.agent_ids)
        if config.num_coding_agents > 1:
            agent_ids_for_transcripts.append("project_manager_agent")

        for agent_id in agent_ids_for_transcripts:
            agent_logger = logging.getLogger(f"agent_org.{agent_id}")
            agent_logger.setLevel(logging.INFO)
            agent_logger.propagate = False  # Don't propagate to root logger (avoid console dups)
            handler = logging.FileHandler(self._transcripts_dir / f"{agent_id}.txt")
            handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            agent_logger.addHandler(handler)
            self._agent_loggers[agent_id] = agent_logger

    def _log(self, message: str, agent_id: Optional[str] = None):
        """Log to logger, main transcript, and optionally agent-specific transcript"""
        # Use agent-specific logger if agent_id provided, otherwise default logger
        logger = logging.getLogger(agent_id) if agent_id else self.logger
        logger.info(message)
        self.transcript.append(message)
        if agent_id and agent_id in self.agent_transcripts:
            self.agent_transcripts[agent_id].append(message)
            # Write to agent-specific file via logger
            self._agent_loggers[agent_id].info(message)

    async def _streaming_prompt(self, content: str):
        """Wrap prompt as async generator - required for MCP servers."""
        yield {"type": "user", "message": {"role": "user", "content": content}}

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point. Execute a task with the multi-agent organization.

        Args:
            task: Task definition dict with keys:
                - title: str
                - description: str
                - business_goal: str
                - acceptance_criteria: List[str]
                - test_requirements: List[str]

        Returns:
            Dict with execution results
        """
        self._log("=== Starting AgentOrg execution ===")
        self._log(f"Task: {task.get('title', 'Untitled')}")
        self._log(f"Agents: {self.agent_ids}")

        try:
            # Step 1: Load root ticket(s) from task
            self.state.load_from_dict(task)
            initial_tickets = self.state.list_tickets(TicketStatus.CREATED)

            if not initial_tickets:
                self._log("No tickets in CREATED status to process.")
                return self.summary()

            for ticket in initial_tickets:
                self.state.set_approval_required(ticket.id, self.config.approval_required)

            self._log(f"Dispatching {len(initial_tickets)} created tickets concurrently...")

            # Step 2: Single agent skips PM, multi-agent uses PM decomposition
            if self.config.num_coding_agents == 1:
                # Single agent: assign tickets directly (no PM, system assigns)
                single_agent_id = self.agent_ids[0]
                for ticket in initial_tickets:
                    self.state.assign_ticket_to_agent(ticket.id, single_agent_id, assigned_by="system")
                self._log(f"Single agent mode: assigned {len(initial_tickets)} tickets to {single_agent_id}")
            else:
                # Multi-agent: PM decomposes each root ticket using MCP tools
                for ticket in initial_tickets:
                    pm_success = await self._run_pm(ticket)
                    if not pm_success:
                        self._log(f"ERROR: PM decomposition failed for ticket {ticket.id}")
                        return self.summary()

                # Verify all leaf tickets (no children) are assigned
                # Parent tickets stay CREATED until children complete - that's expected
                created_tickets = self.state.list_tickets(TicketStatus.CREATED)
                unassigned_leaves = [t for t in created_tickets if not t.children_ids]
                assigned_count = sum(
                    1
                    for t in self.state.tickets.values()
                    if t.status in (TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS)
                )
                self._log(f"PM assigned {assigned_count} tickets")

                if unassigned_leaves:
                    self._log(
                        f"ERROR: {len(unassigned_leaves)} leaf tickets not assigned: {[t.id for t in unassigned_leaves]}"
                    )
                    self._log("PM failed to assign all tickets - aborting")
                    return self.summary()

            # Step 3: Spawn workers concurrently
            self._log("\n--- Spawning Workers ---")
            await self._run_all_workers()

            # Step 4: Return summary (matches old ticketing_system.summary())
            self._log("\n--- Collecting Results ---")
            return self.summary()

        except Exception as e:
            self._log(f"ERROR: {e}")
            return self.summary()

    # =========================================================================
    # PM DECOMPOSITION (TOOL-BASED)
    # =========================================================================

    async def _run_pm(self, root_ticket: Ticket) -> bool:
        """
        Run PM to decompose task into tickets using MCP tools.

        PM uses tools: list_tickets, get_ticket, create_subtasks, assign_ticket
        PM signals completion with "TASK_STATUS: COMPLETE"

        Args:
            root_ticket: The root Ticket object to decompose

        Returns:
            True if PM completed successfully, False otherwise
        """
        # Build prompt using ticket repr (matches old code)
        pm_prompts = PM_PROMPT_REGISTRY[self.config.pm_prompt_set]
        prompt = pm_prompts["task_prompt"].format(
            ticket_repr=repr(root_ticket),
            num_developers=len(self.agent_ids),
            developer_ids="\n".join(f"- {agent_id}" for agent_id in self.agent_ids),
        )
        system_prompt = pm_prompts["system_prompt"]

        # Create PM MCP tools server
        pm_tools_server = create_pm_tools(self.state, self.agent_ids)

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            mcp_servers={"pm": pm_tools_server},
            allowed_tools=[
                "mcp__pm__list_tickets",
                "mcp__pm__get_ticket",
                "mcp__pm__create_subtasks",
                "mcp__pm__assign_ticket",
            ],
            cwd=str(self.config.codebase_path),
            model=self.config.model,
            max_turns=self.config.max_turns,
        )

        # Run PM query - MCP servers require streaming input mode
        self._log(f"🔨 Starting ticket: {root_ticket.id} - {root_ticket.title}", agent_id="project_manager_agent")
        pm_completed = False

        try:
            async for message in query(prompt=self._streaming_prompt(prompt), options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            self._log("💭 LLM RESPONSE:", agent_id="project_manager_agent")
                            self._log(block.text, agent_id="project_manager_agent")
                            # Check for completion signal
                            if "TASK_STATUS: COMPLETE" in block.text.upper():
                                pm_completed = True
                        elif isinstance(block, ToolUseBlock):
                            # Truncate large inputs to avoid potential buffer issues
                            input_str = str(block.input)
                            if len(input_str) > 5000:
                                input_str = input_str[:5000] + "...[truncated]"
                            self._log(f"🔧 Tool: {block.name}({input_str})", agent_id="project_manager_agent")
                elif isinstance(message, UserMessage):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            if isinstance(block.content, str):
                                result_text = block.content
                            elif isinstance(block.content, list):
                                result_text = " ".join(
                                    item.get("text", "")
                                    for item in block.content
                                    if isinstance(item, dict) and item.get("type") == "text"
                                )
                            else:
                                result_text = ""
                            self._log(f"✅ TOOL RESULT:\n{result_text}", agent_id="project_manager_agent")
                elif isinstance(message, ResultMessage):
                    self._log(
                        f"Completed: {message.subtype} (turns={message.num_turns}, cost=${message.total_cost_usd:.4f})",
                        agent_id="project_manager_agent",
                    )
        except Exception as e:
            import traceback

            self._log(f"PM query error: {e}\n{traceback.format_exc()}", agent_id="project_manager_agent")
            return False

        # Save decomposed state
        if pm_completed:
            state_file = self.config.workspace_path / "ticketing_system.decomposed.json"
            self.state.save(state_file)
            self._log(f"✅ Ticket decomposed and assigned: {root_ticket.title}", agent_id="project_manager_agent")
        else:
            self._log(
                f"❌ PM did not signal completion for: {root_ticket.title}",
                agent_id="project_manager_agent",
            )

        return pm_completed

    # =========================================================================
    # WORKER EXECUTION
    # =========================================================================

    async def _run_all_workers(self):
        """
        Spawn all workers concurrently and wait for them to complete.

        Workers self-manage via MCP tools and terminate when get_next_task returns "all_done".
        Global timeout provides safety net for hangs.
        """
        tasks = [asyncio.create_task(self._run_worker(agent_id)) for agent_id in self.agent_ids]

        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.config.global_timeout,
            )
        except asyncio.TimeoutError:
            self._log(f"WARNING: Workers timed out after {self.config.global_timeout} seconds")
            for task in tasks:
                if not task.done():
                    task.cancel()
            # Wait for cancellations to complete
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_worker(self, agent_id: str):
        """
        Spawn a single worker agent.

        The worker self-manages from here using its loop and MCP tools.
        """
        self._log(f"Starting worker: {agent_id}", agent_id=agent_id)

        # Mark agent as active (for reviewer selection filtering)
        async with self.state.lock:
            self.state.active_agents.add(agent_id)

        # Build system prompt from registry
        coder_prompts = CODER_PROMPT_REGISTRY.get(self.config.coder_prompt_set, CODER_PROMPT_REGISTRY["benign"])
        system_prompt = coder_prompts["system_message"]

        # Fetch first task from backlog and format it
        async with self.state.lock:
            result = self.state.claim_next_task(agent_id)
            if not result:
                self._log(f"No tasks assigned to {agent_id}, terminating", agent_id=agent_id)
                self.state.active_agents.discard(agent_id)
                return

            _, ticket = result
        task_prompt = format_task_prompt(
            ticket=ticket,
            codebase_path=self.config.codebase_path,
            prompt_set=self.config.coder_prompt_set,
        )

        # Create per-agent MCP tools server (agent_id baked in via closure)
        tools_server = create_coding_agent_tools(
            board=self.state,
            agent_id=agent_id,
            coding_agent_ids=self.agent_ids,
            model_id=self.config.model,
            max_turns=self.config.max_turns,
            codebase_path=self.config.codebase_path,
            coder_prompt_set=self.config.coder_prompt_set,
            reviewer_selection_has_memory=self.config.reviewer_selection_has_memory,
            review_has_memory=self.config.review_has_memory,
        )

        # Configure worker options
        # Prepend venv bin to PATH so agents use the correct Python (bypasses pyenv issues)
        venv_bin = str(Path(sys.executable).parent)
        worker_env = {"PATH": f"{venv_bin}:{os.environ.get('PATH', '')}"}

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            mcp_servers={"org": tools_server},
            allowed_tools=[
                # Claude Code built-in tools
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                "Bash",
                # Organization MCP tools
                "mcp__org__complete_ticket",
                "mcp__org__request_review",
                "mcp__org__request_changes",
                "mcp__org__approve_ticket",
            ],
            permission_mode=self.config.permission_mode,
            cwd=str(self.config.codebase_path),
            env=worker_env,
            model=self.config.model,
            max_turns=self.config.max_turns,
        )

        # Run the worker - MCP servers require streaming input mode
        try:
            async for message in query(prompt=self._streaming_prompt(task_prompt), options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            self._log("💭 LLM RESPONSE:", agent_id=agent_id)
                            self._log(block.text, agent_id=agent_id)
                        elif isinstance(block, ToolUseBlock):
                            # Truncate large inputs to avoid potential buffer issues
                            input_str = str(block.input)
                            if len(input_str) > 5000:
                                input_str = input_str[:5000] + "...[truncated]"
                            self._log(f"🔧 Tool: {block.name}({input_str})", agent_id=agent_id)
                elif isinstance(message, UserMessage):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            if isinstance(block.content, str):
                                result_text = block.content
                            elif isinstance(block.content, list):
                                result_text = " ".join(
                                    item.get("text", "")
                                    for item in block.content
                                    if isinstance(item, dict) and item.get("type") == "text"
                                )
                            else:
                                result_text = ""
                            self._log(f"✅ TOOL RESULT:\n{result_text}", agent_id=agent_id)
                elif isinstance(message, ResultMessage):
                    self._log(
                        f"Completed: {message.subtype} (turns={message.num_turns}, cost=${message.total_cost_usd:.4f})",
                        agent_id=agent_id,
                    )

        except Exception as e:
            import traceback

            self._log(f"ERROR: {e}\n{traceback.format_exc()}", agent_id=agent_id)

        finally:
            # Cleanup: mark agent as inactive and fail any incomplete ticket
            async with self.state.lock:
                self.state.active_agents.discard(agent_id)
                current = self.state.current_tasks.get(agent_id)
                if current:
                    _, ticket_id = current
                    ticket = self.state.get_ticket(ticket_id)
                    if ticket and ticket.status not in (TicketStatus.COMPLETED, TicketStatus.FAILED):
                        self._log(
                            f"Agent terminated with incomplete ticket {ticket_id} - marking FAILED", agent_id=agent_id
                        )
                        self.state.update_ticket_status(ticket_id, TicketStatus.FAILED)
                    self.state.current_tasks[agent_id] = None

    # =========================================================================
    # RESULTS
    # =========================================================================

    def summary(self) -> Dict[str, Any]:
        """
        Return summary of ticket completion.

        Matches old ticketing_system.summary() exactly:
        {
            "total_tickets": N,
            "completed_tickets": N,
            "failed_tickets": N,
        }
        """
        total_tickets = len(self.state.tickets)
        completed_tickets = len(self.state.list_tickets(TicketStatus.COMPLETED))
        failed_tickets = total_tickets - completed_tickets

        return {
            "total_tickets": total_tickets,
            "completed_tickets": completed_tickets,
            "failed_tickets": failed_tickets,
        }

    def get_transcript(self) -> str:
        """Return full transcript as string"""
        return "\n".join(self.transcript)

    def get_agent_transcript(self, agent_id: str) -> str:
        """Return transcript for a specific agent"""
        if agent_id in self.agent_transcripts:
            return "\n".join(self.agent_transcripts[agent_id])
        return ""

    def save_transcript(self, path: Path):
        """Save main transcript to file"""
        path.write_text(self.get_transcript())

    def save_all_transcripts(self, directory: Path):
        """
        Save main transcript and per-agent transcripts to directory.

        Creates:
        - transcript.txt (main)
        - transcripts/project_manager_agent.txt
        - transcripts/coding_agent_0.txt
        - transcripts/coding_agent_1.txt
        - etc.
        """
        # Save main transcript
        self.save_transcript(directory / "transcript.txt")

        # Create transcripts subdirectory
        transcripts_dir = directory / "transcripts"
        transcripts_dir.mkdir(exist_ok=True)

        # Save per-agent transcripts
        for agent_id, transcript_lines in self.agent_transcripts.items():
            if transcript_lines:  # Only save if there's content
                agent_file = transcripts_dir / f"{agent_id}.txt"
                agent_file.write_text("\n".join(transcript_lines))
