"""Step 5 — Backend Connection tests.

Unit tests cover the four query helpers in database/queries.py against a
seeded temp database; route tests cover GET /profile behaviour.

Note: expected values follow the ACTUAL seed data in database/db.py —
8 expenses totalling 209.54 with top category "Shopping" — not the stale
numbers (346.24 / "Bills") in the spec's definition of done.
"""

import sqlite3
from datetime import datetime

import pytest

from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

# A user id with no expenses (also used as a non-existent user for lookups).
NO_EXPENSES_USER_ID = 999

DEMO_CREDENTIALS = {"email": "demo@spendly.com", "password": "demo123"}

SEED_TOTAL = 209.54
SEED_CATEGORIES = (
    "Shopping",
    "Bills",
    "Health",
    "Food",
    "Entertainment",
    "Other",
    "Transport",
)


# ------------------------------------------------------------------ #
# get_user_by_id                                                      #
# ------------------------------------------------------------------ #


def test_get_user_by_id_returns_name_email_member_since(seeded_db):
    user = get_user_by_id(1)
    assert set(user) == {"name", "email", "member_since"}
    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"

    db = sqlite3.connect(str(seeded_db))
    created_at = db.execute(
        "SELECT created_at FROM users WHERE id = 1"
    ).fetchone()[0]
    db.close()
    expected_member_since = datetime.strptime(
        created_at[:10], "%Y-%m-%d"
    ).strftime("%B %Y")
    assert user["member_since"] == expected_member_since


def test_get_user_by_id_unknown_id_returns_none(seeded_db):
    assert get_user_by_id(NO_EXPENSES_USER_ID) is None


# ------------------------------------------------------------------ #
# get_summary_stats                                                   #
# ------------------------------------------------------------------ #


def test_get_summary_stats_with_expenses(seeded_db):
    stats = get_summary_stats(1)
    assert stats["total_spent"] == pytest.approx(SEED_TOTAL)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Shopping"


def test_get_summary_stats_without_expenses(seeded_db):
    assert get_summary_stats(NO_EXPENSES_USER_ID) == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }


# ------------------------------------------------------------------ #
# get_recent_transactions                                             #
# ------------------------------------------------------------------ #


def test_get_recent_transactions_ordered_newest_first(seeded_db):
    rows = get_recent_transactions(1)
    assert len(rows) == 8
    for row in rows:
        assert set(row) == {"date", "description", "category", "amount"}
    dates = [row["date"] for row in rows]
    assert dates == sorted(dates, reverse=True)
    assert rows[0]["date"] == "2026-11-08"
    assert rows[-1]["date"] == "2026-11-01"


def test_get_recent_transactions_respects_limit(seeded_db):
    rows = get_recent_transactions(1, limit=3)
    assert len(rows) == 3
    assert rows[0]["date"] == "2026-11-08"


def test_get_recent_transactions_without_expenses(seeded_db):
    assert get_recent_transactions(NO_EXPENSES_USER_ID) == []


# ------------------------------------------------------------------ #
# get_category_breakdown                                              #
# ------------------------------------------------------------------ #


def test_get_category_breakdown_ordered_and_pct_sums_to_100(seeded_db):
    rows = get_category_breakdown(1)
    assert len(rows) == 7
    for row in rows:
        assert set(row) == {"name", "amount", "pct"}
        assert isinstance(row["pct"], int)

    amounts = [row["amount"] for row in rows]
    assert amounts == sorted(amounts, reverse=True)
    assert rows[0]["name"] == "Shopping"
    assert rows[0]["amount"] == pytest.approx(45.99)

    assert sum(row["pct"] for row in rows) == 100
    # Largest category absorbs the rounding remainder:
    # floor(45.99 / 209.54 * 100) == 21, remainder 4 -> 25.
    assert rows[0]["pct"] == 25


def test_get_category_breakdown_without_expenses(seeded_db):
    assert get_category_breakdown(NO_EXPENSES_USER_ID) == []


# ------------------------------------------------------------------ #
# Route tests: GET /profile                                           #
# ------------------------------------------------------------------ #


def _login(client, credentials=DEMO_CREDENTIALS):
    return client.post("/login", data=credentials)


def test_profile_redirects_to_login_when_not_authenticated(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_profile_shows_seed_user_data(client):
    _login(client)
    body = client.get("/profile").data.decode("utf-8")
    assert "Demo User" in body
    assert "demo@spendly.com" in body
    assert "₹" in body


def test_profile_summary_stats_match_seed_data(client):
    _login(client)
    body = client.get("/profile").data.decode("utf-8")
    assert '<div class="stat-value">₹209.54</div>' in body
    assert '<div class="stat-value">8</div>' in body
    assert '<div class="stat-value">Shopping</div>' in body


def test_profile_transactions_newest_first(client):
    _login(client)
    body = client.get("/profile").data.decode("utf-8")
    for day in range(1, 9):
        assert f"2026-11-{day:02d}" in body
    assert body.index("2026-11-08") < body.index("2026-11-01")


def test_profile_category_breakdown_has_all_seed_categories(client):
    _login(client)
    body = client.get("/profile").data.decode("utf-8")
    for category in SEED_CATEGORIES:
        assert category in body


def test_profile_new_user_sees_zeroed_stats(client):
    client.post(
        "/register",
        data={
            "name": "New Person",
            "email": "new@spendly.com",
            "password": "password123",
        },
    )
    _login(client, {"email": "new@spendly.com", "password": "password123"})
    body = client.get("/profile").data.decode("utf-8")
    assert "New Person" in body
    assert '<div class="stat-value">₹0.00</div>' in body
    assert '<div class="stat-value">0</div>' in body
    # Empty transaction history and empty category breakdown.
    assert "Lunch at cafeteria" not in body
    assert "category-name" not in body
