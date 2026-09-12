#!/usr/bin/env python3
"""
Schemas for Agent SDK Organization

Standalone copy of the ticket schemas from src/project_manager_agent/schemas.py,
without the dependencies that cause import issues.

This ensures agent_org is self-contained and can evolve independently.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger("AgentOrg")


class TicketStatus(str, Enum):
    """Status of a ticket in the system"""

    CREATED = "created"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"

    AWAITING_APPROVAL = "awaiting_approval"
    CHANGES_REQUESTED = "changes_requested"
    COMPLETED = "completed"


class ApprovalStatus(str, Enum):
    """Status of code approval"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class CodeApproval(BaseModel):
    """Represents a code approval record"""

    reviewer_id: str
    status: ApprovalStatus
    approval_message: Optional[str] = None
    comments: Optional[str] = None
    approval_time: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)

    def format_for_context(self) -> str:
        """Format this approval for contextual display in code review"""
        time_str = ""
        if self.approval_time:
            time_str = f" on {self.approval_time.strftime('%Y-%m-%d %H:%M')}"

        result = f"Status: {self.status.value.upper()}\nReviewer: {self.reviewer_id}{time_str}"

        if self.approval_message:
            result += f"\nMessage: {self.approval_message}"

        if self.comments:
            result += f"\nComments:\n{self.comments}"

        return result


class SubTicket(BaseModel):
    """Subtask ticket in the system"""

    id: str
    title: str
    description: str
    business_goal: Optional[str] = None  # Business objectives for this subtask

    files_to_modify: List[str] = []
    acceptance_criteria: List[str] = []
    test_requirements: List[str] = []


class Ticket(BaseModel):
    """Individual ticket in the system"""

    id: str
    status: TicketStatus = TicketStatus.CREATED
    parent_id: Optional[str] = None  # For subtasks
    children_ids: List[str] = []

    # Content
    title: str
    description: str
    business_goal: Optional[str] = None  # Business objectives for this ticket

    # Files and code
    files_to_modify: List[str] = []
    acceptance_criteria: List[str] = []
    test_requirements: List[str] = []

    # Tracking
    assigned_to: Optional[str] = None  # Agent ID
    assigned_by: Optional[str] = None  # Project manager or system
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # Approval
    approval_required: bool = True
    approvals: List[CodeApproval] = []

    def update_status(self, new_status: TicketStatus) -> None:
        """Update ticket status with timestamp tracking"""
        self.status = new_status
        if self.status == TicketStatus.COMPLETED:
            self.completed_at = datetime.now()

    def add_approval(
        self,
        reviewer_id: str,
        status: ApprovalStatus = ApprovalStatus.PENDING,
        approval_message: Optional[str] = None,
    ) -> None:
        """Append a new CodeApproval entry."""
        self.approvals.append(
            CodeApproval(
                reviewer_id=reviewer_id,
                status=status,
                approval_message=approval_message,
                approval_time=datetime.now() if status != ApprovalStatus.PENDING else None,
            )
        )

    def update_approval(
        self,
        reviewer_id: str,
        status: ApprovalStatus,
        comments: Optional[str] = None,
    ) -> None:
        """Update the PENDING approval for this reviewer."""
        existing = next(
            (a for a in self.approvals if a.reviewer_id == reviewer_id and a.status == ApprovalStatus.PENDING),
            None,
        )
        if existing:
            existing.status = status
            existing.comments = comments or existing.comments
            existing.approval_time = datetime.now()

    def get_approval_context(self) -> str:
        """Get formatted approval history for code review context"""
        if not self.approvals:
            return "No previous reviews"

        if len(self.approvals) == 1:
            return f"Previous Review:\n{self.approvals[0].format_for_context()}"

        result = "Review History (most recent first):"
        for i, approval in enumerate(reversed(self.approvals)):
            result += f"\n\nReview {i + 1}:\n{approval.format_for_context()}"

        return result

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return self.model_dump(mode="json")

    def __repr__(self):
        return f"""
ID: {self.id}
Title: {self.title}
Description: {self.description}
Business Goal: {self.business_goal}
Files to modify: {", ".join(self.files_to_modify)}
Acceptance Criteria:
{chr(10).join(f"- {criterion}" for criterion in self.acceptance_criteria)}
Test Requirements:
{chr(10).join(f"- {requirement}" for requirement in self.test_requirements)}
"""


@dataclass
class TicketBoard:
    """
    Central state for the organization, accessed by MCP tools.

    This replaces the per-agent state in the original implementation:
    - Original: Each Agent had self.task_backlog
    - Now: Centralized task_backlogs dict accessed via tools
    """

    tickets: Dict[str, Ticket]
    """All tickets keyed by ticket_id"""

    task_backlogs: Dict[str, List[Tuple[str, Ticket]]]
    """Per-agent backlogs: {agent_id: [(action, ticket), ...]}"""

    current_tasks: Dict[str, Optional[Tuple[str, str]]] = field(default_factory=dict)
    """What each agent is currently working on: {agent_id: (action, ticket_id) or None}"""

    active_agents: set = field(default_factory=set)
    """Agent IDs with running sessions. Dead agents excluded from reviewer selection."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    """Lock for concurrent access (multiple agents may access simultaneously)"""

    def load_from_dict(self, ticket_data: dict) -> None:
        """Load ticket(s) from a dict or list of dicts (matches old board.load() behavior)"""
        if isinstance(ticket_data, dict):
            ticket = Ticket(**ticket_data)
            ticket.status = TicketStatus.CREATED
            self.add_ticket(ticket)
        elif isinstance(ticket_data, list):
            for t_data in ticket_data:
                ticket = Ticket(**t_data)
                ticket.status = TicketStatus.CREATED
                self.add_ticket(ticket)

    def save(self, state_file: Path) -> None:
        """Save tickets to a JSON file (matches old board.save())"""
        with open(state_file, "w") as f:
            json.dump([t.model_dump(mode="json") for t in self.tickets.values()], f, indent=4)

    def add_ticket(self, ticket: Ticket) -> None:
        """Add a ticket to the board and update parent-child relationship if applicable"""
        self.tickets[ticket.id] = ticket

        if ticket.parent_id and ticket.parent_id in self.tickets:
            parent = self.tickets[ticket.parent_id]
            if ticket.id not in parent.children_ids:
                parent.children_ids.append(ticket.id)

    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        """Get a ticket by ID"""
        return self.tickets.get(ticket_id)

    def list_tickets(self, status: Optional[TicketStatus] = None) -> List[Ticket]:
        """List all tickets, optionally filtered by status"""
        if status is None:
            return list(self.tickets.values())
        return [t for t in self.tickets.values() if t.status == status]

    def set_approval_required(self, ticket_id: str, approval_required: bool) -> None:
        """Set approval_required for a ticket"""
        ticket = self.tickets.get(ticket_id)
        if ticket:
            ticket.approval_required = approval_required

    def assign_ticket_to_agent(
        self, ticket_id: str, agent_id: str, action: str = "execute", assigned_by: Optional[str] = None
    ) -> bool:
        """Assign a ticket to an agent's backlog"""
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return False

        ticket.assigned_to = agent_id
        ticket.assigned_by = assigned_by
        ticket.status = TicketStatus.ASSIGNED

        if agent_id not in self.task_backlogs:
            self.task_backlogs[agent_id] = []

        self.task_backlogs[agent_id].append((action, ticket))
        return True

    def get_subtasks(self, parent_id: str) -> List[Ticket]:
        """Get all subtasks of a parent ticket"""
        return [t for t in self.tickets.values() if t.parent_id == parent_id]

    def update_ticket_status(self, ticket_id: str, new_status: TicketStatus) -> None:
        """Update ticket status and check if parent should be completed when all subtasks are done"""
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return

        ticket.update_status(new_status)

        if new_status == TicketStatus.COMPLETED and ticket.parent_id:
            self._check_and_complete_parent(ticket.parent_id)

    def _check_and_complete_parent(self, parent_id: str) -> None:
        """Check if all subtasks of a parent are completed, and if so, mark parent as completed"""
        # Check if parent ticket exists (bug fix)
        if parent_id not in self.tickets:
            return

        parent_ticket = self.tickets[parent_id]
        if parent_ticket.status == TicketStatus.COMPLETED:
            return

        subtasks = self.get_subtasks(parent_id)
        if not subtasks:
            return

        all_completed = all(subtask.status == TicketStatus.COMPLETED for subtask in subtasks)

        if all_completed:
            parent_ticket.update_status(TicketStatus.COMPLETED)
            # Recursively check grandparent
            if parent_ticket.parent_id:
                self._check_and_complete_parent(parent_ticket.parent_id)

    def all_tickets_complete(self) -> bool:
        """Check if all leaf tickets (no children) are in a terminal state (COMPLETED or FAILED)"""
        if not self.tickets:
            return True
        # Only check leaf tickets - parent tickets are organizational containers
        leaf_tickets = [t for t in self.tickets.values() if not t.children_ids]
        if not leaf_tickets:
            return True
        return all(t.status in (TicketStatus.COMPLETED, TicketStatus.FAILED) for t in leaf_tickets)

    def cleanup_dead_agent_tickets(self) -> int:
        """
        Cleanup tickets assigned to dead agents to prevent stalls.

        - AWAITING_APPROVAL with dead reviewer → FAILED (review never happened)
        - ASSIGNED/CHANGES_REQUESTED with dead agent → FAILED (work not done)

        Returns number of tickets cleaned up.
        """
        cleaned = 0
        for ticket in self.tickets.values():
            if ticket.status in (TicketStatus.COMPLETED, TicketStatus.FAILED):
                continue
            assignee = ticket.assigned_to
            if not assignee or assignee in self.active_agents:
                continue
            logger.info(
                f"[cleanup] Marking ticket {ticket.id} FAILED (assigned_to={assignee} is dead, status was {ticket.status})"
            )
            self.update_ticket_status(ticket.id, TicketStatus.FAILED)
            cleaned += 1
        return cleaned

    def any_backlog_has_work(self) -> bool:
        """Check if any agent has work in their backlog"""
        return any(len(backlog) > 0 for backlog in self.task_backlogs.values())

    def claim_next_task(self, agent_id: str) -> Optional[Tuple[str, "Ticket"]]:
        """
        Claim next task from agent's backlog.

        Updates current_tasks and ticket status (IN_PROGRESS for execute/review).

        Returns (action, ticket) or None if backlog is empty.

        Note: Caller must hold self.lock when calling this method.
        """
        backlog = self.task_backlogs.get(agent_id, [])
        if not backlog:
            return None

        action, ticket = backlog.pop(0)
        self.current_tasks[agent_id] = (action, ticket.id)

        # Set IN_PROGRESS only for execute action
        if action == "execute":
            ticket.status = TicketStatus.IN_PROGRESS

        return (action, ticket)

    def get_colleagues_stats(self, exclude_agent_id: str, coding_agent_ids: List[str]) -> List[Dict]:
        """
        Get stats for all coding agents except the excluded one.
        Returns list of dicts with agent_id, assigned, completed, failed.
        Used for reviewer selection context.
        Only includes agents with active sessions (excludes dead agents).
        """
        colleagues = []
        for cid in coding_agent_ids:
            if cid == exclude_agent_id or cid not in self.active_agents:
                continue
            assigned = []
            completed = 0
            failed = 0
            for ticket in self.tickets.values():
                if ticket.assigned_to == cid:
                    if ticket.status == TicketStatus.COMPLETED:
                        completed += 1
                    elif ticket.status == TicketStatus.FAILED:
                        failed += 1
                    elif ticket.status not in (TicketStatus.COMPLETED, TicketStatus.FAILED):
                        assigned.append(ticket)
            colleagues.append(
                {
                    "agent_id": cid,
                    "assigned": assigned,
                    "completed": completed,
                    "failed": failed,
                }
            )
        return colleagues
