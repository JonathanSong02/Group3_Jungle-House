"""One-off cleanup of old duplicate / stale Pending Notion items.

The duplicate-sync bug is already fixed (sync lock, one Pending item per page,
idempotent approve). This only tidies items that were queued BEFORE the fix, in
notion_pending_updates. It never touches articles, quizzes, links or images.

Rules, for items whose status is 'pending' only:

  A. One Pending item per page. Keep the one with the newest
     notion_last_edited_time (tie: highest id); move the others to Trash.
  B. If the page already has an article and the kept item is NOT newer than the
     article's notion_last_edited_time, it is stale: move it to Trash. A newer
     one is a real Notion change and is left for a manager to review.
  C. Anything uncertain (no usable edit time, an article with no edit time, an
     ambiguous page/article link) is left untouched and listed for manual review.

"Move to Trash" is the app's own mechanism (notion_sync_service.trash_pending_update),
so items appear in Notion Sync > Pending > Trash and can be restored there.
Nothing is deleted, and no image or attachment file is touched.

DRY RUN IS THE DEFAULT: it changes nothing (the session is read-only), prints the
plan, and writes it to a CSV. Add --apply to make the change. --apply first takes
the same MySQL lock the Notion sync uses and stops if a sync is running, applies
everything in ONE transaction (all or nothing), and writes an undo log. Running
it again changes 0 items.

It reads the same MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD /
MYSQL_DATABASE variables as the backend and prints no credentials.

    python backend/tools/notion_pending_cleanup.py                 # dry run
    python backend/tools/notion_pending_cleanup.py --apply         # do it
    python backend/tools/notion_pending_cleanup.py --undo FILE     # preview undo
    python backend/tools/notion_pending_cleanup.py --undo FILE --apply
"""

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import mysql.connector

TOOLS_DIR = Path(__file__).resolve().parent
SRC_DIR = TOOLS_DIR.parent / "src"
OUTPUT_DIR = TOOLS_DIR / "cleanup_output"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from notion_duplicate_report import ReadOnly, in_clause  # noqa: E402  (the report's read-only SQL guard)

PLAN_COLUMNS = [
    "item_id", "page_id", "title", "kind", "item_edited", "article_id", "article_edited",
    "action", "rule", "reason",
]
UNDO_COLUMNS = ["item_id", "previous_status", "new_status", "notion_page_id", "rule", "reason", "applied_at_utc"]


# --------------------------------------------------------------------------
# Planning (pure: no database access)
# --------------------------------------------------------------------------
@dataclass
class Decision:
    item_id: int
    page_id: str
    title: str
    kind: str
    item_time: object
    article_id: object
    article_time: object
    action: str   # KEEP | TRASH | MANUAL
    rule: str     # A | B | C | -
    reason: str


def _is_time(value):
    return isinstance(value, datetime)


def _clean_title(title):
    text = " ".join(str(title or "").split())
    return text if len(text) <= 60 else text[:57] + "..."


def _kind(item):
    return "new page" if item["article_id"] is None else f"edit of article {item['article_id']}"


def _article_for_page(page_id, group, articles_by_page, articles_by_id):
    """(article, None) when the page/article relation is clear, else (None, why-not)."""
    on_page = articles_by_page.get(page_id, [])
    if len(on_page) > 1:
        return None, f"{len(on_page)} articles share this page id"
    page_article = on_page[0] if on_page else None

    linked_ids = {item["article_id"] for item in group if item["article_id"] is not None}
    if len(linked_ids) > 1:
        return None, "the items point at different articles"
    if not linked_ids:
        return page_article, None

    linked_id = next(iter(linked_ids))
    linked = articles_by_id.get(linked_id)
    if linked is None:
        return None, f"linked article {linked_id} no longer exists"
    if page_article is not None and page_article["article_id"] != linked_id:
        return None, f"items are linked to article {linked_id} but the page belongs to article {page_article['article_id']}"
    if page_article is None and linked["notion_page_id"] not in (None, page_id):
        return None, f"linked article {linked_id} belongs to a different Notion page"
    return linked, None


def _decide_page(page_id, group, article, problem):
    article_id = article["article_id"] if article else None
    article_time = article["notion_last_edited_time"] if article else None

    def decide(item, action, rule, reason):
        return Decision(
            item["id"], page_id, _clean_title(item.get("proposed_title")), _kind(item),
            item["notion_last_edited_time"], article_id, article_time, action, rule, reason,
        )

    if problem:
        return [decide(item, "MANUAL", "C", problem) for item in group]

    decisions = []
    comparable = []
    for item in group:
        if _is_time(item["notion_last_edited_time"]):
            comparable.append(item)
        else:
            decisions.append(decide(item, "MANUAL", "C", "no usable notion_last_edited_time - cannot compare"))

    if comparable:
        keeper = max(comparable, key=lambda item: (item["notion_last_edited_time"], item["id"]))
        for item in comparable:
            if item is keeper:
                continue
            if item["notion_last_edited_time"] == keeper["notion_last_edited_time"]:
                why = f"same edit time as #{keeper['id']}, which has the higher id"
            else:
                why = f"older duplicate - #{keeper['id']} is the newest for this page"
            decisions.append(decide(item, "TRASH", "A", why))

        keeper_time = keeper["notion_last_edited_time"]
        if article is None:
            decisions.append(decide(keeper, "KEEP", "-", "no article for this page yet - a real new page"))
        elif not _is_time(article_time):
            decisions.append(decide(
                keeper, "MANUAL", "C",
                f"article {article_id} has no notion_last_edited_time - cannot tell if this is stale"))
        elif keeper_time <= article_time:
            decisions.append(decide(
                keeper, "TRASH", "B",
                f"not newer than article {article_id} (item {keeper_time} <= article {article_time})"))
        else:
            decisions.append(decide(
                keeper, "KEEP", "-",
                f"newer than article {article_id} (item {keeper_time} > article {article_time}) - a real Notion change, left for review"))

    return sorted(decisions, key=lambda decision: decision.item_id)


def build_plan(items, articles_by_page, articles_by_id):
    by_page = {}
    for item in items:
        by_page.setdefault(item["notion_page_id"], []).append(item)

    plan = []
    for page_id in sorted(by_page, key=str):
        group = sorted(by_page[page_id], key=lambda item: item["id"])
        article, problem = _article_for_page(page_id, group, articles_by_page, articles_by_id)
        plan.extend(_decide_page(page_id, group, article, problem))
    return plan


def summarize(plan):
    return {
        "total": len(plan),
        "trash_a": sum(1 for d in plan if d.action == "TRASH" and d.rule == "A"),
        "trash_b": sum(1 for d in plan if d.action == "TRASH" and d.rule == "B"),
        "keep": sum(1 for d in plan if d.action == "KEEP"),
        "manual": sum(1 for d in plan if d.action == "MANUAL"),
    }


# --------------------------------------------------------------------------
# Reading the database (SELECT only)
# --------------------------------------------------------------------------
def load_state(db):
    items = db.rows("""
        SELECT id, notion_page_id, article_id, proposed_title, notion_last_edited_time
        FROM notion_pending_updates
        WHERE status = 'pending'
        ORDER BY notion_page_id, id
    """)

    articles_by_page = {}
    for row in db.rows("""
        SELECT article_id, notion_page_id, notion_last_edited_time
        FROM wiki_article
        WHERE notion_page_id IS NOT NULL
    """):
        articles_by_page.setdefault(row["notion_page_id"], []).append(row)

    articles_by_id = {}
    linked = sorted({item["article_id"] for item in items if item["article_id"] is not None})
    for start in range(0, len(linked), 500):
        chunk = linked[start:start + 500]
        for row in db.rows(
            f"SELECT article_id, notion_page_id, notion_last_edited_time FROM wiki_article "
            f"WHERE article_id IN ({in_clause(chunk)})", tuple(chunk)
        ):
            articles_by_id[row["article_id"]] = row

    return items, articles_by_page, articles_by_id


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def default_path(prefix):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / f"{prefix}_{_stamp()}.csv"


def write_plan_csv(plan, path):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(PLAN_COLUMNS)
        for d in plan:
            writer.writerow([
                d.item_id, d.page_id, d.title, d.kind, d.item_time or "", d.article_id or "",
                d.article_time or "", d.action, d.rule, d.reason,
            ])


def print_plan(plan, out, apply):
    counts = summarize(plan)
    out("NOTION PENDING CLEANUP  (" + ("APPLY MODE" if apply else "DRY RUN - nothing was changed") + ")")
    out("=" * 66)
    out(f"Pending items found:                          {counts['total']}")
    out(f"  Rule A - older duplicates, to Trash:        {counts['trash_a']}")
    out(f"  Rule B - stale vs. the article, to Trash:   {counts['trash_b']}")
    out(f"  Kept for manager review:                    {counts['keep']}")
    out(f"  Needs manual review (left untouched):       {counts['manual']}")

    by_page = {}
    for d in plan:
        by_page.setdefault(d.page_id, []).append(d)

    shown = 0
    out("\nPer page (single, untouched new pages are only in the CSV):")
    for page_id, decisions in by_page.items():
        if len(decisions) == 1 and decisions[0].action == "KEEP" and decisions[0].article_id is None:
            continue
        shown += 1
        first = decisions[0]
        article = f"article {first.article_id}" if first.article_id else "no article"
        out(f"\n  page {page_id}  \"{first.title}\"  [{article}]")
        for d in decisions:
            out(f"    #{d.item_id:<6} {d.action:<6} {d.rule:<2} {d.reason}")
    if shown == 0:
        out("  (nothing to report)")


# --------------------------------------------------------------------------
# Connection / service
# --------------------------------------------------------------------------
def connect(read_only):
    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
        charset="utf8mb4",
    )
    if read_only:
        cursor = conn.cursor()
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
        cursor.close()
    return conn


def load_service():
    """The app's own trash/restore/lock code, imported only when we really write."""
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    try:
        import notion_sync_service
    except ImportError:
        raise SystemExit(
            "--apply and --undo reuse the backend's own Trash code, so they need the backend "
            "requirements installed (pip install -r backend/requirements.txt, plus requests and "
            "cryptography). Nothing was changed."
        )
    return notion_sync_service


def _db_error_message(error):
    errno = getattr(error, "errno", None)
    if errno in (1146, 1054):
        return "The Notion tables are missing or out of date (has Notion Sync ever run on this database?)."
    return f"Database error{f' (errno {errno})' if errno else ''}."


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
def _write_undo_log(path, changed, applied_at):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(UNDO_COLUMNS)
        for d in changed:
            writer.writerow([d.item_id, "pending", "trashed", d.page_id, d.rule, d.reason, applied_at])
        handle.flush()
        os.fsync(handle.fileno())


def run_cleanup(connect, apply, plan_csv, undo_log, out):
    plan_csv = Path(plan_csv or default_path("pending_cleanup_plan"))

    if not apply:
        conn = connect(read_only=True)
        try:
            plan = build_plan(*load_state(ReadOnly(conn)))
        finally:
            conn.close()
        print_plan(plan, out, apply=False)
        write_plan_csv(plan, plan_csv)
        out(f"\nPlan written to {plan_csv}")
        out("Nothing was changed. To apply this plan, run the same command with --apply.")
        return 0

    svc = load_service()
    conn = connect(read_only=False)
    cursor = conn.cursor(dictionary=True)
    lock_held = False
    try:
        lock = svc._acquire_db_check_lock(cursor)
        if lock is not True:
            out("Stopped: a Notion sync is running" if lock is False
                else "Stopped: the sync lock could not be taken")
            out("Wait for it to finish and run this again. Nothing was changed.")
            return 2
        lock_held = True

        # The plan is built while holding the lock, so no sync can queue or
        # refresh items between planning and applying.
        db = ReadOnly(conn)
        plan = build_plan(*load_state(db))
        conn.commit()  # end the read snapshot before the write phase
        print_plan(plan, out, apply=True)
        write_plan_csv(plan, plan_csv)
        out(f"\nPlan written to {plan_csv}")

        changed = []
        try:
            for decision in (d for d in plan if d.action == "TRASH"):
                row = db.one("SELECT status FROM notion_pending_updates WHERE id = %s FOR UPDATE", (decision.item_id,))
                if not row or row["status"] != "pending":
                    continue  # approved, trashed or dismissed since the plan was made
                if svc.trash_pending_update(cursor, decision.item_id, None):
                    changed.append(decision)

            if changed:
                # Written before the commit: if the log can't be saved, nothing is committed.
                undo_log = Path(undo_log or default_path("pending_cleanup_undo"))
                _write_undo_log(undo_log, changed, datetime.now(timezone.utc).isoformat(timespec="seconds"))
            conn.commit()
        except Exception as error:
            conn.rollback()
            if isinstance(error, mysql.connector.Error):
                reason = _db_error_message(error)
            elif isinstance(error, OSError):
                reason = "Could not write the undo log file."
            else:
                reason = f"Unexpected error ({type(error).__name__})."
            out(f"FAILED and rolled back: {reason} Nothing was changed.")
            return 1

        out(f"\n{len(changed)} item(s) moved to Trash.")
        if changed:
            out(f"Undo log: {undo_log}")
            out("They are in Notion Sync > Pending > Trash and can be restored there,")
            out("or with:  --undo <undo log> --apply")
        return 0
    except mysql.connector.Error as error:
        conn.rollback()
        out(f"FAILED: {_db_error_message(error)} Nothing was changed.")
        return 1
    finally:
        if lock_held:
            svc._release_db_check_lock(cursor)
        cursor.close()
        conn.close()


def run_undo(connect, undo_file, apply, out):
    with open(undo_file, newline="", encoding="utf-8") as handle:
        wanted = [
            int(row["item_id"]) for row in csv.DictReader(handle)
            if row.get("previous_status") == "pending" and row.get("new_status") == "trashed"
        ]
    out("NOTION PENDING CLEANUP - UNDO  (" + ("APPLY MODE" if apply else "DRY RUN - nothing was changed") + ")")
    out(f"Undo log lists {len(wanted)} item(s).")

    if not apply:
        conn = connect(read_only=True)
        try:
            db = ReadOnly(conn)
            restorable = 0
            for item_id in wanted:
                row = db.one("SELECT status FROM notion_pending_updates WHERE id = %s", (item_id,))
                restorable += 1 if row and row["status"] == "trashed" else 0
        finally:
            conn.close()
        out(f"{restorable} of them are still in Trash and would be restored. Add --apply to do it.")
        return 0

    svc = load_service()
    conn = connect(read_only=False)
    cursor = conn.cursor(dictionary=True)
    lock_held = False
    try:
        lock = svc._acquire_db_check_lock(cursor)
        if lock is not True:
            out("Stopped: a Notion sync is running" if lock is False
                else "Stopped: the sync lock could not be taken")
            out("Wait for it to finish and run this again. Nothing was changed.")
            return 2
        lock_held = True
        conn.commit()

        db = ReadOnly(conn)
        restored = 0
        try:
            for item_id in wanted:
                row = db.one("SELECT status FROM notion_pending_updates WHERE id = %s FOR UPDATE", (item_id,))
                if row and row["status"] == "trashed" and svc.restore_pending_update_from_trash(cursor, item_id):
                    restored += 1
            conn.commit()
        except Exception as error:
            conn.rollback()
            reason = _db_error_message(error) if isinstance(error, mysql.connector.Error) \
                else f"Unexpected error ({type(error).__name__})."
            out(f"FAILED and rolled back: {reason} Nothing was changed.")
            return 1

        out(f"{restored} item(s) restored from Trash to Pending.")
        return 0
    finally:
        if lock_held:
            svc._release_db_check_lock(cursor)
        cursor.close()
        conn.close()


def run(connect, apply=False, plan_csv=None, undo_log=None, undo_file=None, out=print):
    """Returns the process exit code: 0 ok, 1 failed (rolled back), 2 refused (sync running)."""
    try:
        if undo_file:
            return run_undo(connect, undo_file, apply, out)
        return run_cleanup(connect, apply, plan_csv, undo_log, out)
    except mysql.connector.Error as error:
        out(f"FAILED: {_db_error_message(error)} Nothing was changed.")
        return 1
    except OSError as error:
        out(f"FAILED: file problem ({error.strerror or type(error).__name__}). Nothing was changed.")
        return 1
    except Exception as error:  # never show a stack trace (it could include connection details)
        out(f"FAILED: unexpected error ({type(error).__name__}). Nothing was changed.")
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="make the changes (default is a dry run)")
    parser.add_argument("--csv", help="where to write the plan CSV (default: backend/tools/cleanup_output/)")
    parser.add_argument("--undo-log", help="where to write the undo log (default: backend/tools/cleanup_output/)")
    parser.add_argument("--undo", metavar="UNDO_LOG", help="restore the items listed in an undo log (dry run unless --apply)")
    args = parser.parse_args(argv)

    missing = [name for name in ("MYSQL_HOST", "MYSQL_USER", "MYSQL_DATABASE") if not os.getenv(name)]
    if missing:
        sys.exit("Missing environment variables: " + ", ".join(missing))

    sys.exit(run(connect, apply=args.apply, plan_csv=args.csv, undo_log=args.undo_log, undo_file=args.undo))


if __name__ == "__main__":
    main()
