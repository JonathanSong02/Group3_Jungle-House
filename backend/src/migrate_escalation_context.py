"""One additive Railway pre-deploy migration; never imports the Flask app.

Uses the same MYSQL_* environment variables as db_helper. It creates only the
optional escalation discussion table, without copying or changing ticket data.
Run from backend/: python src/migrate_escalation_context.py
"""

import os
import re
import sys
from pathlib import Path


# Kept in sync with mysql/escalation_context.sql. Embed the single reviewed DDL
# because Railway's backend build may not include the repository's mysql/ folder.
CREATE_CONTEXT_TABLE = """
CREATE TABLE IF NOT EXISTS escalation_context (
    escalation_id INT NOT NULL PRIMARY KEY,
    conversation_id VARCHAR(96) NOT NULL,
    issue_id VARCHAR(96) NOT NULL,
    context_json MEDIUMTEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_escalation_context_ticket
        FOREIGN KEY (escalation_id) REFERENCES escalation(escalation_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""
REQUIRED_COLUMNS = {
    "escalation_id", "conversation_id", "issue_id", "context_json", "created_at"
}


class MigrationError(Exception):
    """Contains only safe, authored diagnostics, never driver error messages."""


def migrate(connection):
    """Check the parent table before DDL; repeated deployments retain all rows."""
    cursor = connection.cursor(dictionary=True)
    try:
        # Bound waits for a concurrent deployment's metadata lock.
        cursor.execute("SET SESSION lock_wait_timeout = 30")
        cursor.execute("SELECT DATABASE() AS selected_database")
        row = cursor.fetchone()
        if not row or not row["selected_database"]:
            raise MigrationError("No target database selected; check MYSQL_DATABASE.")

        cursor.execute("""
            SELECT c.COLUMN_TYPE, c.COLUMN_KEY, t.ENGINE
            FROM information_schema.COLUMNS c
            JOIN information_schema.TABLES t
              ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME
            WHERE c.TABLE_SCHEMA = DATABASE()
              AND c.TABLE_NAME = 'escalation' AND c.COLUMN_NAME = 'escalation_id'
        """)
        parent = cursor.fetchone()
        if not parent:
            raise MigrationError("Parent escalation table/key is missing; verify the target database.")
        if (not re.fullmatch(r"int(?:\(\d+\))?", parent["COLUMN_TYPE"].lower())
                or parent["COLUMN_KEY"] != "PRI"
                or (parent["ENGINE"] or "").lower() != "innodb"):
            raise MigrationError("Parent escalation key must be a signed INT primary key in InnoDB; no schema changed.")

        cursor.execute(CREATE_CONTEXT_TABLE)
        cursor.execute("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'escalation_context'
        """)
        columns = {row["COLUMN_NAME"] for row in cursor.fetchall()}
        if not REQUIRED_COLUMNS.issubset(columns):
            raise MigrationError("Existing escalation_context schema is incompatible; manual review required.")
    finally:
        cursor.close()


def main():
    connection = None
    try:
        # Railway provides process variables; dotenv is only a local fallback.
        from dotenv import load_dotenv
        import mysql.connector

        load_dotenv(Path(__file__).with_name(".env"))
        required = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_DATABASE", "MYSQL_PASSWORD")
        missing = [name for name in required if os.getenv(name) is None
                   or (name != "MYSQL_PASSWORD" and not os.getenv(name))]
        if missing:
            raise MigrationError("Missing environment variables: " + ", ".join(missing))
        try:
            port = int(os.getenv("MYSQL_PORT", "3306"))
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            raise MigrationError("MYSQL_PORT must be a valid port number.") from None

        connection = mysql.connector.connect(
            host=os.environ["MYSQL_HOST"], port=port,
            user=os.environ["MYSQL_USER"], password=os.environ["MYSQL_PASSWORD"],
            database=os.environ["MYSQL_DATABASE"], connection_timeout=10,
        )
        migrate(connection)
        print("Escalation context migration ready; existing ticket and discussion data retained.")
        return 0
    except MigrationError as error:
        print("Escalation context migration failed: " + str(error), file=sys.stderr)
        return 1
    except Exception as error:
        # Driver messages can contain database hosts, account names or SQL/data.
        errno = getattr(error, "errno", None)
        code = str(errno) if isinstance(errno, int) else "unavailable"
        print("Escalation context migration failed (error code: " + code
              + "); check database access, CREATE permission and schema.", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                # Do not leak driver details or mask the migration result.
                pass


if __name__ == "__main__":
    sys.exit(main())
