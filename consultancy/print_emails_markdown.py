"""
print_emails_markdown.py - Export simulation emails and agent thinking to markdown

This script reads a simulation database (.db file) and outputs emails and model
messages in markdown format for easy review and documentation.

Usage examples:
  # Print emails and agent thinking for all agents
  python print_emails_markdown.py simulations/simulation_consultancy_1234567890.db

  # Redirect output to a file
  python print_emails_markdown.py simulations/simulation_consultancy_1234567890.db > output.md

Output format:
  For each agent:
  - Section with emails sent (timestamp, recipients, subject, content)
  - Section with model thinking and outputs (assistant/user messages by iteration)

See also: webapp.py for a web-based viewer of the same data.
"""

from database_repository import DatabaseRepository
from datetime import datetime
import argparse
import os

def print_emails_markdown(db_path):
    db_repo = DatabaseRepository(db_path)
    try:
        all_emails = db_repo.get_conversation_log()
        # Group emails by sender
        emails_by_sender = {}
        for email in all_emails:
            sender = email['sender']
            emails_by_sender.setdefault(sender, []).append(email)
        
        for sender, emails in emails_by_sender.items():
            print(f"## {sender}\n")
            for i, email in enumerate(emails, 1):
                timestamp = datetime.fromtimestamp(email['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                recipients = ', '.join(email['recipients'])
                subject = email.get('subject', '')
                content = email.get('content', '')
                print(f"### Email #{i}")
                print(f"- **Timestamp:** {timestamp}")
                print(f"- **To:** {recipients}")
                print(f"- **Subject:** {subject}")
                print(f"- **Iteration:** {email.get('iteration_id', '')}")
                print()
                print("```")
                print(content)
                print("```\n")
    finally:
        db_repo.close()


def print_emails_and_thinking_markdown(db_path):
    db_repo = DatabaseRepository(db_path)
    try:
        # Get all emails and agent messages
        all_emails = db_repo.get_conversation_log()
        agent_names = db_repo.get_all_agent_names()
        agent_id_map = {name: db_repo.get_agent_id(name) for name in agent_names}
        agent_messages = {name: db_repo.get_agent_messages(agent_id) for name, agent_id in agent_id_map.items() if agent_id}

        # Group emails by sender
        emails_by_sender = {}
        for email in all_emails:
            sender = email['sender']
            emails_by_sender.setdefault(sender, []).append(email)

        for agent in agent_names: #["communications_intern"]:
            print(f"# {agent}\n")

            # Print emails
            emails = emails_by_sender.get(agent, [])
            if emails:
                print("## Emails Sent\n")
                for i, email in enumerate(emails, 1):
                    timestamp = datetime.fromtimestamp(email['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                    recipients = ', '.join(email['recipients'])
                    subject = email.get('subject', '')
                    content = email.get('content', '')
                    print(f"### Email #{i}")
                    print(f"- **Timestamp:** {timestamp}")
                    print(f"- **To:** {recipients}")
                    print(f"- **Subject:** {subject}")
                    print(f"- **Iteration:** {email.get('iteration_id', '')}")
                    print()
                    print("```")
                    print(content)
                    print("```\n")
            else:
                print("_No emails sent._\n")

            # Print agent "thinking"/outputs
            messages = agent_messages.get(agent, [])
            if messages:
                print("## Model Thinking & Outputs\n")
                for msg in messages:
                    timestamp = datetime.fromtimestamp(msg['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                    print(f"### {msg['role'].capitalize()} (Iteration {msg['iteration_id']})")
                    print(f"- **Timestamp:** {timestamp}")
                    print()
                    print("```")
                    print(msg['content'])
                    print("```\n")
            else:
                print("_No model thinking/outputs._\n")

            print("\n---\n")
    finally:
        db_repo.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Print all emails by agent as markdown")
    parser.add_argument("db_path", type=str, help="Path to the .db file")
    args = parser.parse_args()
    if not os.path.exists(args.db_path):
        print(f"File not found: {args.db_path}")
        exit(1)
    print_emails_and_thinking_markdown(args.db_path)