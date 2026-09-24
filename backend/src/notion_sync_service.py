import os
import re
import json
import time
import mysql.connector
import requests
from flask import request as flask_request

# Reuse the exact same encryption approach already built and proven for AI
# provider keys, instead of inventing a second encryption scheme.
import ai_provider_service


def get_public_base_url():
    """
    Same fix as the earlier mixed-content bug: Railway terminates TLS at
    its edge, so request.host_url resolves to http:// even though the site
    is always served over https. The frontend and backend are on
    completely different domains (Vercel / Railway), so any image URL we
    bake into article content MUST be absolute -- a relative path only
    ever resolves against whichever domain is currently loaded.
    """
    try:
        base_url = flask_request.host_url.rstrip("/")
    except RuntimeError:
        return "http://localhost:4000"

    if base_url.startswith("http://"):
        base_url = "https://" + base_url[len("http://"):]

    return base_url


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


# =========================
# DATABASE CONNECTION (own connection, same pattern as db_helper.py /
# ai_provider_service.py, to avoid a circular import with app.py)
# =========================
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
    )


# =========================
# TABLE / COLUMN SETUP
# =========================
def _column_exists(cursor, table_name, column_name):
    cursor.execute("""
        SELECT COUNT(*) AS c
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
    """, (table_name, column_name))
    row = cursor.fetchone()
    count = row["c"] if isinstance(row, dict) else row[0]
    return count > 0


def ensure_notion_columns_on_wiki_article(cursor):
    if not _column_exists(cursor, "wiki_article", "source_type"):
        cursor.execute("""
            ALTER TABLE wiki_article
            ADD COLUMN source_type VARCHAR(20) DEFAULT 'manual'
        """)

    if not _column_exists(cursor, "wiki_article", "notion_page_id"):
        cursor.execute("""
            ALTER TABLE wiki_article
            ADD COLUMN notion_page_id VARCHAR(64) NULL,
            ADD UNIQUE INDEX idx_wiki_article_notion_page_id (notion_page_id)
        """)

    if not _column_exists(cursor, "wiki_article", "notion_last_edited_time"):
        cursor.execute("""
            ALTER TABLE wiki_article
            ADD COLUMN notion_last_edited_time DATETIME NULL
        """)


def ensure_notion_sync_tables(cursor):
    ensure_notion_columns_on_wiki_article(cursor)

    # source_id/encrypted_notion_token kept NOT NULL for backward compatibility
    # with any existing row from the old token-paste flow, but the OAuth flow
    # below writes empty strings into them and uses the new columns instead --
    # dropping/renaming them would risk losing whatever is already saved.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notion_sync_configs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            encrypted_notion_token TEXT NOT NULL,
            source_id VARCHAR(255) NOT NULL,
            source_name VARCHAR(255) NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            created_by INT NULL,
            updated_by INT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_notion_sync_configs_active (is_active)
        )
    """)

    config_columns = {
        "encrypted_access_token": "ALTER TABLE notion_sync_configs ADD COLUMN encrypted_access_token TEXT NULL",
        "notion_workspace_id": "ALTER TABLE notion_sync_configs ADD COLUMN notion_workspace_id VARCHAR(64) NULL",
        "notion_workspace_name": "ALTER TABLE notion_sync_configs ADD COLUMN notion_workspace_name VARCHAR(255) NULL",
        "notion_workspace_icon": "ALTER TABLE notion_sync_configs ADD COLUMN notion_workspace_icon VARCHAR(500) NULL",
        "notion_bot_id": "ALTER TABLE notion_sync_configs ADD COLUMN notion_bot_id VARCHAR(64) NULL",
    }
    existing_config_columns = {
        row["Field"] if isinstance(row, dict) else row[0]
        for row in _describe_table(cursor, "notion_sync_configs")
    }
    for column_name, statement in config_columns.items():
        if column_name not in existing_config_columns:
            cursor.execute(statement)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notion_sync_jobs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            status VARCHAR(50) NOT NULL,
            imported_count INT DEFAULT 0,
            updated_count INT DEFAULT 0,
            skipped_count INT DEFAULT 0,
            failed_count INT DEFAULT 0,
            error_message TEXT NULL,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME NULL,
            created_by INT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notion_oauth_states (
            state VARCHAR(64) PRIMARY KEY,
            created_by INT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL
        )
    """)

    # Lets a manager point this deployment at a different Notion public
    # integration (their own Client ID/Secret) from the Notion Sync page,
    # instead of needing Railway env var access -- e.g. when this system is
    # handed off to a different client who wants their own Notion app on
    # the consent screen. NOTION_OAUTH_CLIENT_ID/SECRET env vars remain the
    # fallback default when no row here is active (see
    # get_notion_oauth_credentials), so nothing already deployed breaks.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notion_oauth_apps (
            id INT AUTO_INCREMENT PRIMARY KEY,
            client_id VARCHAR(255) NOT NULL,
            encrypted_client_secret TEXT NOT NULL,
            client_secret_hint VARCHAR(20) NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            created_by INT NULL,
            updated_by INT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_notion_oauth_apps_active (is_active)
        )
    """)

    # article_id is NULL for a brand-new Notion page that hasn't been
    # imported yet (nothing to link to until a manager approves it) and set
    # for an edit to an already-imported article -- see
    # check_for_notion_updates/apply_pending_update, which branch on this.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notion_pending_updates (
            id INT AUTO_INCREMENT PRIMARY KEY,
            article_id INT NULL,
            notion_page_id VARCHAR(64) NOT NULL,
            proposed_title VARCHAR(500) NULL,
            proposed_content MEDIUMTEXT NULL,
            previous_title VARCHAR(500) NULL,
            previous_content MEDIUMTEXT NULL,
            notion_last_edited_time DATETIME NULL,
            status ENUM('pending', 'applied', 'dismissed') NOT NULL DEFAULT 'pending',
            detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_by INT NULL,
            resolved_at DATETIME NULL,
            INDEX idx_notion_pending_updates_article (article_id, status)
        )
    """)

    # Deployments that already created this table before article_id became
    # nullable need an explicit migration -- CREATE TABLE IF NOT EXISTS above
    # only applies to a fresh table.
    pending_updates_columns = {
        row["Field"] if isinstance(row, dict) else row[0]: row
        for row in _describe_table(cursor, "notion_pending_updates")
    }
    article_id_column = pending_updates_columns.get("article_id")
    if article_id_column:
        is_nullable = article_id_column["Null"] if isinstance(article_id_column, dict) else article_id_column[2]
        if str(is_nullable).upper() == "NO":
            cursor.execute("ALTER TABLE notion_pending_updates MODIFY COLUMN article_id INT NULL")


def _describe_table(cursor, table_name):
    cursor.execute(f"SHOW COLUMNS FROM {table_name}")
    return cursor.fetchall() or []


# =========================
# CONFIG READ / WRITE (single active config, same shape as
# ai_provider_configs -- reuses the same encrypt/decrypt/mask helpers)
# =========================
def get_active_notion_config(cursor):
    cursor.execute("""
        SELECT * FROM notion_sync_configs
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
    """)
    return cursor.fetchone()


def get_notion_public_config(cursor):
    """
    Connection status for the OAuth flow: whether a workspace is connected,
    and its name/icon -- never the access token itself. The old token-hint
    shape is no longer needed since the OAuth flow replaces manual token
    entry, but get_active_notion_config()/save_notion_config() (the old
    integration-token path) are left in place, unused, so any pre-existing
    row and the encrypted_notion_token/source_id NOT NULL columns are never
    touched or lost.
    """
    config = get_active_notion_config(cursor)

    if not config or not config.get("encrypted_access_token"):
        return None

    return {
        "connected": True,
        "workspaceId": config.get("notion_workspace_id"),
        "workspaceName": config.get("notion_workspace_name"),
        "workspaceIcon": config.get("notion_workspace_icon"),
        "updatedAt": (
            config["updated_at"].strftime("%d/%m/%Y %I:%M %p")
            if config.get("updated_at")
            else None
        ),
    }


def get_active_notion_access_token(cursor):
    config = get_active_notion_config(cursor)

    if not config or not config.get("encrypted_access_token"):
        return None

    return ai_provider_service.decrypt_api_key(config["encrypted_access_token"])


def save_notion_config(cursor, raw_token, source_id, source_name, actor_id):
    cursor.execute("UPDATE notion_sync_configs SET is_active = 0 WHERE is_active = 1")

    encrypted_token = ai_provider_service.encrypt_api_key(raw_token)

    cursor.execute("""
        INSERT INTO notion_sync_configs
        (encrypted_notion_token, source_id, source_name, is_active, created_by, updated_by)
        VALUES (%s, %s, %s, 1, %s, %s)
    """, (encrypted_token, source_id, source_name, actor_id, actor_id))

    return cursor.lastrowid


def save_notion_oauth_config(cursor, access_token, workspace_id, workspace_name, workspace_icon, bot_id, actor_id):
    cursor.execute("UPDATE notion_sync_configs SET is_active = 0 WHERE is_active = 1")

    encrypted_access_token = ai_provider_service.encrypt_api_key(access_token)

    cursor.execute("""
        INSERT INTO notion_sync_configs
        (encrypted_notion_token, source_id, source_name, is_active,
         encrypted_access_token, notion_workspace_id, notion_workspace_name,
         notion_workspace_icon, notion_bot_id, created_by, updated_by)
        VALUES ('', '', %s, 1, %s, %s, %s, %s, %s, %s, %s)
    """, (
        workspace_name, encrypted_access_token, workspace_id, workspace_name,
        workspace_icon, bot_id, actor_id, actor_id
    ))

    return cursor.lastrowid


def disconnect_notion(cursor):
    cursor.execute("UPDATE notion_sync_configs SET is_active = 0 WHERE is_active = 1")


def get_active_notion_oauth_app(cursor):
    cursor.execute("""
        SELECT * FROM notion_oauth_apps
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
    """)
    return cursor.fetchone()


def get_notion_oauth_app_public_config(cursor):
    """
    Never returns the client secret -- only whether an app is configured,
    where it came from, and (if saved in the database) a short hint plus
    the client ID, which isn't sensitive.
    """
    app_row = get_active_notion_oauth_app(cursor)

    if app_row:
        return {
            "configured": True,
            "source": "database",
            "clientId": app_row.get("client_id"),
            "clientSecretHint": app_row.get("client_secret_hint"),
            "updatedAt": (
                app_row["updated_at"].strftime("%d/%m/%Y %I:%M %p")
                if app_row.get("updated_at")
                else None
            ),
        }

    env_client_id = os.getenv("NOTION_OAUTH_CLIENT_ID", "").strip()
    env_client_secret = os.getenv("NOTION_OAUTH_CLIENT_SECRET", "").strip()

    if env_client_id and env_client_secret:
        return {
            "configured": True,
            "source": "environment",
            "clientId": env_client_id,
            "clientSecretHint": None,
            "updatedAt": None,
        }

    return {"configured": False, "source": None, "clientId": None, "clientSecretHint": None, "updatedAt": None}


def get_notion_oauth_credentials(cursor):
    """
    Resolves which Notion app to use for OAuth: a database override (set by
    a manager on the Notion Sync page) always wins over the
    NOTION_OAUTH_CLIENT_ID/SECRET env vars, which remain the fallback so
    existing deployments keep working untouched. Returns (client_id,
    client_secret), or (None, None) if neither is configured.
    """
    app_row = get_active_notion_oauth_app(cursor)

    if app_row:
        client_secret = ai_provider_service.decrypt_api_key(app_row["encrypted_client_secret"])
        return app_row.get("client_id"), client_secret

    env_client_id = os.getenv("NOTION_OAUTH_CLIENT_ID", "").strip()
    env_client_secret = os.getenv("NOTION_OAUTH_CLIENT_SECRET", "").strip()

    if env_client_id and env_client_secret:
        return env_client_id, env_client_secret

    return None, None


def save_notion_oauth_app(cursor, client_id, client_secret, actor_id):
    cursor.execute("UPDATE notion_oauth_apps SET is_active = 0 WHERE is_active = 1")

    encrypted_secret = ai_provider_service.encrypt_api_key(client_secret)
    secret_hint = ai_provider_service.mask_api_key(client_secret)

    cursor.execute("""
        INSERT INTO notion_oauth_apps
        (client_id, encrypted_client_secret, client_secret_hint, is_active, created_by, updated_by)
        VALUES (%s, %s, %s, 1, %s, %s)
    """, (client_id, encrypted_secret, secret_hint, actor_id, actor_id))

    return cursor.lastrowid


def clear_notion_oauth_app(cursor):
    cursor.execute("UPDATE notion_oauth_apps SET is_active = 0 WHERE is_active = 1")


def create_oauth_state(cursor, actor_id, ttl_seconds=600):
    import secrets as secrets_module

    state = secrets_module.token_urlsafe(32)

    cursor.execute("""
        INSERT INTO notion_oauth_states (state, created_by, expires_at)
        VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL %s SECOND))
    """, (state, actor_id, ttl_seconds))

    return state


def consume_oauth_state(cursor, state):
    """
    Validates and immediately deletes the state row (single use). Returns
    the actor_id that originated the request, or None if the state is
    missing/expired/already used -- the caller must treat that as a failed
    OAuth attempt.
    """
    if not state:
        return None

    cursor.execute("""
        SELECT created_by FROM notion_oauth_states
        WHERE state = %s AND expires_at > NOW()
        LIMIT 1
    """, (state,))
    row = cursor.fetchone()

    cursor.execute("DELETE FROM notion_oauth_states WHERE state = %s", (state,))

    if not row:
        return None

    return row.get("created_by") if isinstance(row, dict) else row[0]


def build_authorize_url(client_id, redirect_uri, state):
    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "response_type": "code",
        "owner": "user",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{NOTION_API_BASE}/oauth/authorize?{urlencode(params)}"


def exchange_oauth_code_for_token(client_id, client_secret, code, redirect_uri):
    response = requests.post(
        f"{NOTION_API_BASE}/oauth/token",
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/json", "Notion-Version": NOTION_VERSION},
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


# =========================
# NOTION ID / URL PARSING
# =========================
def extract_notion_id(raw_value):
    """
    Accepts a raw 32-char ID, a hyphenated UUID, or a full Notion URL, and
    returns the clean 32-character hex ID Notion's API expects.
    """
    raw_value = str(raw_value or "").strip()

    # Prefer the hyphenated UUID shape first (unambiguous, appears verbatim
    # in Notion URLs/IDs).
    uuid_match = re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        raw_value,
    )
    if uuid_match:
        return uuid_match.group(0).replace("-", "")

    # Otherwise look for a bare 32-hex-char ID, but only where it isn't
    # directly adjacent to another hex character -- prevents grabbing a
    # stray hex-valid letter (e.g. the "e" in "...Page-<id>") from
    # surrounding URL slug text.
    bare_match = re.search(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])", raw_value)

    if bare_match:
        return bare_match.group(0)

    return None


# =========================
# NOTION API CALLS
# =========================
def notion_request(token, method, path, json_body=None, timeout=20):
    response = requests.request(
        method,
        f"{NOTION_API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        json=json_body,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def list_notion_pages(token, source_id):
    """
    source_id may be either a database ID or a single page ID. Tries the
    database-query endpoint first; if that isn't a database, falls back to
    treating it as a single page.
    """
    try:
        results = []
        start_cursor = None

        while True:
            body = {"start_cursor": start_cursor} if start_cursor else {}
            data = notion_request(token, "POST", f"/databases/{source_id}/query", body)
            results.extend(data.get("results", []))

            if not data.get("has_more"):
                break

            start_cursor = data.get("next_cursor")

        return results
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code in (400, 404):
            # Not a database -- treat source_id as a single page instead.
            page = notion_request(token, "GET", f"/pages/{source_id}")
            return [page]
        raise


def discover_notion_content(token):
    """
    Replaces the old single-source_id model: after OAuth, the integration
    may have access to many pages/databases (whatever the admin selected on
    Notion's own consent screen). POST /v1/search with no query/filter
    returns everything currently shared with it -- top-level pages AND
    database entries alike -- so this is the one call needed to discover the
    full accessible content instead of requiring one hardcoded page/database
    ID. Database entries also returned via search need no separate
    /databases/{id}/query call; only the "container" databases themselves
    (object == "database") are excluded here since their rows already came
    back individually as object == "page" results.
    """
    results = []
    start_cursor = None

    while True:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor

        data = notion_request(token, "POST", "/search", body)
        results.extend(data.get("results", []))

        if not data.get("has_more"):
            break

        start_cursor = data.get("next_cursor")

    return [item for item in results if item.get("object") == "page"]


def extract_notion_page_title(page):
    properties = page.get("properties", {})

    for prop in properties.values():
        if prop.get("type") == "title":
            title_parts = prop.get("title", [])
            return "".join(part.get("plain_text", "") for part in title_parts).strip() or "Untitled"

    return "Untitled"


def notion_property_to_text(prop):
    prop_type = prop.get("type")

    if prop_type == "title":
        return "".join(p.get("plain_text", "") for p in prop.get("title", []))
    if prop_type == "rich_text":
        return "".join(p.get("plain_text", "") for p in prop.get("rich_text", []))
    if prop_type == "select":
        return (prop.get("select") or {}).get("name", "") or ""
    if prop_type == "status":
        return (prop.get("status") or {}).get("name", "") or ""
    if prop_type == "multi_select":
        return ", ".join(o.get("name", "") for o in prop.get("multi_select", []))
    if prop_type == "people":
        return ", ".join(p.get("name", "") for p in prop.get("people", []))
    if prop_type == "date":
        date_obj = prop.get("date") or {}
        return date_obj.get("start", "") or ""
    if prop_type == "checkbox":
        return "Yes" if prop.get("checkbox") else "No"
    if prop_type == "number":
        return str(prop.get("number")) if prop.get("number") is not None else ""
    if prop_type == "url":
        return prop.get("url", "") or ""
    if prop_type == "email":
        return prop.get("email", "") or ""

    return ""


def notion_child_database_to_html(token, database_id):
    """
    A "child_database" block is a full embedded Notion database (with its
    own rows/columns), completely different from a simple "table" block.
    Renders each row as a table row, using the first row's property names
    as column headers.
    """
    try:
        pages = list_notion_pages(token, database_id)
    except Exception as error:
        print("NOTION CHILD DATABASE FETCH ERROR:", error)
        return ""

    if not pages:
        return ""

    column_names = list(pages[0].get("properties", {}).keys())
    header_html = "".join(f"<th>{name}</th>" for name in column_names)

    row_html_parts = []
    for page in pages:
        properties = page.get("properties", {})
        cells = "".join(
            f"<td>{notion_property_to_text(properties.get(name, {}))}</td>"
            for name in column_names
        )
        row_html_parts.append(f"<tr>{cells}</tr>")

    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(row_html_parts)}</tbody></table>"


def fetch_notion_block_children(token, block_id):
    results = []
    start_cursor = None

    while True:
        path = f"/blocks/{block_id}/children?page_size=100"

        if start_cursor:
            path += f"&start_cursor={start_cursor}"

        data = notion_request(token, "GET", path)
        results.extend(data.get("results", []))

        if not data.get("has_more"):
            break

        start_cursor = data.get("next_cursor")

    return results


# =========================
# BLOCK -> HTML CONVERSION
# =========================
def notion_rich_text_to_html(rich_text_array):
    html_parts = []

    for span in rich_text_array or []:
        text = span.get("plain_text", "")
        text = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        annotations = span.get("annotations", {})

        if annotations.get("code"):
            text = f"<code>{text}</code>"
        if annotations.get("bold"):
            text = f"<strong>{text}</strong>"
        if annotations.get("italic"):
            text = f"<em>{text}</em>"
        if annotations.get("underline"):
            text = f"<u>{text}</u>"
        if annotations.get("strikethrough"):
            text = f"<s>{text}</s>"

        link = span.get("href")
        if link:
            # Links to another page *within the same Notion workspace*
            # (mentions) come back as a bare relative path like
            # "/21ca360a...", which is meaningless outside Notion's own
            # app -- turn it into a real, clickable Notion URL instead.
            if link.startswith("/"):
                link = f"https://www.notion.so{link}"
            text = f'<a href="{link}" target="_blank" rel="noopener noreferrer">{text}</a>'

        html_parts.append(text)

    return "".join(html_parts)


def download_and_host_notion_file(url, upload_folder):
    """
    Downloads a Notion-hosted file (images expire after ~1 hour on Notion's
    side) and re-hosts it in this app's own upload folder, using the exact
    same naming/URL convention as manually uploaded article attachments so
    it behaves identically everywhere else in the system (permanent-delete
    cleanup, AI Chat/quiz image extraction, etc.).
    """
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        extension = "png"
        content_type = response.headers.get("Content-Type", "")

        if "jpeg" in content_type or "jpg" in content_type:
            extension = "jpg"
        elif "gif" in content_type:
            extension = "gif"
        elif "pdf" in content_type:
            extension = "pdf"
        elif "png" in content_type:
            extension = "png"

        unique_filename = f"{int(time.time() * 1000)}_notion_import.{extension}"
        file_path = upload_folder / unique_filename

        with open(file_path, "wb") as f:
            f.write(response.content)

        return f"{get_public_base_url()}/static/uploads/articles/{unique_filename}"
    except Exception as error:
        print("NOTION FILE DOWNLOAD ERROR:", error)
        return None


def notion_blocks_to_html(token, blocks, upload_folder, depth=0):
    html_parts = []
    list_buffer = []
    list_type = None

    def flush_list():
        nonlocal list_buffer, list_type
        if list_buffer:
            tag = "ul" if list_type == "bulleted" else "ol"
            html_parts.append(f"<{tag}>" + "".join(list_buffer) + f"</{tag}>")
        list_buffer = []
        list_type = None

    for block in blocks:
        block_type = block.get("type")
        data = block.get(block_type, {}) if block_type else {}

        try:
            if block_type in ("bulleted_list_item", "numbered_list_item"):
                current_type = "bulleted" if block_type == "bulleted_list_item" else "numbered"

                if list_type and list_type != current_type:
                    flush_list()

                list_type = current_type
                item_html = notion_rich_text_to_html(data.get("rich_text"))

                if block.get("has_children") and depth < 3:
                    children = fetch_notion_block_children(token, block["id"])
                    item_html += notion_blocks_to_html(token, children, upload_folder, depth + 1)

                list_buffer.append(f"<li>{item_html}</li>")
                continue

            flush_list()

            if block_type == "paragraph":
                text = notion_rich_text_to_html(data.get("rich_text"))
                if text.strip():
                    html_parts.append(f"<p>{text}</p>")

            elif block_type in ("heading_1", "heading_2", "heading_3"):
                tag = {"heading_1": "h1", "heading_2": "h2", "heading_3": "h3"}[block_type]
                html_parts.append(f"<{tag}>{notion_rich_text_to_html(data.get('rich_text'))}</{tag}>")

            elif block_type == "to_do":
                checked = "checked" if data.get("checked") else ""
                text = notion_rich_text_to_html(data.get("rich_text"))
                html_parts.append(
                    f'<p><input type="checkbox" disabled {checked}> {text}</p>'
                )

            elif block_type == "quote":
                html_parts.append(f"<blockquote>{notion_rich_text_to_html(data.get('rich_text'))}</blockquote>")

            elif block_type == "divider":
                html_parts.append("<hr>")

            elif block_type == "code":
                text = notion_rich_text_to_html(data.get("rich_text"))
                html_parts.append(f"<pre><code>{text}</code></pre>")

            elif block_type == "image":
                image_url = (
                    data.get("file", {}).get("url")
                    or data.get("external", {}).get("url")
                )
                if image_url:
                    hosted_url = download_and_host_notion_file(image_url, upload_folder)
                    if hosted_url:
                        html_parts.append(f'<p><img src="{hosted_url}" width="300"></p>')

            elif block_type == "file" or block_type == "pdf":
                file_url = (
                    data.get("file", {}).get("url")
                    or data.get("external", {}).get("url")
                )
                if file_url:
                    hosted_url = download_and_host_notion_file(file_url, upload_folder)
                    if hosted_url:
                        html_parts.append(
                            f'<p><a href="{hosted_url}" target="_blank" rel="noopener noreferrer">Attached file</a></p>'
                        )

            elif block_type == "table":
                if block.get("has_children"):
                    rows = fetch_notion_block_children(token, block["id"])
                    row_html = []
                    for row in rows:
                        cells = row.get("table_row", {}).get("cells", [])
                        cell_html = "".join(
                            f"<td>{notion_rich_text_to_html(cell)}</td>" for cell in cells
                        )
                        row_html.append(f"<tr>{cell_html}</tr>")
                    html_parts.append(f"<table>{''.join(row_html)}</table>")

            elif block_type == "child_database":
                title = data.get("title") or "Database"
                table_html = notion_child_database_to_html(token, block["id"])
                if table_html:
                    html_parts.append(f"<h3>{title}</h3>{table_html}")

            elif block_type in ("video", "embed", "bookmark", "link_preview"):
                # These blocks are how a pasted YouTube/Vimeo/Google Drive/
                # website link shows up in Notion. The frontend strips
                # <iframe> tags for security, so we can't embed a player --
                # render a plain clickable link instead, same as file/pdf.
                link_url = (
                    data.get("url")
                    or data.get("external", {}).get("url")
                    or data.get("file", {}).get("url")
                )
                caption = notion_rich_text_to_html(data.get("caption"))
                if link_url:
                    label = caption.strip() if caption and caption.strip() else link_url
                    html_parts.append(
                        f'<p><a href="{link_url}" target="_blank" rel="noopener noreferrer">{label}</a></p>'
                    )

            else:
                # Unsupported block type -- degrade gracefully instead of
                # failing the whole import. Grab whatever plain text is
                # available so nothing is silently lost.
                rich_text = data.get("rich_text")
                if rich_text:
                    html_parts.append(f"<p>{notion_rich_text_to_html(rich_text)}</p>")

        except Exception as error:
            print("NOTION BLOCK CONVERT ERROR:", block_type, error)
            continue

    flush_list()

    return "".join(html_parts)


# =========================
# SYNC ORCHESTRATION
# =========================
def _normalize_notion_edited_time(last_edited_time):
    # MySQL's DATETIME column drops fractional seconds, but Notion's
    # last_edited_time always includes them (e.g. "...T00:00:00.000Z") --
    # normalize both sides to whole-second precision before comparing, or a
    # real unchanged page would always look "changed".
    return re.sub(r"\.\d+", "", last_edited_time).replace("T", " ").replace("Z", "")


def check_for_notion_updates(token, actor_id, upload_folder):
    """
    Discovers everything currently shared with the connected integration
    (discover_notion_content) and, per page:
      - not yet imported -> stage it as a pending "new" entry
        (article_id NULL) for a manager to approve before it reaches the
        Knowledge Base, unless this exact edited-time is already sitting
        pending/resolved for this page (avoids re-flagging on every click).
      - already imported and Notion's last_edited_time changed, with no
        existing pending/dismissed notion_pending_updates row already
        covering this exact edited-time -> stage the new content as a
        pending update instead of overwriting the live article.
      - unchanged -> skip.

    Both cases are reported in flagged_items so the caller (the /check
    route) can notify the admin(s). Nothing ever reaches wiki_article
    without going through the Pending Updates review queue first -- see
    apply_pending_update, which creates the article for a "new" entry or
    updates the existing one for an edit. This function intentionally does
    not call into app.py's create_notification_safe() itself, to avoid a
    circular import between this service module and app.py.
    """
    conn = None
    cursor = None

    new_count = 0
    flagged_count = 0
    unchanged_count = 0
    failed_count = 0
    error_message = None
    flagged_items = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        ensure_notion_sync_tables(cursor)

        pages = discover_notion_content(token)

        for page in pages:
            page_id = page.get("id")
            last_edited_time = page.get("last_edited_time")

            try:
                cursor.execute("""
                    SELECT article_id, title, content, notion_last_edited_time
                    FROM wiki_article
                    WHERE notion_page_id = %s
                    LIMIT 1
                """, (page_id,))
                existing = cursor.fetchone()

                edited_time_mysql = _normalize_notion_edited_time(last_edited_time)

                existing_edited = (
                    existing["notion_last_edited_time"].strftime("%Y-%m-%d %H:%M:%S")
                    if existing and existing.get("notion_last_edited_time")
                    else None
                )

                if existing and existing_edited == edited_time_mysql:
                    unchanged_count += 1
                    continue

                if existing:
                    # Already imported, Notion side changed. Don't overwrite
                    # yet -- only stage it if this exact edited-time isn't
                    # already sitting as a pending or previously-dismissed
                    # proposal (avoids re-flagging the same change on every
                    # click of "Check for Updates").
                    cursor.execute("""
                        SELECT id FROM notion_pending_updates
                        WHERE notion_page_id = %s AND notion_last_edited_time = %s
                        LIMIT 1
                    """, (page_id, edited_time_mysql))
                    already_staged = cursor.fetchone()

                    if already_staged:
                        unchanged_count += 1
                        continue

                    title = extract_notion_page_title(page)
                    blocks = fetch_notion_block_children(token, page_id)
                    content_html = notion_blocks_to_html(token, blocks, upload_folder)

                    if not content_html.strip():
                        content_html = "<p>(No readable content found in this Notion page.)</p>"

                    cursor.execute("""
                        INSERT INTO notion_pending_updates
                        (article_id, notion_page_id, proposed_title, proposed_content,
                         previous_title, previous_content, notion_last_edited_time, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
                    """, (
                        existing["article_id"], page_id, title, content_html,
                        existing.get("title"), existing.get("content"),
                        edited_time_mysql,
                    ))
                    pending_id = cursor.lastrowid

                    flagged_count += 1
                    flagged_items.append({
                        "kind": "update",
                        "article_id": existing["article_id"],
                        "title": title,
                        "pending_id": pending_id,
                    })
                else:
                    # Brand-new page, never imported. Same dedupe as the
                    # edit branch above -- don't create a second pending
                    # entry for a page already sitting pending/resolved at
                    # this exact edited-time.
                    cursor.execute("""
                        SELECT id FROM notion_pending_updates
                        WHERE article_id IS NULL AND notion_page_id = %s AND notion_last_edited_time = %s
                        LIMIT 1
                    """, (page_id, edited_time_mysql))
                    already_staged = cursor.fetchone()

                    if already_staged:
                        unchanged_count += 1
                        continue

                    title = extract_notion_page_title(page)
                    blocks = fetch_notion_block_children(token, page_id)
                    content_html = notion_blocks_to_html(token, blocks, upload_folder)

                    if not content_html.strip():
                        content_html = "<p>(No readable content found in this Notion page.)</p>"

                    cursor.execute("""
                        INSERT INTO notion_pending_updates
                        (article_id, notion_page_id, proposed_title, proposed_content,
                         previous_title, previous_content, notion_last_edited_time, status)
                        VALUES (NULL, %s, %s, %s, NULL, NULL, %s, 'pending')
                    """, (page_id, title, content_html, edited_time_mysql))
                    pending_id = cursor.lastrowid

                    new_count += 1
                    flagged_items.append({
                        "kind": "new",
                        "article_id": None,
                        "title": title,
                        "pending_id": pending_id,
                    })

                conn.commit()
            except Exception as page_error:
                conn.rollback()
                failed_count += 1
                print("NOTION PAGE CHECK ERROR:", page_id, page_error)
                continue

        status = "completed"
    except Exception as error:
        status = "failed"
        error_message = str(error)
        print("NOTION CHECK ERROR:", error)
    finally:
        if cursor:
            try:
                cursor.execute("""
                    INSERT INTO notion_sync_jobs
                    (status, imported_count, updated_count, skipped_count, failed_count, error_message, completed_at, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                """, (status, new_count, flagged_count, unchanged_count, failed_count, error_message, actor_id))
                conn.commit()
            except Exception:
                pass

            cursor.close()
        if conn:
            conn.close()

    return {
        "status": status,
        "new": new_count,
        "flagged": flagged_count,
        "unchanged": unchanged_count,
        "failed": failed_count,
        "errorMessage": error_message,
        "flaggedItems": flagged_items,
    }


def list_pending_updates(cursor):
    # Includes the full proposed/previous content -- the Notion Sync page's
    # "Review Changes" compare view renders these directly from this list
    # rather than fetching each item individually.
    cursor.execute("""
        SELECT id, article_id, notion_page_id, proposed_title, proposed_content,
               previous_title, previous_content, notion_last_edited_time, detected_at
        FROM notion_pending_updates
        WHERE status = 'pending'
        ORDER BY detected_at DESC
    """)
    return cursor.fetchall() or []


def get_pending_update(cursor, pending_id):
    cursor.execute("""
        SELECT * FROM notion_pending_updates WHERE id = %s LIMIT 1
    """, (pending_id,))
    return cursor.fetchone()


def apply_pending_update(cursor, pending_id, actor_id):
    """
    Returns the resulting article_id on success (the existing one for an
    edit, or the newly-created one for a "new" entry), or None if the
    update was already resolved by someone else.
    """
    pending = get_pending_update(cursor, pending_id)

    if not pending or pending.get("status") != "pending":
        return None

    if pending.get("article_id") is None:
        # Brand-new page approved for the first time -- create it now,
        # same shape as the old direct-import insert used to.
        cursor.execute("""
            INSERT INTO wiki_article
            (title, content, category, sub_category, link, is_deleted, source_type, notion_page_id, notion_last_edited_time)
            VALUES (%s, %s, %s, %s, %s, FALSE, 'notion', %s, %s)
        """, (
            pending["proposed_title"], pending["proposed_content"], "Notion", "", "",
            pending["notion_page_id"], pending["notion_last_edited_time"],
        ))
        article_id = cursor.lastrowid
    else:
        article_id = pending["article_id"]
        cursor.execute("""
            UPDATE wiki_article
            SET title = %s, content = %s, notion_last_edited_time = %s
            WHERE article_id = %s
        """, (
            pending["proposed_title"], pending["proposed_content"],
            pending["notion_last_edited_time"], article_id,
        ))

    cursor.execute("""
        UPDATE notion_pending_updates
        SET status = 'applied', resolved_by = %s, resolved_at = NOW()
        WHERE id = %s AND status = 'pending'
    """, (actor_id, pending_id))

    if cursor.rowcount <= 0:
        return None

    return article_id


def dismiss_pending_update(cursor, pending_id, actor_id):
    cursor.execute("""
        UPDATE notion_pending_updates
        SET status = 'dismissed', resolved_by = %s, resolved_at = NOW()
        WHERE id = %s AND status = 'pending'
    """, (actor_id, pending_id))

    return cursor.rowcount > 0
