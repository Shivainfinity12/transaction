"""Pure SQLite query helpers for the profile page.

Step 5 — Backend Connection (.opencode/specs/05-backend-routes-for-profile-page.md)

Rules for every helper in this module:
- Raw sqlite3 only via get_db() — no ORMs
- Parameterised queries only — never string-format values into SQL
- Each helper opens its own connection and closes it before returning
- Empty data returns zeros / empty lists, never exceptions
"""

from datetime import datetime

from database.db import get_db


def get_user_by_id(user_id):
    """Return the user's info as a dict, or None if no such user exists.

    Returns {"name": str, "email": str, "member_since": "Month YYYY"}.
    member_since is derived from users.created_at (e.g. "January 2026").
    """
    db = get_db()
    try:
        row = db.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        db.close()

    if row is None:
        return None

    member_since = datetime.strptime(row["created_at"][:10], "%Y-%m-%d").strftime(
        "%B %Y"
    )
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": member_since,
    }


def get_recent_transactions(user_id, limit=10):
    """Return the user's most recent transactions, newest first.

    Returns a list of plain dicts, each with keys "date", "description",
    "category" and "amount", ordered newest-first (date DESC, then id DESC
    for stable ordering of same-date rows). Returns [] when the user has
    no expenses.
    """
    # === SUBAGENT 1: transaction history ===
    db = get_db()
    try:
        rows = db.execute(
            "SELECT date, description, category, amount "
            "FROM expenses WHERE user_id = ? "
            "ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        db.close()

    return [
        {
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in rows
    ]
    # === END SUBAGENT 1 ===


def get_summary_stats(user_id):
    """Return summary stats for the user's expenses as a dict.

    Returns {"total_spent": float, "transaction_count": int,
    "top_category": str} where top_category is the category with the
    highest SUM(amount). When the user has no expenses, returns
    {"total_spent": 0, "transaction_count": 0, "top_category": "—"}.
    """
    # === SUBAGENT 2: summary stats ===
    db = get_db()
    try:
        totals = db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total_spent,"
            " COUNT(*) AS transaction_count"
            " FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        top = db.execute(
            "SELECT category"
            " FROM expenses WHERE user_id = ?"
            " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        db.close()

    return {
        "total_spent": totals["total_spent"],
        "transaction_count": totals["transaction_count"],
        "top_category": top["category"] if top is not None else "—",
    }
    # === END SUBAGENT 2 ===


def get_category_breakdown(user_id):
    """Return the user's spending per category as a list of dicts.

    Each dict has keys "name" (category), "amount" (SUM of that
    category's expenses) and "pct" (integer percentage of the user's
    total spending). Ordered by amount descending. The pct values are
    integers that sum to exactly 100: floor each share, then the largest
    category absorbs the rounding remainder. Returns [] when the user
    has no expenses.
    """
    # === SUBAGENT 3: category breakdown ===
    db = get_db()
    try:
        rows = db.execute(
            "SELECT category, SUM(amount) AS total "
            "FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY total DESC",
            (user_id,),
        ).fetchall()
    finally:
        db.close()

    if not rows:
        return []

    total_spent = sum(row["total"] for row in rows)
    if not total_spent:
        return []

    breakdown = [
        {
            "name": row["category"],
            "amount": row["total"],
            "pct": int(row["total"] / total_spent * 100),
        }
        for row in rows
    ]
    remainder = 100 - sum(item["pct"] for item in breakdown)
    if remainder:
        breakdown[0]["pct"] += remainder

    return breakdown
    # === END SUBAGENT 3 ===
