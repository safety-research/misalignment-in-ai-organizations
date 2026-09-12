import sqlite3
import time
import logging
import threading
from typing import List, Optional, Dict, Any
import shutil
from datetime import datetime
import os
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class DatabaseRepository:
    """Handles all database interactions for the AI organization simulation."""

    # Schema version - increment when making breaking changes
    SCHEMA_VERSION = 2

    # Thread-local storage for database connections
    _local = threading.local()

    def __init__(self, db_path: str):
        """
        Initializes the database connection and creates tables if they don't exist.

        Args:
            db_path: The path to the SQLite database file.
        """
        self.db_path = db_path
        # Initialize the connection for the current thread
        self._get_connection()
        logging.info(f"Connected to database: {self.db_path}")
        self._initialize_database()

    def _get_connection(self):
        """Gets a thread-local connection and cursor or creates them if they don't exist."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            try:
                self._local.conn = sqlite3.connect(self.db_path)
                self._local.cursor = self._local.conn.cursor()
                logging.debug(
                    f"Created new database connection for thread {threading.current_thread().name}"
                )
            except sqlite3.Error as e:
                logging.error(f"Database error creating connection: {e}")
                raise

        return self._local.conn, self._local.cursor

    def _initialize_database(self):
        """Initialize the database schema or migrate if needed."""
        try:
            conn, cursor = self._get_connection()

            # Check if the metadata table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'"
            )
            metadata_exists = cursor.fetchone() is not None
            creating_new_db = False

            if not metadata_exists:
                # If no metadata table, either it's a new DB or an old one needing migration
                self._create_metadata_table()

                # Check if other tables exist (indicating this is an old DB)
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
                )
                agents_exists = cursor.fetchone() is not None

                if agents_exists:
                    # This is an existing database without metadata - set version to 1
                    self._set_schema_version(1)
                    logging.info(
                        "Migrating existing database to schema versioning system"
                    )
                else:
                    # This is a completely new database
                    self._set_schema_version(self.SCHEMA_VERSION)
                    creating_new_db = True
                    logging.info(
                        f"Initializing new database with schema version {self.SCHEMA_VERSION}"
                    )

            # Get current schema version
            current_version = self._get_schema_version()
            logging.info(f"Current database schema version: {current_version}")

            # Create base schema (idempotent)
            self._create_base_schema()
            if creating_new_db:
                self._apply_migrations(0)

            # Apply migrations if needed
            if current_version < self.SCHEMA_VERSION:
                self._backup_database()
                self._apply_migrations(current_version)
                self._set_schema_version(self.SCHEMA_VERSION)
                logging.info(f"Database migrated to version {self.SCHEMA_VERSION}")

            conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Database initialization error: {e}")
            conn, _ = self._get_connection()
            conn.rollback()
            raise

    def _backup_database(self):
        """Backup the current database to a new file with a timestamp."""
        # Create backups directory if it doesn't exist
        backup_dir = os.path.join(os.path.dirname(self.db_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)

        # Create backup with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{os.path.basename(self.db_path)}.{timestamp}.bak"
        backup_path = os.path.join(backup_dir, backup_filename)

        shutil.copy2(self.db_path, backup_path)
        logging.info(f"Database backed up to {backup_path}")

    def _create_metadata_table(self):
        """Create metadata table for tracking schema version and experiment configuration."""
        conn, cursor = self._get_connection()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """
        )
        conn.commit()
        logging.info("Created metadata table")

    def _set_schema_version(self, version):
        """Set the schema version in metadata table."""
        conn, cursor = self._get_connection()
        cursor.execute(
            """
            INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', ?)
        """,
            (str(version),),
        )
        conn.commit()

    def _get_schema_version(self):
        """Get the current schema version from metadata table."""
        conn, cursor = self._get_connection()
        cursor.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
        result = cursor.fetchone()

        if result:
            return int(result[0])
        return 0  # Default to 0 if no version found

    def _create_base_schema(self):
        """Create the base schema tables (idempotent)."""
        conn, cursor = self._get_connection()

        # Agents table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                agent_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                system_prompt TEXT NOT NULL,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """
        )

        # Messages table (for agent internal thoughts/API calls)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
            )
        """
        )

        # Emails table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS emails (
                email_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_agent_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                FOREIGN KEY(sender_agent_id) REFERENCES agents(agent_id)
            )
        """
        )

        # Email Recipients table (to handle multiple recipients)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS email_recipients (
                email_id INTEGER NOT NULL,
                recipient_agent_id INTEGER NOT NULL,
                PRIMARY KEY (email_id, recipient_agent_id),
                FOREIGN KEY(email_id) REFERENCES emails(email_id),
                FOREIGN KEY(recipient_agent_id) REFERENCES agents(agent_id)
            )
        """
        )

        conn.commit()
        logging.info("Base database schema created")

    def _apply_migrations(self, current_version):
        """Apply migrations to update the schema to the latest version."""
        try:
            # Apply migrations incrementally
            if current_version < 2:
                self._migrate_to_v2()

            # Add future migrations here with version checks
            # if current_version < 3:
            #     self._migrate_to_v3()

            logging.info(
                f"Successfully migrated database from version {current_version} to {self.SCHEMA_VERSION}"
            )
        except sqlite3.Error as e:
            logging.error(f"Migration error: {e}")
            conn, _ = self._get_connection()
            conn.rollback()
            raise

    def _migrate_to_v2(self):
        """Migrate database to version 2: add org_level and iteration_id columns."""
        conn, cursor = self._get_connection()

        # Add org_level to agents
        self._add_column_if_not_exists("agents", "org_level", "INTEGER DEFAULT 0")

        # Add iteration_id to emails
        self._add_column_if_not_exists("emails", "iteration_id", "INTEGER DEFAULT 0")

        # Add iteration_id to messages
        self._add_column_if_not_exists("messages", "iteration_id", "INTEGER DEFAULT 0")

        conn.commit()
        logging.info(
            "Applied migration to version 2: added org_level and iteration_id columns"
        )

    def _add_column_if_not_exists(self, table, column, definition):
        """Add a column to a table if it doesn't already exist."""
        try:
            conn, cursor = self._get_connection()

            # Check if column exists
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [info[1] for info in cursor.fetchall()]

            if column not in columns:
                logging.info(f"Adding column '{column}' to table '{table}'")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                return True
            return False
        except sqlite3.Error as e:
            logging.error(f"Error adding column '{column}' to table '{table}': {e}")
            raise

    def add_agent(self, name: str, system_prompt: str, org_level: int = 0) -> int:
        """
        Adds a new agent to the database.

        Args:
            name: The name of the agent.
            system_prompt: The system prompt for the agent.
            org_level: The organizational hierarchy level (0 = top, higher numbers = lower levels).

        Returns:
            The ID of the newly inserted agent.

        Raises:
            sqlite3.Error: If a database error occurs.
        """
        try:
            conn, cursor = self._get_connection()

            cursor.execute(
                "INSERT INTO agents (name, system_prompt, org_level) VALUES (?, ?, ?)",
                (name, system_prompt, org_level),
            )

            conn.commit()
            agent_id = cursor.lastrowid
            logging.info(
                f"Added agent '{name}' with ID {agent_id} to database at org level {org_level}."
            )
            return agent_id
        except sqlite3.IntegrityError:
            logging.warning(f"Agent with name '{name}' already exists. Fetching ID.")
            return self.get_agent_id(
                name
            )  # Return existing ID if name is unique constraint violated
        except sqlite3.Error as e:
            logging.error(f"Database error adding agent '{name}': {e}")
            conn, _ = self._get_connection()
            conn.rollback()
            raise

    def get_agent_id(self, name: str) -> Optional[int]:
        """
        Retrieves the ID of an agent by name.

        Args:
            name: The name of the agent.

        Returns:
            The agent's ID, or None if not found.
        """
        try:
            conn, cursor = self._get_connection()
            cursor.execute("SELECT agent_id FROM agents WHERE name = ?", (name,))
            result = cursor.fetchone()
            if result:
                logging.debug(f"Found agent ID {result[0]} for name '{name}'.")
                return result[0]
            else:
                logging.warning(f"Agent ID not found for name '{name}'.")
                return None
        except sqlite3.Error as e:
            logging.error(f"Database error getting agent ID for '{name}': {e}")
            return None  # Return None on error

    def get_all_agent_names(self) -> List[str]:
        """Retrieves the names of all agents in the database."""
        try:
            conn, cursor = self._get_connection()
            cursor.execute("SELECT name FROM agents ORDER BY name")
            results = cursor.fetchall()
            names = [row[0] for row in results]
            logging.debug(f"Retrieved {len(names)} agent names from database.")
            return names
        except sqlite3.Error as e:
            logging.error(f"Database error getting all agent names: {e}")
            return []

    def add_message(
        self,
        agent_id: int,
        role: str,
        content: str,
        timestamp: float,
        iteration_id: int = 0,
    ) -> int:
        """
        Adds a message associated with an agent to the database.

        Args:
            agent_id: The ID of the agent associated with the message.
            role: The role of the message ('user' or 'assistant').
            content: The content of the message.
            timestamp: The time the message was created/recorded.
            iteration_id: The processing iteration during which this message was generated.

        Returns:
            The ID of the newly inserted message.

        Raises:
            sqlite3.Error: If a database error occurs.
        """
        try:
            conn, cursor = self._get_connection()

            cursor.execute(
                "INSERT INTO messages (agent_id, role, content, timestamp, iteration_id) VALUES (?, ?, ?, ?, ?)",
                (agent_id, role, content, timestamp, iteration_id),
            )

            conn.commit()
            message_id = cursor.lastrowid
            logging.debug(
                f"Added message with ID {message_id} for agent {agent_id} in iteration {iteration_id}."
            )
            return message_id
        except sqlite3.Error as e:
            logging.error(f"Database error adding message for agent {agent_id}: {e}")
            conn, _ = self._get_connection()
            conn.rollback()
            raise

    def add_email(
        self,
        sender_agent_id: int,
        recipient_agent_ids: List[int],
        subject: str,
        content: str,
        timestamp: float,
        iteration_id: int = 0,
    ) -> int:
        """
        Adds an email and its recipients to the database.

        Args:
            sender_agent_id: The ID of the sending agent.
            recipient_agent_ids: A list of IDs for the recipient agents.
            subject: The subject of the email.
            content: The content of the email.
            timestamp: The time the email was sent/recorded.
            iteration_id: The processing iteration during which this email was generated.

        Returns:
            The ID of the newly inserted email.

        Raises:
            sqlite3.Error: If a database error occurs.
        """
        try:
            conn, cursor = self._get_connection()

            cursor.execute(
                "INSERT INTO emails (sender_agent_id, subject, content, timestamp, iteration_id) VALUES (?, ?, ?, ?, ?)",
                (sender_agent_id, subject, content, timestamp, iteration_id),
            )

            email_id = cursor.lastrowid

            # Insert recipient mappings
            recipient_data = [
                (email_id, recipient_id) for recipient_id in recipient_agent_ids
            ]
            cursor.executemany(
                "INSERT INTO email_recipients (email_id, recipient_agent_id) VALUES (?, ?)",
                recipient_data,
            )

            conn.commit()
            logging.info(
                f"Added email with ID {email_id} from agent {sender_agent_id} to agents {recipient_agent_ids} in iteration {iteration_id}."
            )
            return email_id
        except sqlite3.Error as e:
            logging.error(
                f"Database error adding email from agent {sender_agent_id}: {e}"
            )
            conn, _ = self._get_connection()
            conn.rollback()
            raise

    def get_conversation_log(self) -> List[Dict[str, Any]]:
        """
        Retrieves the entire email conversation log from the database.

        Returns:
            A list of dictionaries, each representing an email with sender/recipient names and iteration info.
        """
        log = []
        try:
            conn, cursor = self._get_connection()

            # After migration, all fields should exist, so we can use the full query
            query = """
                SELECT 
                    e.email_id, e.timestamp, a_sender.name AS sender_name, 
                    e.subject, e.content, e.iteration_id, a_sender.org_level
                FROM emails e
                JOIN agents a_sender ON e.sender_agent_id = a_sender.agent_id
                ORDER BY e.timestamp
            """

            cursor.execute(query)
            emails = cursor.fetchall()

            for (
                email_id,
                timestamp,
                sender_name,
                subject,
                content,
                iteration_id,
                org_level,
            ) in emails:
                # Get recipient information
                cursor.execute(
                    """
                    SELECT a_recipient.name, a_recipient.org_level
                    FROM email_recipients er
                    JOIN agents a_recipient ON er.recipient_agent_id = a_recipient.agent_id
                    WHERE er.email_id = ?
                """,
                    (email_id,),
                )
                recipients = cursor.fetchall()
                recipient_names = [r[0] for r in recipients]
                recipient_levels = [r[1] for r in recipients]

                # Create the email entry with all fields
                email_entry = {
                    "email_id": email_id,
                    "timestamp": timestamp,
                    "sender": sender_name,
                    "sender_level": org_level,
                    "recipients": recipient_names,
                    "recipient_levels": recipient_levels,
                    "subject": subject,
                    "content": content,
                    "iteration_id": iteration_id,
                }

                log.append(email_entry)

            logging.info(f"Retrieved {len(log)} emails for conversation log.")
            return log
        except sqlite3.Error as e:
            logging.error(f"Database error retrieving conversation log: {e}")
            return []  # Return empty log on error

    def get_agent_messages(self, agent_id: int) -> List[Dict[str, Any]]:
        """
        Retrieves all internal messages (API exchanges) for a specific agent.

        Args:
            agent_id: The ID of the agent.

        Returns:
            A list of dictionaries containing the message data including iteration info.
        """
        messages = []
        try:
            conn, cursor = self._get_connection()

            # After migration, all columns should exist
            query = """
                SELECT message_id, role, content, timestamp, iteration_id
                FROM messages
                WHERE agent_id = ?
                ORDER BY timestamp
            """

            cursor.execute(query, (agent_id,))

            rows = cursor.fetchall()
            for message_id, role, content, timestamp, iteration_id in rows:
                message = {
                    "message_id": message_id,
                    "role": role,
                    "content": content,
                    "timestamp": timestamp,
                    "iteration_id": iteration_id,
                }
                messages.append(message)
            logging.info(f"Retrieved {len(messages)} messages for agent ID {agent_id}.")
            return messages
        except sqlite3.Error as e:
            logging.error(
                f"Database error retrieving messages for agent ID {agent_id}: {e}"
            )
            return []

    def get_messages_by_iteration(self, iteration_id: int) -> List[Dict[str, Any]]:
        """
        Retrieves all internal messages for a specific iteration.

        Args:
            iteration_id: The ID of the iteration.

        Returns:
            A list of dictionaries containing the message data.
        """
        messages = []
        try:
            conn, cursor = self._get_connection()

            # After migration, can use iteration_id directly
            cursor.execute(
                """
                SELECT m.message_id, a.name as agent_name, m.role, m.content, m.timestamp
                FROM messages m
                JOIN agents a ON m.agent_id = a.agent_id
                WHERE m.iteration_id = ?
                ORDER BY m.timestamp
            """,
                (iteration_id,),
            )

            rows = cursor.fetchall()
            for row in rows:
                message_id, agent_name, role, content, timestamp = row
                messages.append(
                    {
                        "message_id": message_id,
                        "agent_name": agent_name,
                        "role": role,
                        "content": content,
                        "timestamp": timestamp,
                        "iteration_id": iteration_id,
                    }
                )

            logging.info(
                f"Retrieved {len(messages)} messages for iteration ID {iteration_id}."
            )
            return messages
        except sqlite3.Error as e:
            logging.error(
                f"Database error retrieving messages for iteration ID {iteration_id}: {e}"
            )
            return []

    def get_total_email_count(self) -> int:
        """
        Returns the total number of emails in the database.

        Returns:
            int: The total number of emails.
        """
        try:
            conn, cursor = self._get_connection()
            cursor.execute("SELECT COUNT(*) FROM emails")
            count = cursor.fetchone()[0]
            logging.debug(f"Retrieved total email count: {count}")
            return count
        except sqlite3.Error as e:
            logging.error(f"Database error getting total email count: {e}")
            return 0

    def get_agent_email_counts(self) -> dict:
        """
        Returns a dictionary of email counts per agent, including both sent and received.

        Returns:
            Dict[str, int]: Dictionary with agent names as keys and their email counts as values.
        """
        agent_counts = {}
        try:
            conn, cursor = self._get_connection()
            # Get all agent names first
            agents = self.get_all_agent_names()
            for agent_name in agents:
                agent_id = self.get_agent_id(agent_name)
                if agent_id is None:
                    continue

                # Count emails sent by this agent
                cursor.execute(
                    "SELECT COUNT(*) FROM emails WHERE sender_agent_id = ?", (agent_id,)
                )
                sent_count = cursor.fetchone()[0]

                # Count emails received by this agent
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT emails.email_id)
                    FROM emails
                    JOIN email_recipients ON emails.email_id = email_recipients.email_id
                    WHERE email_recipients.recipient_agent_id = ?
                    """,
                    (agent_id,),
                )
                received_count = cursor.fetchone()[0]

                # Total emails = sent + received
                agent_counts[agent_name] = sent_count + received_count

            logging.debug(f"Retrieved email counts for {len(agent_counts)} agents")
            return agent_counts
        except sqlite3.Error as e:
            logging.error(f"Database error getting agent email counts: {e}")
            return {}

    def get_agent_message_counts(self) -> dict:
        """
        Returns a dictionary of API message counts per agent.

        Returns:
            Dict[str, int]: Dictionary with agent names as keys and their message counts as values.
        """
        message_counts = {}
        try:
            # Get all agent names first
            conn, cursor = self._get_connection()
            agents = self.get_all_agent_names()
            for agent_name in agents:
                agent_id = self.get_agent_id(agent_name)
                if agent_id is None:
                    continue

                # Count messages for this agent
                cursor.execute(
                    "SELECT COUNT(*) FROM messages WHERE agent_id = ?", (agent_id,)
                )
                count = cursor.fetchone()[0]
                message_counts[agent_name] = count

            logging.debug(f"Retrieved message counts for {len(message_counts)} agents")
            return message_counts
        except sqlite3.Error as e:
            logging.error(f"Database error getting agent message counts: {e}")
            return {}

    def close(self):
        """Closes the thread-local database connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.commit()  # Ensure any pending changes are saved
                self._local.conn.close()
                self._local.conn = None
                self._local.cursor = None
                logging.info(
                    f"Database connection closed for thread {threading.current_thread().name}"
                )
            except sqlite3.Error as e:
                logging.error(f"Database error during close: {e}")

    def update_agent_org_level(self, agent_id: int, org_level: int) -> bool:
        """
        Updates the organizational level of an agent for visualization purposes.

        Args:
            agent_id: The ID of the agent to update.
            org_level: The organizational hierarchy level (0 = top, higher numbers = lower levels).

        Returns:
            Boolean indicating if the update was successful.
        """
        try:
            conn, cursor = self._get_connection()
            cursor.execute(
                "UPDATE agents SET org_level = ? WHERE agent_id = ?",
                (org_level, agent_id),
            )
            conn.commit()
            success = cursor.rowcount > 0
            if success:
                logging.info(
                    f"Updated agent ID {agent_id} organization level to {org_level}."
                )
            else:
                logging.warning(
                    f"No agent found with ID {agent_id} to update organization level."
                )
            return success
        except sqlite3.Error as e:
            logging.error(
                f"Database error updating organization level for agent {agent_id}: {e}"
            )
            conn, _ = self._get_connection()
            conn.rollback()
            return False

    def get_iteration_summary(self) -> List[Dict[str, Any]]:
        """
        Retrieves a summary of emails and messages grouped by iteration ID.

        Returns:
            A list of dictionaries containing iteration summaries.
        """
        summary = []
        try:
            conn, cursor = self._get_connection()
            # Get distinct iteration IDs and their email counts
            cursor.execute(
                """
                SELECT 
                    i.iteration_id, 
                    COUNT(DISTINCT e.email_id) as email_count,
                    COUNT(DISTINCT m.message_id) as message_count,
                    MIN(COALESCE(e.timestamp, m.timestamp)) as start_time, 
                    MAX(COALESCE(e.timestamp, m.timestamp)) as end_time
                FROM (
                    SELECT DISTINCT iteration_id FROM emails
                    UNION 
                    SELECT DISTINCT iteration_id FROM messages
                ) i
                LEFT JOIN emails e ON i.iteration_id = e.iteration_id
                LEFT JOIN messages m ON i.iteration_id = m.iteration_id
                GROUP BY i.iteration_id
                ORDER BY i.iteration_id
            """
            )

            iterations = cursor.fetchall()
            for (
                iteration_id,
                email_count,
                message_count,
                start_time,
                end_time,
            ) in iterations:
                # For each iteration, get the distinct agents involved
                cursor.execute(
                    """
                    SELECT DISTINCT a.name
                    FROM (
                        SELECT sender_agent_id as agent_id FROM emails WHERE iteration_id = ?
                        UNION
                        SELECT recipient_agent_id FROM email_recipients er
                        JOIN emails e ON er.email_id = e.email_id WHERE e.iteration_id = ?
                        UNION
                        SELECT agent_id FROM messages WHERE iteration_id = ?
                    ) active_agents
                    JOIN agents a ON active_agents.agent_id = a.agent_id
                """,
                    (iteration_id, iteration_id, iteration_id),
                )

                agents_involved = [row[0] for row in cursor.fetchall()]

                summary.append(
                    {
                        "iteration_id": iteration_id,
                        "email_count": email_count,
                        "message_count": message_count,
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration": (
                            end_time - start_time if start_time and end_time else 0
                        ),
                        "agents_involved": agents_involved,
                    }
                )

            logging.info(f"Retrieved summary for {len(summary)} iterations.")
            return summary
        except sqlite3.Error as e:
            logging.error(f"Database error retrieving iteration summary: {e}")
            return []

    def get_agent_system_prompt(self, agent_id: int) -> Optional[str]:
        """
        Retrieves the system prompt for a specific agent.

        Args:
            agent_id: The ID of the agent.

        Returns:
            The system prompt string or None if the agent is not found.
        """
        try:
            conn, cursor = self._get_connection()
            cursor.execute(
                "SELECT system_prompt FROM agents WHERE agent_id = ?", (agent_id,)
            )
            result = cursor.fetchone()
            if result:
                logging.debug(f"Retrieved system prompt for agent ID {agent_id}.")
                return result[0]
            else:
                logging.warning(f"No system prompt found for agent ID {agent_id}.")
                return None
        except sqlite3.Error as e:
            logging.error(
                f"Database error retrieving system prompt for agent ID {agent_id}: {e}"
            )
            return None

    def set_experiment_config(self, config_dict: Dict[str, Any]) -> bool:
        """
        Stores experiment configuration as JSON in the metadata table.

        Args:
            config_dict: Dictionary containing experiment configuration

        Returns:
            Boolean indicating if the operation was successful
        """
        try:
            conn, cursor = self._get_connection()
            config_json = json.dumps(config_dict)

            cursor.execute(
                """
                INSERT OR REPLACE INTO metadata (key, value) 
                VALUES ('experiment_config', ?)
            """,
                (config_json,),
            )

            conn.commit()
            logging.info(f"Saved experiment configuration: {config_dict}")
            return True
        except sqlite3.Error as e:
            logging.error(f"Database error saving experiment configuration: {e}")
            conn, _ = self._get_connection()
            conn.rollback()
            return False
        except Exception as e:
            logging.error(f"Error saving experiment configuration: {e}")
            return False

    def get_experiment_config(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves the experiment configuration.

        Returns:
            Dictionary containing experiment configuration or None if not found
        """
        try:
            conn, cursor = self._get_connection()

            cursor.execute("SELECT value FROM metadata WHERE key = 'experiment_config'")
            result = cursor.fetchone()

            if result:
                config_json = result[0]
                config_dict = json.loads(config_json)
                logging.debug(f"Retrieved experiment configuration: {config_dict}")
                return config_dict
            else:
                logging.info("No experiment configuration found")
                return None
        except sqlite3.Error as e:
            logging.error(f"Database error retrieving experiment configuration: {e}")
            return None
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding experiment configuration JSON: {e}")
            return None
        except Exception as e:
            logging.error(f"Error retrieving experiment configuration: {e}")
            return None


# Example usage (optional, for testing the repository directly)
if __name__ == "__main__":
    db_file = f"test_repo_{int(time.time())}.db"
    print(f"Creating test database: {db_file}")
    repo = None
    try:
        repo = DatabaseRepository(db_file)
        print("Database repository initialized.")

        # Add agents
        agent1_id = repo.add_agent("AgentAlpha", "System prompt for Alpha.", 0)
        agent2_id = repo.add_agent("AgentBeta", "System prompt for Beta.", 0)
        print(f"Added agents: Alpha ID={agent1_id}, Beta ID={agent2_id}")

        # Add a message
        msg_ts = time.time()
        msg_id = repo.add_message(agent1_id, "user", "Initial instruction.", msg_ts)
        print(f"Added message ID={msg_id}")

        # Add an email
        email_ts = time.time()
        email_id = repo.add_email(
            agent1_id, [agent2_id], "Project Update", "Work is proceeding.", email_ts
        )
        print(f"Added email ID={email_id}")

        # Test fetching agent ID
        retrieved_id = repo.get_agent_id("AgentAlpha")
        print(
            f"Retrieved AgentAlpha ID: {retrieved_id}, Match: {retrieved_id == agent1_id}"
        )
        retrieved_id_nonexistent = repo.get_agent_id("AgentGamma")
        print(
            f"Retrieved AgentGamma ID: {retrieved_id_nonexistent}, Match: {retrieved_id_nonexistent is None}"
        )

        # Test adding duplicate agent
        agent1_id_dup = repo.add_agent("AgentAlpha", "Updated prompt.", 0)
        print(
            f"Attempted adding duplicate AgentAlpha. Got ID: {agent1_id_dup}, Match: {agent1_id_dup == agent1_id}"
        )

    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
    finally:
        if repo:
            repo.close()
            print("Database connection closed.")
        # Optional: Clean up the test database file
        # import os
        # try:
        #     os.remove(db_file)
        #     print(f"Removed test database: {db_file}")
        # except OSError as e:
        #     print(f"Error removing test database file: {e}")
