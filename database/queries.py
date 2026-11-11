"""Pure SQLite query helpers for the profile page.

Step 5 — Backend Connection (.opencode/specs/05-backend-routes-for-profile-page.md)
Step 06 — Date Filter (.opencode/specs/06-date-filter-for-profile-page.md) added
optional start_date/end_date bounds to the three profile helpers below.

Date bounds shared by every helper: start_date and end_date are optional
inclusive bounds in YYYY-MM-DD format (expenses.date is TEXT, so plain
lexicographic comparison is correct). None means unbounded on that side.

Rules for every helper in this module:
- Raw sqlite3 only via get_db() — no ORMs
- Parameterised queries only — never string-format values into SQL
- Each helper opens its own connection and closes it before returning
- Empty data returns zeros / empty lists, never exceptions
"""

from datetime import datetime

from database.db import get_db


def _expense_where_clause(user_id, start_date, end_date):
    """Shared WHERE clause: user ownership plus optional date bounds.

    Clause text is literal; every value travels via a ? placeholder.
    Returns (where_clause, params) — extend both with further literal
    clauses (ORDER BY, LIMIT, GROUP BY) before executing.
    """
    where = "WHERE user_id = ?"
    params = [user_id]
    if start_date is not None:
        where += " AND date >= ?"
        params.append(start_date)
    if end_date is not None:
        where += " AND date <= ?"
        params.append(end_date)
    return where, params


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


def get_recent_transactions(user_id, limit=10, start_date=None, end_date=None):
    """Return the user's most recent transactions, newest first.

    Optional inclusive date bounds — see the module docstring.

    Returns a list of plain dicts, each with keys "date", "description",
    "category" and "amount", ordered newest-first (date DESC, then id DESC
    for stable ordering of same-date rows). Returns [] when the user has
    no expenses in the (possibly filtered) period.
    """
    where, params = _expense_where_clause(user_id, start_date, end_date)
    params.append(limit)

    query = (
        "SELECT date, description, category, amount "
        "FROM expenses " + where + " "
        "ORDER BY date DESC, id DESC LIMIT ?"
    )

    db = get_db()
    try:
        rows = db.execute(query, params).fetchall()
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


def get_summary_stats(user_id, start_date=None, end_date=None):
    """Return summary stats for the user's expenses as a dict.

    Optional inclusive date bounds — see the module docstring. Both
    queries below use the same bounds so the stats describe the same
    filtered period.

    Returns {"total_spent": float, "transaction_count": int,
    "top_category": str} where top_category is the category with the
    highest SUM(amount). When the user has no expenses in the filtered
    period, returns {"total_spent": 0, "transaction_count": 0,
    "top_category": "—"}.
    """
    where, params = _expense_where_clause(user_id, start_date, end_date)

    db = get_db()
    try:
        totals = db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total_spent,"
            " COUNT(*) AS transaction_count"
            " FROM expenses " + where,
            params,
        ).fetchone()
        top = db.execute(
            "SELECT category"
            " FROM expenses " + where +
            " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            params,
        ).fetchone()
    finally:
        db.close()

    return {
        "total_spent": totals["total_spent"],
        "transaction_count": totals["transaction_count"],
        "top_category": top["category"] if top is not None else "—",
    }


def get_category_breakdown(user_id, start_date=None, end_date=None):
    """Return the user's spending per category as a list of dicts.

    Optional inclusive date bounds — see the module docstring.
    Percentages are computed within the filtered period.

    Each dict has keys "name" (category), "amount" (SUM of that
    category's expenses) and "pct" (integer percentage of the user's
    total spending). Ordered by amount descending. The pct values are
    integers that sum to exactly 100: floor each share, then the largest
    category absorbs the rounding remainder. Returns [] when the user
    has no expenses in the (possibly filtered) period.
    """
    where, params = _expense_where_clause(user_id, start_date, end_date)

    db = get_db()
    try:
        rows = db.execute(
            "SELECT category, SUM(amount) AS total "
            "FROM expenses " + where + " "
            "GROUP BY category ORDER BY total DESC",
            params,
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
