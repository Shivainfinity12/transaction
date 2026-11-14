"""Step 9 — Delete Expense tests.

Spec source: .opencode/specs/09-delete-expense.md — every test below validates a
behaviour the spec explicitly requires (Routes, Rules for implementation,
Definition of done 1-9). Route tests cover GET/POST /expenses/<id>/delete
(auth guard, confirmation rendering, GET-never-deletes, 404 scoping on missing
and foreign ids, actual deletion on POST, stale-delete safety, profile Delete
links) against the seeded temp database from conftest's seeded_db/client
fixtures.

Baseline (seed data): demo user id=1 owns 8 expenses with ids 1-8. Expense
id 1 = 2026-11-01 / Food / 12.50 / "Lunch at cafeteria"; id 2 = 2026-11-02 /
Transport / 8.75 / "Bus fare". Seed amounts are SQLite REAL, so 12.50 is
stored as 12.5 — the confirmation page is expected to format it with 2
decimals as "12.50". A delete reduces the row count from 8 to 7.

Counting nuance: the profile table's Edit links carry class="table-action"
and Delete links carry class="table-action table-action-danger". The
substring 'class="table-action"' matches ONLY the Edit links (the Delete
link's class string continues with " table-action-danger" before the closing
quote), so Edit-link counting stays valid — but Delete links must be counted
via 'table-action table-action-danger' or '/delete' URL occurrences instead.
"""

import database.db as database_db

DEMO_CREDENTIALS = {"email": "demo@spendly.com", "password": "demo123"}

SEED_ROW_COUNT = 8
DELETED_EXPENSE_ID = 1
UNTOUCHED_EXPENSE_ID = 2
NONEXISTENT_EXPENSE_ID = 999

SEED_ROW_1 = {
    "user_id": 1,
    "amount": 12.5,
    "category": "Food",
    "date": "2026-11-01",
    "description": "Lunch at cafeteria",
}

RIVAL_ROW = {
    "user_id": 2,
    "amount": 42.0,
    "category": "Shopping",
    "date": "2026-11-09",
    "description": "Rival's private expense",
}

LOGIN_URL = "/login"
LOGOUT_URL = "/logout"
REGISTER_URL = "/register"
PROFILE_URL = "/profile"
ADD_EXPENSE_URL = "/expenses/add"

DELETE_LINK_CLASS = "table-action table-action-danger"


def _delete_url(expense_id):
    return f"/expenses/{expense_id}/delete"


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #


def _login(client, credentials=DEMO_CREDENTIALS):
    return client.post(LOGIN_URL, data=credentials)


def _register_and_login(client, name, email, password="password123"):
    """Register a fresh user through the real POST /register, then log in."""
    client.post(REGISTER_URL, data={"name": name, "email": email, "password": password})
    return client.post(LOGIN_URL, data={"email": email, "password": password})


def _expense_row_count():
    """Total rows in the expenses table (routed to the patched temp DB)."""
    db = database_db.get_db()
    try:
        return db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        db.close()


def _fetch_expense(expense_id):
    """The expense row with the given id as a plain dict, or None."""
    db = database_db.get_db()
    try:
        row = db.execute(
            "SELECT user_id, amount, category, date, description "
            "FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def _assert_row_matches(expense_id, expected):
    row = _fetch_expense(expense_id)
    assert row is not None, f"Expense {expense_id} must still exist"
    assert row == expected, (
        f"Expense {expense_id} must match {expected}, got {row}"
    )


def _assert_row_unchanged(expense_id, expected=SEED_ROW_1):
    _assert_row_matches(expense_id, expected)


def _attack_expense_of_second_user(client):
    """Register a second user, add one expense as them, then re-login as demo.

    Returns the id of the second user's expense so tests can target it.
    """
    _register_and_login(
        client, name="Rival User", email="rival@spendly.com"
    )
    client.post(
        ADD_EXPENSE_URL,
        data={
            "amount": "42.00",
            "category": "Shopping",
            "date": "2026-11-09",
            "description": "Rival's private expense",
        },
    )
    rival_ids = _user_expense_ids(2)
    assert len(rival_ids) == 1, "Setup: the second user must own exactly one expense"
    client.get(LOGOUT_URL)
    _login(client)
    return rival_ids[0]


def _user_expense_ids(user_id):
    """Ids of every expense owned by the given user."""
    db = database_db.get_db()
    try:
        rows = db.execute(
            "SELECT id FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [row["id"] for row in rows]
    finally:
        db.close()


# ------------------------------------------------------------------ #
# Auth guard (DoD 1, 7)                                               #
# ------------------------------------------------------------------ #


def test_delete_expense_get_redirects_to_login_when_logged_out(client):
    response = client.get(_delete_url(DELETED_EXPENSE_ID))
    assert response.status_code == 302, "Logged-out GET must redirect"
    assert response.headers["Location"].endswith(LOGIN_URL), (
        "Logged-out GET must redirect to the login page"
    )


def test_delete_expense_post_redirects_to_login_when_logged_out_and_deletes_nothing(client):
    response = client.post(_delete_url(DELETED_EXPENSE_ID))
    assert response.status_code == 302, "Logged-out POST must redirect"
    assert response.headers["Location"].endswith(LOGIN_URL), (
        "Logged-out POST must redirect to the login page"
    )
    assert _expense_row_count() == SEED_ROW_COUNT, (
        "Logged-out POST must not remove any rows"
    )
    _assert_row_unchanged(DELETED_EXPENSE_ID)


# ------------------------------------------------------------------ #
# Confirmation page rendering (DoD 2)                                 #
# ------------------------------------------------------------------ #


def test_delete_expense_get_logged_in_renders_confirmation_form_targeting_delete_url(client):
    _login(client)
    response = client.get(_delete_url(DELETED_EXPENSE_ID))
    assert response.status_code == 200, "Logged-in GET must render the confirmation page"
    body = response.data.decode("utf-8")
    assert f'action="{_delete_url(DELETED_EXPENSE_ID)}"' in body, (
        "The form action must target this expense's /expenses/<id>/delete URL"
    )
    assert 'method="post"' in body.lower(), (
        "The confirmation form must submit via POST — the mutation must never fire on GET"
    )


def test_delete_expense_get_logged_in_shows_expense_details(client):
    _login(client)
    body = client.get(_delete_url(DELETED_EXPENSE_ID)).data.decode("utf-8")
    assert "2026-11-01" in body, "The confirmation page must show the expense's date"
    assert "Lunch at cafeteria" in body, (
        "The confirmation page must show the expense's description"
    )
    assert "Food" in body, "The confirmation page must show the expense's category"
    assert "12.50" in body, (
        "The confirmation page must show the amount formatted with 2 decimals"
    )


def test_delete_expense_get_logged_in_shows_confirm_button_and_cancel_link(client):
    _login(client)
    body = client.get(_delete_url(DELETED_EXPENSE_ID)).data.decode("utf-8")
    assert "Delete" in body, "The confirmation page must have a Delete (confirm) button"
    assert PROFILE_URL in body, (
        "The confirmation page must offer a Cancel link back to the profile"
    )


# ------------------------------------------------------------------ #
# GET never deletes (DoD 4)                                           #
# ------------------------------------------------------------------ #


def test_delete_expense_get_never_deletes_anything(client):
    _login(client)
    response = client.get(_delete_url(DELETED_EXPENSE_ID))
    assert response.status_code == 200
    assert _expense_row_count() == SEED_ROW_COUNT, (
        "Visiting the confirmation page must not delete the row"
    )
    assert _fetch_expense(DELETED_EXPENSE_ID) is not None, (
        "Expense 1 must still exist after a GET"
    )


# ------------------------------------------------------------------ #
# 404 scoping — GET (DoD 3)                                           #
# ------------------------------------------------------------------ #


def test_delete_expense_get_nonexistent_id_returns_404(client):
    _login(client)
    response = client.get(_delete_url(NONEXISTENT_EXPENSE_ID))
    assert response.status_code == 404, (
        "GET on a nonexistent expense id must respond 404"
    )


def test_delete_expense_get_another_users_expense_returns_404_and_leaves_row_unchanged(client):
    rival_expense_id = _attack_expense_of_second_user(client)
    response = client.get(_delete_url(rival_expense_id))
    assert response.status_code == 404, (
        "GET on another user's expense must respond 404, not expose the row"
    )
    _assert_row_matches(rival_expense_id, RIVAL_ROW)


# ------------------------------------------------------------------ #
# Happy path — POST deletes (DoD 5, 6)                                #
# ------------------------------------------------------------------ #


def test_delete_expense_post_deletes_row_and_redirects_to_profile(client):
    _login(client)
    response = client.post(_delete_url(DELETED_EXPENSE_ID))
    assert response.status_code == 302, "A successful delete POST must redirect"
    assert response.headers["Location"].endswith(PROFILE_URL), (
        "A successful delete POST must redirect to the profile page"
    )
    assert _expense_row_count() == SEED_ROW_COUNT - 1, (
        "The delete POST must remove exactly one row (8 -> 7)"
    )
    assert _fetch_expense(DELETED_EXPENSE_ID) is None, (
        "Expense 1 must be gone from the database after the delete POST"
    )
    other = _fetch_expense(UNTOUCHED_EXPENSE_ID)
    assert other["user_id"] == 1, "Other seed rows must not be touched by the delete"
    assert other["amount"] == 8.75, "Other seed rows must not be touched by the delete"
    assert other["category"] == "Transport", (
        "Other seed rows must not be touched by the delete"
    )
    assert other["date"] == "2026-11-02", (
        "Other seed rows must not be touched by the delete"
    )
    assert other["description"] == "Bus fare", (
        "Other seed rows must not be touched by the delete"
    )


def test_delete_expense_post_deleted_row_no_longer_on_profile(client):
    _login(client)
    client.post(_delete_url(DELETED_EXPENSE_ID))
    body = client.get(PROFILE_URL).data.decode("utf-8")
    assert "Lunch at cafeteria" not in body, (
        "The deleted description must no longer appear on the profile page"
    )


# ------------------------------------------------------------------ #
# 404 scoping — POST (DoD 7)                                          #
# ------------------------------------------------------------------ #


def test_delete_expense_post_nonexistent_id_returns_404_and_deletes_nothing(client):
    _login(client)
    response = client.post(_delete_url(NONEXISTENT_EXPENSE_ID))
    assert response.status_code == 404, (
        "POST on a nonexistent expense id must respond 404"
    )
    assert _expense_row_count() == SEED_ROW_COUNT, (
        "POST on a nonexistent expense id must not remove any rows"
    )


def test_delete_expense_post_another_users_expense_returns_404_and_leaves_rows_unchanged(client):
    rival_expense_id = _attack_expense_of_second_user(client)
    response = client.post(_delete_url(rival_expense_id))
    assert response.status_code == 404, (
        "POST on another user's expense must respond 404"
    )
    assert _expense_row_count() == SEED_ROW_COUNT + 1, (
        "POST on another user's expense must not remove any rows (8 seed + 1 rival)"
    )
    _assert_row_matches(rival_expense_id, RIVAL_ROW)
    _assert_row_unchanged(DELETED_EXPENSE_ID)


# ------------------------------------------------------------------ #
# Stale delete safety (DoD 8)                                         #
# ------------------------------------------------------------------ #


def test_delete_expense_post_twice_second_post_returns_404_not_crash(client):
    _login(client)
    first = client.post(_delete_url(DELETED_EXPENSE_ID))
    assert first.status_code == 302, "The first delete POST must succeed"
    second = client.post(_delete_url(DELETED_EXPENSE_ID))
    assert second.status_code == 404, (
        "A second POST on an already-deleted expense must respond 404, not crash"
    )
    assert _expense_row_count() == SEED_ROW_COUNT - 1, (
        "The second POST must not remove any additional rows"
    )


# ------------------------------------------------------------------ #
# Profile integration (DoD 9)                                         #
# ------------------------------------------------------------------ #


def test_profile_shows_delete_link_for_each_row(client):
    _login(client)
    body = client.get(PROFILE_URL).data.decode("utf-8")
    assert _delete_url(DELETED_EXPENSE_ID) in body, (
        "Each row must have a Delete link to its /expenses/<id>/delete URL"
    )
    delete_links = body.count(DELETE_LINK_CLASS)
    assert delete_links == SEED_ROW_COUNT, (
        f"Each of the {SEED_ROW_COUNT} rows must have one Delete link, "
        f"found {delete_links}"
    )
    delete_urls = body.count(_delete_url(DELETED_EXPENSE_ID))
    assert delete_urls >= 1, (
        "The Delete link for expense 1 must appear on the profile page"
    )


def test_profile_shows_no_delete_links_for_user_with_no_expenses(client):
    _register_and_login(client, name="Empty User", email="empty@spendly.com")
    body = client.get(PROFILE_URL).data.decode("utf-8")
    assert DELETE_LINK_CLASS not in body, (
        "A user with no expenses must not see any Delete links"
    )
    assert "/delete" not in body, (
        "A user with no expenses must not see any Delete links"
    )
