"""Read-only report: which accounts do NOT store a recognised password hash.

Login and change password only compare typed text directly with users.password_hash when the stored value
is not a hash at all (a legacy plain-text password); that account is upgraded to a real hash on its next
successful sign-in. This report shows how many such accounts exist, so the legacy path can be removed once
the count is 0.

It NEVER changes anything: every statement must be a SELECT/SHOW (the script refuses otherwise) and the
session is opened read-only. It never prints a password hash or any part of one, only the user id, role,
status and a masked email. It connects with the same MYSQL_HOST / MYSQL_PORT / MYSQL_USER /
MYSQL_PASSWORD / MYSQL_DATABASE variables the backend uses and prints no credentials.

    railway run python backend/tools/legacy_password_report.py
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from password_check import classify_stored_password  # noqa: E402  (the same rule login uses)

_READ_ONLY_SQL = re.compile(r"^\s*(SELECT|SHOW)\b", re.IGNORECASE)

GROUPS = (
    ("plaintext", "Legacy plain-text password (not a hash). Upgraded to a hash on the next successful sign-in"),
    ("empty", "No password stored. This account cannot sign in until the password is reset"),
    ("other_hash", "A hash format this backend cannot verify. This account cannot sign in until the password is reset"),
)


def connect():
    import mysql.connector

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


def mask_email(email):
    """j***@junglehouse.com. Never more than the first character of the name."""
    value = str(email or "").strip()
    name, at, domain = value.partition("@")
    if not at or not name:
        return "***"
    return f"{name[0]}***@{domain}"


def collect(db):
    """-> {"total": n, "verifiable": n, "groups": {group: [ {user_id, role, status, email}, ... ]}}

    The hash is classified here and dropped at once; it is never stored in the result.
    """
    users = db.rows("""
        SELECT u.user_id, u.email, u.status, u.password_hash, r.role_name
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.role_id
        ORDER BY u.user_id
    """)
    report = {"total": len(users), "verifiable": 0, "groups": {name: [] for name, _ in GROUPS}}
    for row in users:
        kind = classify_stored_password(row.get("password_hash"))
        row["password_hash"] = None                       # never kept, never printed
        if kind == "verifiable":
            report["verifiable"] += 1
            continue
        report["groups"][kind].append({
            "user_id": row.get("user_id"),
            "role": row.get("role_name") or "-",
            "status": row.get("status") or "-",
            "email": mask_email(row.get("email")),
        })
    return report


def render(report):
    lines = [
        "Legacy password report (read-only)",
        f"Accounts checked: {report['total']}",
        f"Recognised hash this backend can verify: {report['verifiable']}",
    ]
    for name, title in GROUPS:
        accounts = report["groups"][name]
        lines.append("")
        lines.append(f"{title}: {len(accounts)}")
        for account in accounts:
            lines.append(f"  user_id={account['user_id']}  role={account['role']}  status={account['status']}  email={account['email']}")
    not_recognised = len(report["groups"]["plaintext"]) + len(report["groups"]["empty"])
    lines.append("")
    lines.append(f"NOT a recognised hash format (plain text or empty): {not_recognised}")
    if not report["groups"]["plaintext"]:
        lines.append("No legacy plain-text passwords: the legacy sign-in path can be removed.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.parse_args(argv)
    try:
        conn = connect()
    except Exception as error:      # no credentials or host in the message
        print(f"Database is not reachable. Check the MYSQL_* variables. ({type(error).__name__})", file=sys.stderr)
        return 2
    try:
        print(render(collect(ReadOnly(conn))))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
