"""
webapp.py - Flask web application for viewing simulation results

This web app provides a browser-based interface to explore simulation databases.
View emails, agent interactions, and internal model messages through an intuitive UI.

Usage:
  # Run with default settings (searches for simulation_*.db in simulations/)
  python webapp.py

  # Specify a custom folder containing simulation databases
  python webapp.py --db-folder path/to/your/simulations

  # Set custom port (default: 5001)
  PORT=8080 python webapp.py

The app will:
  - Auto-discover all simulation_*.db files in the specified folder
  - Create a separate view for each simulation database
  - Start a web server at http://localhost:5001 (or custom port)

Features:
  - View all emails in chronological order
  - Filter emails by agent
  - View agent-to-agent interactions
  - Inspect internal model messages and thinking
  - View system prompts for each agent
  - Navigate between multiple simulation runs

See also: print_emails_markdown.py for CLI-based markdown export.
"""

import html
import os
import textwrap
import time
import glob
import datetime
from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    g,
    Blueprint,
    current_app,
)
from database_repository import DatabaseRepository
import logging
from markupsafe import Markup

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

import argparse


# Function to create a blueprint for a specific database
def create_db_blueprint(db_path, blueprint_name):
    bp = Blueprint(blueprint_name, __name__, url_prefix=f"/{blueprint_name}")

    # Store the database path in the blueprint config
    bp.db_path = db_path


    # Get database repository for this specific blueprint
    def get_blueprint_db_repo() -> DatabaseRepository:
        """Create or return a database repository for the current request and blueprint."""
        attr_name = f"db_repo_{blueprint_name}"
        if not hasattr(g, attr_name):
            setattr(g, attr_name, DatabaseRepository(bp.db_path))
        return getattr(g, attr_name)

    # Add a helper function to get sidebar counts
    def get_sidebar_counts():
        """Get email and message counts for the sidebar."""
        db_repo = get_blueprint_db_repo()
        try:
            total_email_count = db_repo.get_total_email_count()
            agent_email_counts = db_repo.get_agent_email_counts()
            agent_message_counts = db_repo.get_agent_message_counts()

            return {
                "total_email_count": total_email_count,
                "agent_email_counts": agent_email_counts,
                "agent_message_counts": agent_message_counts,
            }
        except Exception as e:
            logging.error(f"Error getting sidebar counts: {e}")
            return {
                "total_email_count": 0,
                "agent_email_counts": {},
                "agent_message_counts": {},
            }

    @bp.teardown_app_request
    def close_blueprint_db_repo(error):
        """Close the database repository at the end of the request."""
        attr_name = f"db_repo_{blueprint_name}"
        db_repo = None
        if hasattr(g, attr_name):
            db_repo = getattr(g, attr_name)
            delattr(g, attr_name)
        if db_repo is not None:
            db_repo.close()

    @bp.route("/")
    def index():
        """Home page - redirects to emails view."""
        return redirect(url_for(f"{blueprint_name}.view_emails"))

    @bp.route("/emails")
    def view_emails():
        """View all emails in the conversation log."""
        db_repo = get_blueprint_db_repo()
        try:
            conversation_log = db_repo.get_conversation_log()
            agents = db_repo.get_all_agent_names()

            # Format timestamps for display
            for email in conversation_log:
                email["formatted_time"] = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(email["timestamp"])
                )

            # Get sidebar counts
            sidebar_counts = get_sidebar_counts()

            return render_template(
                "emails.html",
                emails=conversation_log,
                agents=agents,
                title=f"{blueprint_name} - All Emails",
                blueprint_name=blueprint_name,
                database_names=current_app.config.get("DATABASE_NAMES", []),
                **sidebar_counts,  # Add sidebar counts to template variables
            )
        except Exception as e:
            logging.error(f"Error in {blueprint_name}.view_emails: {e}")
            flash(f"An error occurred: {e}", "danger")
            return render_template(
                "emails.html",
                emails=[],
                agents=[],
                title=f"{blueprint_name} - All Emails",
                blueprint_name=blueprint_name,
                database_names=current_app.config.get("DATABASE_NAMES", []),
                total_email_count=0,
                agent_email_counts={},
                agent_message_counts={},
            )

    @bp.route("/agent/<agent_name>")
    def view_agent(agent_name):
        """View emails sent and received by a specific agent."""
        db_repo = get_blueprint_db_repo()
        try:
            # Get all emails
            all_emails = db_repo.get_conversation_log()
            agents = db_repo.get_all_agent_names()

            # Filter emails where the agent is either the sender or a recipient
            agent_emails = []
            for email in all_emails:
                if email["sender"] == agent_name or agent_name in email["recipients"]:
                    # Format timestamp
                    email["formatted_time"] = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(email["timestamp"])
                    )
                    # Add a flag to easily identify if agent is sender or recipient
                    email["is_sender"] = email["sender"] == agent_name
                    agent_emails.append(email)

            # Get sidebar counts
            sidebar_counts = get_sidebar_counts()

            return render_template(
                "agent.html",
                agent_name=agent_name,
                emails=agent_emails,
                agents=agents,
                title=f"{blueprint_name} - {agent_name} Interactions",
                blueprint_name=blueprint_name,
                database_names=current_app.config.get("DATABASE_NAMES", []),
                **sidebar_counts,  # Add sidebar counts to template variables
            )
        except Exception as e:
            logging.error(f"Error in {blueprint_name}.view_agent: {e}")
            flash(f"An error occurred: {e}", "danger")
            return render_template(
                "agent.html",
                agent_name=agent_name,
                emails=[],
                agents=[],
                title=f"{blueprint_name} - {agent_name} Interactions",
                blueprint_name=blueprint_name,
                database_names=current_app.config.get("DATABASE_NAMES", []),
                total_email_count=0,
                agent_email_counts={},
                agent_message_counts={},
            )

    @bp.route("/agent/<agent_name>/messages")
    def view_agent_messages(agent_name):
        """View internal API messages for a specific agent."""
        db_repo = get_blueprint_db_repo()
        try:
            # Get agent ID
            agent_id = db_repo.get_agent_id(agent_name)
            if agent_id is None:
                flash(f"Agent '{agent_name}' not found.", "danger")
                return redirect(url_for(f"{blueprint_name}.index"))

            # Get agent messages
            messages = db_repo.get_agent_messages(agent_id)
            agents = db_repo.get_all_agent_names()

            # Get system prompt for this agent
            system_prompt = db_repo.get_agent_system_prompt(agent_id)
            if system_prompt:
                system_prompt = textwrap.dedent(system_prompt)
                system_prompt = html.escape(system_prompt)

            # Format timestamps for display
            for message in messages:
                message["formatted_time"] = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(message["timestamp"])
                )
                message["content"] = html.escape(message["content"])

            # Get sidebar counts
            sidebar_counts = get_sidebar_counts()

            return render_template(
                "agent_messages.html",
                agent_name=agent_name,
                messages=messages,
                system_prompt=system_prompt,
                agents=agents,
                title=f"{blueprint_name} - {agent_name} API Messages",
                blueprint_name=blueprint_name,
                database_names=current_app.config.get("DATABASE_NAMES", []),
                **sidebar_counts,  # Add sidebar counts to template variables
            )
        except Exception as e:
            logging.error(f"Error in {blueprint_name}.view_agent_messages: {e}")
            flash(f"An error occurred: {e}", "danger")
            return render_template(
                "agent_messages.html",
                agent_name=agent_name,
                messages=[],
                system_prompt=None,
                agents=[],
                title=f"{blueprint_name} - {agent_name} API Messages",
                blueprint_name=blueprint_name,
                database_names=current_app.config.get("DATABASE_NAMES", []),
                total_email_count=0,
                agent_email_counts={},
                agent_message_counts={},
            )

    return bp


def create_app():
    """Create and configure the Flask app."""
    app = Flask(__name__)
    app.secret_key = os.urandom(24)  # For flash messages

    # Define database paths
    # Find all simulation database files
    db_base_path = os.environ.get(
        "DB_BASE_PATH", "simulations/"
    )  # Base directory to search
    db_pattern = os.path.join(db_base_path, "simulation_*.db")
    db_files = {}

    print(db_base_path)
    # Get all matching database files
    for db_path in glob.glob(db_pattern):
        # Create a blueprint name from the filename (without extension)
        db_name = os.path.basename(db_path).split(".")[0]
        db_files[db_name] = db_path


    # Fallback if no databases found
    if not db_files:
        logging.warning(
            "No simulation database files found matching pattern simulation_*.db"
        )
        return 

    # Store database names for use in templates
    app.config["DATABASE_NAMES"] = sorted(list(db_files.keys()))

    # Create and register blueprints for each database
    for name, path in db_files.items():
        logging.info(f"Registering database: {name} at {path}")
        bp = create_db_blueprint(path, name)
        app.register_blueprint(bp)

    # Add context processor to make database names available in all templates
    @app.context_processor
    def inject_database_names():
        return {
            "database_names": app.config["DATABASE_NAMES"],
            "format_db_name": format_db_name,
        }

    @app.template_filter("format_db_name")
    def format_db_name(db_name):
        """Format database name to a readable format with date/time."""
        try:
            # Extract timestamp from the database name
            parts = db_name.split("_")
            for part in parts:
                if part.isdigit() and len(part) >= 10:  # Likely a Unix timestamp
                    timestamp = int(part)
                    dt = datetime.datetime.fromtimestamp(timestamp)
                    formatted_date = dt.strftime("%d/%m %H:%M")

                    # Get the simulation name (e.g., snaxxx)
                    sim_name = ""
                    for p in parts:
                        if not p.isdigit() and p not in ["simulation", "run"]:
                            sim_name += p + " "
                    sim_name = sim_name.strip()

                    if sim_name:
                        return f"{sim_name} - {formatted_date}"
                    else:
                        return f"Simulation - {formatted_date}"

            # Fallback if no timestamp found
            return db_name.replace("simulation_", "").replace("_", " ").title()
        except Exception:
            # If any error occurs, just use the default formatting
            return db_name.replace("simulation_", "").replace("_", " ").title()

    # Root route to redirect to the first database or show a selection page
    @app.route("/")
    def index():
        if db_files:
            # Redirect to the first database
            first_db = next(iter(db_files))
            return redirect(url_for(f"{first_db}.index"))
        else:
            # If no databases, show an error
            flash("No database files found.", "danger")
            return render_template("no_databases.html")

    @app.errorhandler(404)
    def page_not_found(e):
        """Handle 404 errors."""
        return render_template("404.html"), 404

    @app.template_filter("nl2br")
    def nl2br_filter(value):
        """Convert newlines to <br> tags."""
        if value:
            result = value.replace("\n", "<br>")
            return Markup(result)
        return value

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Flask webapp.")
    parser.add_argument(
        "--db-folder",
        type=str,
        default=None,
        help="Folder containing simulation_*.db files",
    )
    args = parser.parse_args()

    print("setting db folder", args.db_folder)
    if args.db_folder:
        os.environ["DB_BASE_PATH"] = (
            args.db_folder
        )  # Set env var for use in create_app()

    # Create the application instance AFTER setting environment variables
    app = create_app()

    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, host="0.0.0.0", port=port)
else:
    # Create the application instance for WSGI servers
    app = create_app()
