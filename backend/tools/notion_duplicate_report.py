"""Read-only duplicate report for Notion-synced articles (a dry run).

Lists what is already duplicated in the database and what references each
copy. It NEVER changes anything: every statement must be a SELECT/SHOW (the
script refuses otherwise) and the session is opened read-only. Any fix it
suggests is only printed for a person to review and run.

It connects with the same MYSQL_HOST / MYSQL_PORT / MYSQL_USER /
MYSQL_PASSWORD / MYSQL_DATABASE variables the backend uses, so run it where
those point at the database you want to inspect (e.g. `railway run python
backend/tools/notion_duplicate_report.py`). It prints no credentials.

    python backend/tools/notion_duplicate_report.py
    python backend/tools/notion_duplicate_report.py --json report.json
"""

import argparse
import json
import os
import re
import sys

import mysql.connector

_READ_ONLY_SQL = re.compile(r"^\s*(SELECT|SHOW)\b", re.IGNORECASE)
_UPLOAD_FILE = re.compile(r"/static/uploads/articles/([^\s\"'?<>)]+)")
# Columns that point at an article by id. Anything matching is checked, so a
# table added later is still covered; the foreign keys below are added too.
_ARTICLE_ID_COLUMN = re.compile(r"article.*id$|^article_id$", re.IGNORECASE)


def connect():
    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
        charset="utf8mb4",
    )
    setup = conn.cursor()
    setup.execute("SET SESSION TRANSACTION READ ONLY")
    setup.close()
    return conn


class ReadOnly:
    def __init__(self, conn):
        self.cursor = conn.cursor(dictionary=True)

    def rows(self, sql, params=()):
        if not _READ_ONLY_SQL.match(sql):
            raise RuntimeError("This report is read-only; refusing to run: " + sql.strip()[:40])
        self.cursor.execute(sql, params)
        return self.cursor.fetchall() or []

    def one(self, sql, params=()):
        found = self.rows(sql, params)
        return found[0] if found else None


def in_clause(values):
    return ", ".join(["%s"] * len(values))


def table_exists(db, name):
    return bool(db.one(
        "SELECT 1 AS x FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
        (name,),
    ))


def columns_of(db, table):
    return {
        row["COLUMN_NAME"]
        for row in db.rows(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
            (table,),
        )
    }


def referencing_columns(db):
    """(table, column) pairs that hold a wiki_article id, from names and real foreign keys."""
    found = set()
    for row in db.rows("""
        SELECT TABLE_NAME, COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME <> 'wiki_article'
    """):
        if _ARTICLE_ID_COLUMN.search(row["COLUMN_NAME"]):
            found.add((row["TABLE_NAME"], row["COLUMN_NAME"]))
    for row in db.rows("""
        SELECT TABLE_NAME, COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME = 'wiki_article'
    """):
        found.add((row["TABLE_NAME"], row["COLUMN_NAME"]))
    return sorted(found)


def article_summary(db, ids, has_notion):
    cols = ["article_id", "title", "category", "is_deleted", "LENGTH(content) AS content_chars"]
    if has_notion["source_type"]:
        cols.append("source_type")
    if has_notion["notion_last_edited_time"]:
        cols.append("notion_last_edited_time")
    if has_notion["notion_page_id"]:
        cols.append("notion_page_id")
    return {
        row["article_id"]: row
        for row in db.rows(
            f"SELECT {', '.join(cols)} FROM wiki_article WHERE article_id IN ({in_clause(ids)})", tuple(ids)
        )
    }


def count_references(db, ids, ref_columns):
    """{article_id: {"table.column": rows}} for every referencing column."""
    result = {article_id: {} for article_id in ids}
    for table, column in ref_columns:
        for row in db.rows(
            f"SELECT `{column}` AS article_id, COUNT(*) AS n FROM `{table}` "
            f"WHERE `{column}` IN ({in_clause(ids)}) GROUP BY `{column}`",
            tuple(ids),
        ):
            result[row["article_id"]][f"{table}.{column}"] = row["n"]

    # image_retrieval keys knowledge-base images by (source_type, source_id).
    if table_exists(db, "image_retrieval") and {"source_type", "source_id"} <= columns_of(db, "image_retrieval"):
        for row in db.rows(
            f"SELECT source_id AS article_id, COUNT(*) AS n FROM image_retrieval "
            f"WHERE source_type = 'knowledge_base' AND source_id IN ({in_clause(ids)}) GROUP BY source_id",
            tuple(ids),
        ):
            result[row["article_id"]]["image_retrieval(knowledge_base).source_id"] = row["n"]
    return result


def uploaded_files(db, ids):
    files = {article_id: set() for article_id in ids}
    for row in db.rows(
        f"SELECT article_id, attachment_url, image_files, content FROM wiki_article "
        f"WHERE article_id IN ({in_clause(ids)})",
        tuple(ids),
    ):
        text = " ".join(str(row.get(key) or "") for key in ("attachment_url", "image_files", "content"))
        files[row["article_id"]] = set(_UPLOAD_FILE.findall(text))
    return files


def describe_group(db, ids, has_notion, ref_columns):
    summary = article_summary(db, ids, has_notion)
    refs = count_references(db, ids, ref_columns)
    files = uploaded_files(db, ids)
    items = []
    for article_id in sorted(ids):
        row = summary.get(article_id, {})
        items.append({
            "article_id": article_id,
            "title": row.get("title"),
            "category": row.get("category"),
            "in_retrieve_bin": bool(row.get("is_deleted")),
            "content_chars": row.get("content_chars"),
            "notion_last_edited_time": str(row.get("notion_last_edited_time") or ""),
            "references": refs.get(article_id, {}),
            "reference_total": sum(refs.get(article_id, {}).values()),
            "uploaded_files": len(files.get(article_id, ())),
        })
    # Suggestion only: prefer a copy staff can see (not in the Retrieve Bin),
    # then the one other records point at, then the oldest.
    keeper = sorted(
        items,
        key=lambda item: (item["in_retrieve_bin"], -item["reference_total"], item["article_id"]),
    )[0]
    return items, keeper["article_id"]


def build_report(db):
    report = {"notes": [], "duplicate_articles": [], "missing_page_id": [], "duplicate_open_review_items": [],
              "stale_new_review_items": []}

    if not table_exists(db, "wiki_article"):
        report["notes"].append("wiki_article does not exist in this database.")
        return report

    article_columns = columns_of(db, "wiki_article")
    has_notion = {
        name: name in article_columns
        for name in ("source_type", "notion_page_id", "notion_last_edited_time")
    }
    report["schema"] = dict(has_notion)

    unique_index = db.one("""
        SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wiki_article'
          AND COLUMN_NAME = 'notion_page_id' AND NON_UNIQUE = 0
    """)["c"] if has_notion["notion_page_id"] else 0
    report["schema"]["notion_page_id_unique_index"] = bool(unique_index)

    if not has_notion["notion_page_id"]:
        report["notes"].append("No notion_page_id column yet: Notion Sync has never run on this database.")
        return report

    ref_columns = referencing_columns(db)
    report["referencing_columns"] = [f"{table}.{column}" for table, column in ref_columns]

    # 1. Several articles for one Notion page (possible only without the unique index).
    for group in db.rows("""
        SELECT notion_page_id, COUNT(*) AS copies FROM wiki_article
        WHERE notion_page_id IS NOT NULL GROUP BY notion_page_id HAVING COUNT(*) > 1
    """):
        ids = [row["article_id"] for row in db.rows(
            "SELECT article_id FROM wiki_article WHERE notion_page_id = %s", (group["notion_page_id"],))]
        items, keeper = describe_group(db, ids, has_notion, ref_columns)
        report["duplicate_articles"].append(
            {"notion_page_id": group["notion_page_id"], "articles": items, "suggested_keeper": keeper})

    # 2. Notion articles that were never given a page id (cannot be matched by the sync).
    if has_notion["source_type"] and table_exists(db, "notion_pending_updates"):
        for article in db.rows("""
            SELECT article_id, title FROM wiki_article
            WHERE source_type = 'notion' AND notion_page_id IS NULL
        """):
            same_title = db.rows(
                "SELECT article_id FROM wiki_article WHERE source_type = 'notion' AND notion_page_id IS NULL "
                "AND title = %s", (article["title"],))
            pages = {row["notion_page_id"] for row in db.rows(
                "SELECT DISTINCT notion_page_id FROM notion_pending_updates WHERE proposed_title = %s",
                (article["title"],))}
            entry = {"article_id": article["article_id"], "title": article["title"],
                     "candidate_page_ids": sorted(pages)}
            if len(same_title) == 1 and len(pages) == 1:
                page_id = next(iter(pages))
                taken = db.one("SELECT article_id FROM wiki_article WHERE notion_page_id = %s", (page_id,))
                if taken:
                    entry["verdict"] = f"conflict: article {taken['article_id']} already holds this page id " \
                                       "(this article is a duplicate of it)"
                else:
                    entry["verdict"] = "confident match (exact title, exactly one page, exactly one article)"
                    entry["proposed_sql"] = (
                        f"UPDATE wiki_article SET notion_page_id = '{page_id}' "
                        f"WHERE article_id = {article['article_id']} AND notion_page_id IS NULL;")
            else:
                entry["verdict"] = "ambiguous - NOT guessed; link it by hand or leave it"
            report["missing_page_id"].append(entry)

    # 3. Review-queue rows that would later try to publish the same page again.
    if table_exists(db, "notion_pending_updates"):
        for row in db.rows("""
            SELECT notion_page_id, article_id, COUNT(*) AS items, GROUP_CONCAT(id ORDER BY id) AS ids
            FROM notion_pending_updates WHERE status = 'pending'
            GROUP BY notion_page_id, article_id HAVING COUNT(*) > 1
        """):
            report["duplicate_open_review_items"].append(
                {"notion_page_id": row["notion_page_id"], "article_id": row["article_id"],
                 "pending_ids": row["ids"]})
        for row in db.rows("""
            SELECT p.id, p.notion_page_id, a.article_id AS existing_article_id
            FROM notion_pending_updates p
            JOIN wiki_article a ON a.notion_page_id = p.notion_page_id
            WHERE p.status = 'pending' AND p.article_id IS NULL
        """):
            report["stale_new_review_items"].append(
                {"pending_id": row["id"], "notion_page_id": row["notion_page_id"],
                 "existing_article_id": row["existing_article_id"]})
    return report


def print_report(report):
    print("NOTION DUPLICATE REPORT  (read-only dry run - nothing was changed)")
    print("=" * 66)
    for note in report["notes"]:
        print("NOTE:", note)
    schema = report.get("schema")
    if schema:
        print("\nSchema:", ", ".join(f"{k}={'yes' if v else 'NO'}" for k, v in schema.items()))
        if not schema.get("notion_page_id_unique_index"):
            print("  -> wiki_article.notion_page_id has no UNIQUE index, so duplicates are possible.")
            print("     Handle the duplicates below, then the app adds the index itself on its next Notion request.")

    groups = report["duplicate_articles"]
    print(f"\n1) Pages with more than one article: {len(groups)}")
    for group in groups:
        print(f"\n  Notion page {group['notion_page_id']}  -> suggested keeper: article {group['suggested_keeper']}")
        for item in group["articles"]:
            marker = "KEEP?" if item["article_id"] == group["suggested_keeper"] else "dup  "
            refs = ", ".join(f"{k}={v}" for k, v in item["references"].items()) or "none"
            print(f"   [{marker}] #{item['article_id']} \"{item['title']}\" cat={item['category']} "
                  f"bin={'yes' if item['in_retrieve_bin'] else 'no'} chars={item['content_chars']} "
                  f"notion_edit={item['notion_last_edited_time'] or '-'} files={item['uploaded_files']}")
            print(f"           referenced by: {refs}")

    missing = report["missing_page_id"]
    print(f"\n2) Notion articles with no notion_page_id (the sync cannot recognise them): {len(missing)}")
    for item in missing:
        print(f"   #{item['article_id']} \"{item['title']}\" -> {item['verdict']}")
        if item.get("proposed_sql"):
            print(f"       proposed (NOT run): {item['proposed_sql']}")

    dup_open = report["duplicate_open_review_items"]
    print(f"\n3) Pages queued more than once in Pending review: {len(dup_open)}")
    for item in dup_open:
        kind = "new page" if item["article_id"] is None else f"edit of article {item['article_id']}"
        print(f"   page {item['notion_page_id']} ({kind}): pending items {item['pending_ids']}")

    stale = report["stale_new_review_items"]
    print(f"\n4) 'New page' items whose page already has an article: {len(stale)}")
    for item in stale:
        print(f"   pending #{item['pending_id']} -> page already published as article {item['existing_article_id']}")

    print("\nReferenced columns checked:", ", ".join(report.get("referencing_columns", [])) or "(none)")
    print("""
RECOMMENDATION
 - Do not delete anything yet. For each group in (1), keep the copy marked KEEP?
   unless a manager edited another copy - the sync overwrites an article only
   from Notion, so keep the one people actually maintain.
 - Before removing a copy, move its references (columns listed above, e.g.
   quiz.source_article_id) to the kept article, then move the copy to the
   Retrieve Bin first, and delete permanently only after a few days.
 - Items in (3)/(4) are harmless now (approving them updates the one article),
   but can be moved to Trash from Notion Sync > Pending to tidy the list.
 - Once (1) is empty the unique index is added automatically.""")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", help="also write the report to this JSON file")
    args = parser.parse_args()

    missing = [name for name in ("MYSQL_HOST", "MYSQL_USER", "MYSQL_DATABASE") if not os.getenv(name)]
    if missing:
        sys.exit("Missing environment variables: " + ", ".join(missing))

    conn = connect()
    try:
        report = build_report(ReadOnly(conn))
    finally:
        conn.close()

    print_report(report)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, default=str, ensure_ascii=False)
        print("\nJSON written to", args.json)


if __name__ == "__main__":
    main()
