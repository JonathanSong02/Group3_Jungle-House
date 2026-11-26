"""Member message files: metadata shares the message transaction; never public static URLs."""
import secrets
import re
from pathlib import Path

MAX_FILE_BYTES = 7 * 1024 * 1024  # Leave room for multipart headers within Flask's 8MB limit.


class AttachmentSchemaNotReady(RuntimeError):
    """The optional member-attachment migration has not been applied."""


def save_attachment(cursor, message_id, file, folder, mime):
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    reference = secrets.token_hex(32)
    name = re.sub(r"[\x00-\x1f\x7f]", "", Path(file.filename.replace("\\", "/")).name)[:255] or "attachment"
    path = root / reference
    try:
        file.save(path)
        cursor.execute("""INSERT INTO message_attachments
            (attachment_id, message_id, storage_name, original_name, mime_type, byte_size)
            VALUES (%s, %s, %s, %s, %s, %s)""",
            (reference, message_id, reference, name, mime, path.stat().st_size))
    except Exception as error:
        path.unlink(missing_ok=True)
        if getattr(error, "errno", None) == 1146:
            raise AttachmentSchemaNotReady() from error
        raise
    return path


def add_attachments(cursor, messages):
    if not messages:
        return messages
    for row in messages:
        row["attachments"] = []
    ids = [row["message_id"] for row in messages]
    try:
        cursor.execute("SELECT attachment_id, message_id, original_name AS name, "
                       "mime_type AS type, byte_size AS size FROM message_attachments "
                       "WHERE message_id IN (" + ",".join(["%s"] * len(ids)) + ")", tuple(ids))
    except Exception as error:
        # MySQL missing-table errors do not abort the transaction. Text messages
        # must work during a rolling deployment before the optional migration.
        if getattr(error, "errno", None) == 1146:
            return messages
        raise
    by_id = {row["message_id"]: row for row in messages}
    for attachment in cursor.fetchall():
        attachment["url"] = "/api/messages/attachments/" + attachment["attachment_id"]
        by_id[attachment["message_id"]]["attachments"].append(attachment)
    return messages
