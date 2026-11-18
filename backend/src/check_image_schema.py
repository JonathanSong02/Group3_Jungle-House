"""Read-only deployment preflight. Never creates tables or applies migrations.

Run in the backend directory: python src/check_image_schema.py
MYSQL_* must point at the intended environment. No credentials are printed.
"""
from db_helper import get_db_connection

REQUIRED_COLUMNS = {
    "chat_attachments": {"attachment_id", "owner_id", "chat_key", "storage_name", "mime_type",
                         "image_hash", "observations", "created_at", "expires_at"},
    "image_retrieval": {"image_hash", "source_hash", "indexed_at", "index_error", "embedding_model"},
}


def missing_columns(connection):
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN (%s, %s)""",
            tuple(REQUIRED_COLUMNS))
        existing = {(row["TABLE_NAME"], row["COLUMN_NAME"]) for row in cursor.fetchall()}
        return sorted(f"{table}.{column}" for table, columns in REQUIRED_COLUMNS.items()
                      for column in columns if (table, column) not in existing)
    finally:
        cursor.close()


def main(connect=get_db_connection, out=print):
    connection = None
    try:
        connection = connect()
        missing = missing_columns(connection)
        if missing:
            out("IMAGE_SCHEMA_NOT_READY: reviewed migration 0004 is required before this release.")
            out("Missing required columns: " + ", ".join(missing))
            out("No database changes were made. Review tools/migrate.py status and apply --dry-run first.")
            return 1
        out("Image schema preflight passed (read-only; no database changes).")
        return 0
    except Exception as error:
        out(f"IMAGE_SCHEMA_CHECK_UNAVAILABLE: {type(error).__name__}; errno={getattr(error, 'errno', None)}. Check MYSQL_* configuration.")
        return 2
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
