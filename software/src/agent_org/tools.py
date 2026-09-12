"""
MCP Tools for Agent SDK Organization

Two separate tool sets:
1. PM Tools - For project manager to manage tickets
2. Coding Agent Tools - For coding agents to self-manage work

PM Tools:
- list_tickets: List all tickets or filter by status
- get_ticket: Get ticket details
- create_subtasks: Create subtask tickets
- assign_ticket: Assign ticket to a coding agent

Coding Agent Tools:
- complete_ticket: Mark work done, trigger approval flow, get next task
- request_review: Request code review from colleague, get next task
- request_changes: Send ticket back for changes after review, get next task
- approve_ticket: Approve after review, mark complete, get next task
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    create_sdk_mcp_server,
    query,
    tool,
)
from safetytooling.apis import InferenceAPI
from safetytooling.data_models import ChatMessage, MessageRole, Prompt
from safetytooling.utils import utils

from .prompts import (
    CODER_PROMPT_REGISTRY,
    format_code_review_prompt,
    format_reviewer_selection_prompt,
    format_task_prompt,
)
from .schemas import ApprovalStatus, Ticket, TicketBoard, TicketStatus

# Load .env and setup environment before creating API clients
utils.setup_environment()

logger = logging.getLogger("AgentOrg")

# Module-level singleton for fresh LLM calls
_inference_api = InferenceAPI(no_cache=True)

# =============================================================================
# PM TOOLS
# =============================================================================


def create_pm_tools(board: TicketBoard, coding_agent_ids: List[str]):
    """
    Create MCP tools for the Project Manager agent.

    PM tools for task decomposition and assignment:
    - list_tickets: Query ticket system
    - get_ticket: Get ticket details
    - create_subtasks: Create subtask tickets from JSON
    - assign_ticket: Assign ticket to a coding agent

    Args:
        board: Shared TicketBoard state
        coding_agent_ids: List of valid coding agent IDs for assignment

    Returns an MCP server for the PM agent.
    """

    @tool(
        "list_tickets",
        "List all tickets in the system, optionally filtered by status. "
        "Valid statuses: created, assigned, in_progress, failed, awaiting_approval, changes_requested, completed",
        {"status": str},
    )
    async def list_tickets(args: Dict[str, Any]) -> Dict[str, Any]:
        """List tickets, optionally filtered by status."""
        status_str = args.get("status")

        async with board.lock:
            if status_str:
                try:
                    status = TicketStatus(status_str.lower())
                    tickets = board.list_tickets(status)
                except ValueError:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Invalid status '{status_str}'. Valid: {[s.value for s in TicketStatus]}",
                            }
                        ]
                    }
            else:
                tickets = board.list_tickets()

            result = (
                f"Found {len(tickets)} tickets"
                + (f" with status {status_str}" if status_str else "")
                + "\n"
                + "\n".join(f"- {t.id}: {t.title}" for t in tickets)
            )

            return {"content": [{"type": "text", "text": result}]}

    @tool(
        "get_ticket",
        "Get detailed information about a specific ticket by ID.",
        {"ticket_id": str},
    )
    async def get_ticket(args: Dict[str, Any]) -> Dict[str, Any]:
        """Get ticket details."""
        ticket_id = args.get("ticket_id")
        if not ticket_id:
            return {"content": [{"type": "text", "text": "Error: get_ticket requires a ticket_id parameter"}]}

        async with board.lock:
            ticket = board.get_ticket(ticket_id)
            if not ticket:
                return {"content": [{"type": "text", "text": f"Ticket '{ticket_id}' not found"}]}

            return {"content": [{"type": "text", "text": repr(ticket)}]}

    @tool(
        "create_subtasks",
        "Create subtask tickets for a parent ticket. "
        "Pass a JSON array of subtask objects with: id, title, description, business_goal, "
        "files_to_modify (array), acceptance_criteria (array), test_requirements (array).",
        {"parent_id": str, "subtasks": list},
    )
    async def create_subtasks(args: Dict[str, Any]) -> Dict[str, Any]:
        """Create subtasks from JSON array."""
        parent_id = args.get("parent_id")
        subtasks_data = args.get("subtasks", [])

        # Handle JSON string input (model sometimes passes string instead of list)
        if isinstance(subtasks_data, str):
            try:
                subtasks_data = json.loads(subtasks_data)
            except json.JSONDecodeError as e:
                return {"content": [{"type": "text", "text": f"Error parsing subtasks JSON: {e}"}]}

        async with board.lock:
            try:
                # Inherit approval_required from parent if it exists
                parent = board.get_ticket(parent_id) if parent_id else None
                approval_required = parent.approval_required if parent else True

                created = []
                for subtask in subtasks_data:
                    ticket = Ticket(**subtask, parent_id=parent_id, approval_required=approval_required)
                    board.add_ticket(ticket)
                    created.append(ticket.id)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "Created subtasks: \n"
                            + "\n".join(f"Created ticket for subtask {id}" for id in created),
                        }
                    ]
                }
            except Exception as e:
                return {"content": [{"type": "text", "text": f"Error creating subtasks: {e}"}]}

    @tool(
        "assign_ticket",
        "Assign a ticket to an agent.",
        {"ticket_id": str, "agent_id": str},
    )
    async def assign_ticket(args: Dict[str, Any]) -> Dict[str, Any]:
        """Assign ticket to an agent's backlog."""
        ticket_id = args.get("ticket_id")
        agent_id = args.get("agent_id")

        if not ticket_id or not agent_id:
            return {"content": [{"type": "text", "text": "Error: ticket_id and agent_id are required"}]}

        if agent_id not in coding_agent_ids:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Invalid agent_id '{agent_id}'. Valid: {coding_agent_ids}",
                    }
                ]
            }

        async with board.lock:
            success = board.assign_ticket_to_agent(
                ticket_id, agent_id, action="execute", assigned_by="project_manager_agent"
            )
            if not success:
                return {"content": [{"type": "text", "text": f"Error: Ticket '{ticket_id}' not found"}]}

            return {"content": [{"type": "text", "text": f"Assigned ticket '{ticket_id}' to agent '{agent_id}'"}]}

    return create_sdk_mcp_server(
        name="pm",
        version="1.0.0",
        tools=[list_tickets, get_ticket, create_subtasks, assign_ticket],
    )


# =============================================================================
# CODING AGENT TOOLS
# =============================================================================


def create_coding_agent_tools(
    board: TicketBoard,
    agent_id: str,
    coding_agent_ids: List[str],
    model_id: str,
    max_turns: int,
    codebase_path: Path,
    coder_prompt_set: str,
    reviewer_selection_has_memory: bool,
    review_has_memory: bool,
):
    """
    Create MCP tools for a coding agent.

    Coding agent tools for self-managing work loop:
    - complete_ticket: Mark done, trigger approval, chain to next task
    - request_review: Request code review from colleague, chain to next task
    - request_changes: Send back for changes after review, chain to next task
    - approve_ticket: Approve after review, mark complete, chain to next task

    Internal helper (_get_next_task) handles task routing and no-memory intercepts.

    Args:
        board: Shared TicketBoard state
        agent_id: This agent's ID (baked in via closure)
        coding_agent_ids: List of all coding agent IDs (for reviewer selection)
        model_id: Model ID for fresh LLM calls
        max_turns: Max turns for fresh review agents
        codebase_path: Path to codebase for task prompts
        coder_prompt_set: Prompt set name for task formatting
        reviewer_selection_has_memory: If False, use fresh LLM for reviewer selection
        review_has_memory: If False, use fresh LLM for code review

    Returns an MCP server for this coding agent.
    """

    def _text_response(text: str) -> Dict[str, Any]:
        """Helper to format MCP text response."""
        return {"content": [{"type": "text", "text": text}]}

    def _get_current_ticket() -> Tuple[Optional[Ticket], Optional[Dict[str, Any]]]:
        """Get current ticket for this agent. Must be called inside board.lock."""
        current_task = board.current_tasks.get(agent_id)
        if not current_task:
            return None, _text_response("Error: No current task")
        _, ticket_id = current_task

        ticket = board.get_ticket(ticket_id)
        if not ticket:
            return None, _text_response(f"Error: Ticket '{ticket_id}' not found")

        return ticket, None

    # Internal helper - not exposed as a tool
    # Called by complete_ticket, request_review, request_changes, approve_ticket to chain to next task
    async def _get_next_task() -> Dict[str, Any]:
        """
        Internal: Get next task, blocking if empty.

        Intercepts request_approval and review actions based on memory config:
        - If no memory: handles via fresh LLM call, then continues to next task
        - If with memory: returns action to agent to handle
        """
        while True:
            # Variables for deferred LLM/agent calls (outside lock)
            pending_llm_call = None
            pending_ticket = None
            pending_colleagues = None

            async with board.lock:
                # Cleanup tickets stuck on dead agents before checking for work
                board.cleanup_dead_agent_tickets()

                result = board.claim_next_task(agent_id)

                if result:
                    action, ticket = result

                    # ===========================================
                    # INTERCEPT: request_approval
                    # ===========================================
                    if action == "request_approval":
                        colleagues = board.get_colleagues_stats(agent_id, coding_agent_ids)

                        if not colleagues:
                            # No colleagues to review - mark complete without approval
                            board.update_ticket_status(ticket.id, TicketStatus.COMPLETED)
                            board.current_tasks[agent_id] = None
                            continue

                        if not reviewer_selection_has_memory:
                            # NO MEMORY: Prepare for fresh LLM call outside lock
                            pending_llm_call, pending_ticket, pending_colleagues = "select_reviewer", ticket, colleagues
                        else:
                            # WITH MEMORY: Return to agent with formatted reviewer selection prompt
                            return _text_response(format_reviewer_selection_prompt(ticket, colleagues))

                    # ===========================================
                    # INTERCEPT: review
                    # ===========================================
                    elif action == "review":
                        if not review_has_memory:
                            # NO MEMORY: Prepare for fresh agent call outside lock
                            pending_llm_call = "perform_review"
                            pending_ticket = ticket
                        else:
                            # WITH MEMORY: Return to agent with formatted code review prompt
                            return _text_response(format_code_review_prompt(ticket))

                    # ===========================================
                    # Normal action (execute)
                    # ===========================================
                    else:
                        prompt = format_task_prompt(
                            ticket=ticket,
                            codebase_path=codebase_path,
                            prompt_set=coder_prompt_set,
                        )
                        return _text_response(prompt)

                # Check if all done (no backlog items)
                elif board.all_tickets_complete():
                    board.current_tasks[agent_id] = None
                    return _text_response("All tickets complete.")

            # ===========================================
            # Handle deferred LLM calls (outside lock)
            # ===========================================
            if pending_llm_call == "select_reviewer":
                # Make fresh LLM call to select reviewer
                reviewer_id, approval_msg = await select_reviewer_fresh(
                    pending_ticket, pending_colleagues, model_id, agent_id
                )

                # Re-acquire lock to update state
                async with board.lock:
                    if reviewer_id and reviewer_id in coding_agent_ids:
                        pending_ticket.status = TicketStatus.AWAITING_APPROVAL
                        pending_ticket.assigned_by = agent_id
                        pending_ticket.assigned_to = reviewer_id
                        pending_ticket.add_approval(
                            reviewer_id=reviewer_id,
                            status=ApprovalStatus.PENDING,
                            approval_message=approval_msg,
                        )
                        board.task_backlogs[reviewer_id].append(("review", pending_ticket))
                        logger.info(f"[{agent_id}] Routed ticket {pending_ticket.id} to {reviewer_id} for review")
                    else:
                        # Invalid reviewer selected - mark ticket failed
                        logger.warning(
                            f"[{agent_id}] Invalid reviewer '{reviewer_id}' - marking ticket {pending_ticket.id} FAILED"
                        )
                        board.update_ticket_status(pending_ticket.id, TicketStatus.FAILED)
                    board.current_tasks[agent_id] = None

                # Continue loop to get agent's real next task
                continue

            elif pending_llm_call == "perform_review":
                # Spawn fresh agent to perform review
                review_status, review_message = await perform_review_fresh(
                    pending_ticket, model_id, codebase_path, max_turns, coder_prompt_set, agent_id
                )

                # Re-acquire lock to update state
                async with board.lock:
                    if review_status == "approved":
                        board.update_ticket_status(pending_ticket.id, TicketStatus.COMPLETED)
                        pending_ticket.update_approval(
                            reviewer_id=agent_id,
                            status=ApprovalStatus.APPROVED,
                            comments=review_message,
                        )
                        logger.info(f"[{agent_id}] Approved ticket {pending_ticket.id}")
                    elif review_status == "changes_requested":
                        # Changes requested - send back to original author
                        original_author = pending_ticket.assigned_by
                        if original_author and original_author in coding_agent_ids:
                            pending_ticket.assigned_by = agent_id  # Who sent it (reviewer)
                            pending_ticket.assigned_to = original_author  # Who has it now
                            pending_ticket.status = TicketStatus.CHANGES_REQUESTED
                            pending_ticket.update_approval(
                                reviewer_id=agent_id,
                                status=ApprovalStatus.CHANGES_REQUESTED,
                                comments=review_message,
                            )
                            board.task_backlogs[original_author].append(("execute", pending_ticket))
                            logger.info(
                                f"[{agent_id}] Requested changes on ticket {pending_ticket.id}, routing back to {original_author}"
                            )
                        else:
                            # Can't route back - mark failed
                            logger.warning(
                                f"[{agent_id}] Can't route ticket {pending_ticket.id} back to '{original_author}' - marking FAILED"
                            )
                            board.update_ticket_status(pending_ticket.id, TicketStatus.FAILED)
                    else:
                        # Review failed (no valid decision) - mark ticket failed
                        logger.warning(f"[{agent_id}] Review failed for ticket {pending_ticket.id} - marking FAILED")
                        board.update_ticket_status(pending_ticket.id, TicketStatus.FAILED)
                    board.current_tasks[agent_id] = None

                # Continue loop to get agent's real next task
                continue

            # Wait and retry (empty backlog, work not done)
            await asyncio.sleep(0.5)

    @tool(
        "complete_ticket",
        "Mark your current ticket as complete (returns next task, if any). "
        "If ticket approval is required, this triggers the approval flow to review your work. ",
        {"comments": str},
    )
    async def complete_ticket(args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Complete a ticket and get next task.

        If approval_required: queues request_approval, then chains to get_next_task
        If no approval: marks complete directly, then chains to get_next_task

        Always chains to get_next_task - never returns early.
        """
        _ = args.get("comments")

        async with board.lock:
            ticket, error = _get_current_ticket()
            if error:
                return error

            board.current_tasks[agent_id] = None
            if ticket.approval_required:
                board.task_backlogs[agent_id].append(("request_approval", ticket))
            else:
                board.update_ticket_status(ticket.id, TicketStatus.COMPLETED)

        return await _get_next_task()

    @tool(
        "request_review",
        "Request code review from another agent. Call this after completing your work.",
        {"target_agent_id": str, "comments": str},
    )
    async def request_review(args: Dict[str, Any]) -> Dict[str, Any]:
        """Request code review from a colleague."""
        target_agent_id = args.get("target_agent_id")
        comments = args.get("comments")

        async with board.lock:
            ticket, error = _get_current_ticket()
            if error:
                return error

            if target_agent_id not in coding_agent_ids:
                available = [cid for cid in coding_agent_ids if cid != agent_id]
                return _text_response(f"Error: Unknown agent '{target_agent_id}'. Available: {available}")

            # Update ticket state: coder sends to reviewer
            ticket.assigned_by = agent_id  # Who sent it (return address)
            ticket.assigned_to = target_agent_id  # Who has it now
            ticket.status = TicketStatus.AWAITING_APPROVAL
            ticket.add_approval(reviewer_id=target_agent_id, status=ApprovalStatus.PENDING, approval_message=comments)

            # Add to reviewer's backlog and clear current task
            board.task_backlogs[target_agent_id].append(("review", ticket))
            board.current_tasks[agent_id] = None

        return await _get_next_task()

    @tool(
        "request_changes",
        "Send ticket back for changes after code review. Automatically returns to the original author.",
        {"comments": str},
    )
    async def request_changes(args: Dict[str, Any]) -> Dict[str, Any]:
        """Send ticket back to original author for changes."""
        comments = args.get("comments")

        async with board.lock:
            ticket, error = _get_current_ticket()
            if error:
                return error

            # Return to sender (who requested the review)
            return_to = ticket.assigned_by
            if not return_to or return_to not in coding_agent_ids:
                return _text_response("Error: Cannot determine original author to return ticket to")

            # Update ticket state: reviewer sends back to coder
            ticket.assigned_by = agent_id  # Who sent it (reviewer)
            ticket.assigned_to = return_to  # Who has it now (original coder)
            ticket.status = TicketStatus.CHANGES_REQUESTED
            ticket.update_approval(
                reviewer_id=agent_id,
                status=ApprovalStatus.CHANGES_REQUESTED,
                comments=comments,
            )

            # Add to original author's backlog and clear current task
            board.task_backlogs[return_to].append(("execute", ticket))
            board.current_tasks[agent_id] = None

        return await _get_next_task()

    @tool(
        "approve_ticket",
        "Approve your current ticket after successful code review. Marks the ticket as complete.",
        {"comments": str},
    )
    async def approve_ticket(args: Dict[str, Any]) -> Dict[str, Any]:
        """Approve ticket and get next task."""
        comments = args.get("comments")

        async with board.lock:
            ticket, error = _get_current_ticket()
            if error:
                return error

            # Mark complete (triggers parent cascade)
            board.update_ticket_status(ticket.id, TicketStatus.COMPLETED)
            ticket.update_approval(
                reviewer_id=agent_id,
                status=ApprovalStatus.APPROVED,
                comments=comments,
            )

            board.current_tasks[agent_id] = None

        return await _get_next_task()

    return create_sdk_mcp_server(
        name="org",
        version="1.0.0",
        tools=[complete_ticket, request_review, request_changes, approve_ticket],
    )


# =============================================================================
# FRESH LLM CALLS (NO-MEMORY HELPERS)
# =============================================================================
#
# These functions make fresh LLM calls without inheriting the agent's conversation
# history. Used when config.reviewer_selection_has_memory=False or
# config.review_has_memory=False.
#
# This replicates the old code's bug behavior where:
# - _select_reviewers() made a fresh LLM call to pick a reviewer
# - review_approval() started a fresh conversation for code review


async def select_reviewer_fresh(
    ticket: Ticket,
    colleagues: List[Dict[str, Any]],
    model_id: str,
    requesting_agent_id: str,
) -> Tuple[str, str]:
    """
    Make a fresh LLM call to select a reviewer (no memory).

    Replicates old code's _select_reviewers() which made a single LLM call
    without the agent's conversation history.

    Args:
        ticket: The ticket needing review
        colleagues: List of colleague info dicts with agent_id, assigned, completed, failed
        model_id: Model to use for the LLM call
        requesting_agent_id: The agent requesting the review

    Returns:
        Tuple of (reviewer_agent_id, approval_message)
    """
    colleague_ids = [c["agent_id"] for c in colleagues]
    logger.info(f"[{requesting_agent_id}] select_reviewer_fresh: ticket {ticket.id}, candidates: {colleague_ids}")

    # Use shared prompt with no-memory completion (JSON output)
    selection_prompt = format_reviewer_selection_prompt(ticket, colleagues, with_memory=False)

    # Make fresh LLM call using safety-tooling
    messages = [ChatMessage(role=MessageRole.user, content=selection_prompt)]
    response = await _inference_api(model_id=model_id, prompt=Prompt(messages=messages))

    # Extract response text
    response_text = ""
    if isinstance(response, list) and len(response) > 0:
        first = response[0]
        if hasattr(first, "completion") and first.completion:
            response_text = first.completion
        elif hasattr(first, "content") and first.content:
            response_text = first.content

    # Parse response
    parsed = _extract_json_from_response(response_text)
    if not parsed or not isinstance(parsed, dict):
        # Fallback: pick first colleague (colleagues is always non-empty here)
        fallback_id = colleagues[0]["agent_id"]
        logger.info(f"[{requesting_agent_id}] select_reviewer_fresh: Parse failed, fallback to {fallback_id}")
        return fallback_id, "Please review my code changes."

    agent_id = str(parsed.get("agent_id", "")).strip()
    approval_msg = parsed.get("approval_message", "Please review my code changes.")

    logger.info(f"[{requesting_agent_id}] select_reviewer_fresh: selected {agent_id} for ticket {ticket.id}")
    return agent_id, approval_msg


async def perform_review_fresh(
    ticket: Ticket,
    model_id: str,
    codebase_path: Path,
    max_turns: int,
    coder_prompt_set: str,
    reviewing_agent_id: str,
) -> Tuple[str, str]:
    """
    Spawn a fresh agent to perform code review (no memory).

    Replicates old code's review_approval() which started a fresh conversation
    with tools (read_file, list_files, run_tests) for interactive review.

    Args:
        ticket: The ticket being reviewed
        model_id: Model to use for the agent
        codebase_path: Path to the codebase for tool access
        max_turns: Maximum number of turns for the review agent
        coder_prompt_set: Prompt set name to get system prompt from
        reviewing_agent_id: The agent performing the review

    Returns:
        Tuple of (status, message) where status is 'approved', 'changes_requested', or 'failed'
    """
    logger.info(
        f"[{reviewing_agent_id}] perform_review_fresh: starting review for ticket {ticket.id} from {ticket.assigned_by}"
    )

    # Use shared prompt with no-memory completion (JSON output)
    review_prompt = format_code_review_prompt(ticket, with_memory=False)

    # Get system prompt from registry (matches old code behavior)
    coder_prompts = CODER_PROMPT_REGISTRY.get(coder_prompt_set, CODER_PROMPT_REGISTRY["benign"])
    system_prompt = coder_prompts["system_message"]

    # Helper for streaming input mode
    async def _streaming_prompt():
        yield {"type": "user", "message": {"role": "user", "content": review_prompt}}

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=["Read", "Glob", "Grep", "Bash"],
        permission_mode="acceptEdits",
        cwd=str(codebase_path),
        model=model_id,
        max_turns=max_turns,  # Match old code's max_iterations for review
    )

    # Collect agent's text output to find the final decision
    collected_text = ""

    try:
        async for message in query(prompt=_streaming_prompt(), options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        collected_text += block.text + "\n"
    except Exception as e:
        logger.error(f"[perform_review_fresh] Error reviewing ticket {ticket.id}: {e}")
        return ("failed", f"Review agent encountered an error: {e}")

    # Parse the final JSON decision from collected text
    parsed = _extract_json_from_response(collected_text)
    if not parsed or parsed.get("status") not in ("approved", "changes_requested"):
        logger.warning(f"[perform_review_fresh] No valid decision for ticket {ticket.id}")
        return ("failed", "Review incomplete - no valid decision")

    status = parsed["status"]
    message = parsed.get("approval_message", "")

    # changes_requested without feedback is useless - treat as failed
    if status == "changes_requested" and not message:
        logger.warning(f"[perform_review_fresh] Changes requested but no feedback for ticket {ticket.id}")
        return ("failed", "Review incomplete - no feedback provided")

    logger.info(
        f"[{reviewing_agent_id}] perform_review_fresh: completed review for ticket from {ticket.assigned_by}--{ticket.id}: {status}"
    )
    return (status, message)


def _extract_json_from_response(response: str) -> Optional[Dict[str, Any]]:
    """Parse last valid JSON from LLM response, handling code blocks."""
    # Try JSON code blocks first (last one wins)
    json_matches = re.findall(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
    for json_str in reversed(json_matches):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            continue

    # Try plain JSON objects (last one wins)
    json_matches = re.findall(r"\{[^{}]*\}", response, re.DOTALL)
    for json_str in reversed(json_matches):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            continue

    return None
