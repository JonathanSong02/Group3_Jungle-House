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
    config = get_active_notion_config(cursor)

    if not config:
        return None

    return {
        "sourceId": config.get("source_id"),
        "sourceName": config.get("source_name"),
        "tokenHint": ai_provider_service.mask_api_key(
            ai_provider_service.decrypt_api_key(config["encrypted_notion_token"])
        ),
        "updatedAt": (
            config["updated_at"].strftime("%d/%m/%Y %I:%M %p")
            if config.get("updated_at")
            else None
        ),
    }


def save_notion_config(cursor, raw_token, source_id, source_name, actor_id):
    cursor.execute("UPDATE notion_sync_configs SET is_active = 0 WHERE is_active = 1")

    encrypted_token = ai_provider_service.encrypt_api_key(raw_token)

    cursor.execute("""
        INSERT INTO notion_sync_configs
        (encrypted_notion_token, source_id, source_name, is_active, created_by, updated_by)
        VALUES (%s, %s, %s, 1, %s, %s)
    """, (encrypted_token, source_id, source_name, actor_id, actor_id))

    return cursor.lastrowid


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
def sync_notion_source(token, source_id, actor_id, upload_folder):
    conn = None
    cursor = None

    imported_count = 0
    updated_count = 0
    skipped_count = 0
    failed_count = 0
    error_message = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        ensure_notion_sync_tables(cursor)

        pages = list_notion_pages(token, source_id)

        for page in pages:
            page_id = page.get("id")
            last_edited_time = page.get("last_edited_time")

            try:
                cursor.execute("""
                    SELECT article_id, notion_last_edited_time
                    FROM wiki_article
                    WHERE notion_page_id = %s
                    LIMIT 1
                """, (page_id,))
                existing = cursor.fetchone()

                # MySQL's DATETIME column drops fractional seconds, but
                # Notion's last_edited_time always includes them (e.g.
                # "...T00:00:00.000Z") -- normalize both sides to
                # whole-second precision before comparing, or a real
                # unchanged page would always look "changed".
                edited_time_mysql = re.sub(r"\.\d+", "", last_edited_time).replace("T", " ").replace("Z", "")

                existing_edited = (
                    existing["notion_last_edited_time"].strftime("%Y-%m-%d %H:%M:%S")
                    if existing and existing.get("notion_last_edited_time")
                    else None
                )

                if existing and existing_edited == edited_time_mysql:
                    skipped_count += 1
                    continue

                title = extract_notion_page_title(page)
                blocks = fetch_notion_block_children(token, page_id)
                content_html = notion_blocks_to_html(token, blocks, upload_folder)

                if not content_html.strip():
                    content_html = "<p>(No readable content found in this Notion page.)</p>"

                if existing:
                    cursor.execute("""
                        UPDATE wiki_article
                        SET title = %s,
                            content = %s,
                            notion_last_edited_time = %s
                        WHERE article_id = %s
                    """, (title, content_html, edited_time_mysql, existing["article_id"]))
                    updated_count += 1
                else:
                    cursor.execute("""
                        INSERT INTO wiki_article
                        (title, content, category, sub_category, link, is_deleted, source_type, notion_page_id, notion_last_edited_time)
                        VALUES (%s, %s, %s, %s, %s, FALSE, 'notion', %s, %s)
                    """, (title, content_html, "Notion", "", "", page_id, edited_time_mysql))
                    imported_count += 1

                conn.commit()
            except Exception as page_error:
                conn.rollback()
                failed_count += 1
                print("NOTION PAGE IMPORT ERROR:", page_id, page_error)
                continue

        status = "completed"
    except Exception as error:
        status = "failed"
        error_message = str(error)
        print("NOTION SYNC ERROR:", error)
    finally:
        if cursor:
            try:
                cursor.execute("""
                    INSERT INTO notion_sync_jobs
                    (status, imported_count, updated_count, skipped_count, failed_count, error_message, completed_at, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                """, (status, imported_count, updated_count, skipped_count, failed_count, error_message, actor_id))
                conn.commit()
            except Exception:
                pass

            cursor.close()
        if conn:
            conn.close()

    return {
        "status": status,
        "imported": imported_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "errorMessage": error_message,
    }
