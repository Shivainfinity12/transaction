"""Step 8 — Edit Expense tests.

Spec source: .opencode/specs/08-edit-expense.md — every test below validates a
behaviour the spec explicitly requires (Routes, Rules for implementation,
Definition of done 2-10). Route tests cover GET/POST /expenses/<id>/edit
(auth guard, 404 scoping, prefilled form rendering, server-side validation,
DB updates) against the seeded temp database from conftest's seeded_db/client
fixtures.

Baseline (seed data): demo user id=1 owns 8 expenses with ids 1-8. Expense
id 1 = 2026-11-01 / Food / 12.50 / "Lunch at cafeteria"; id 2 = 2026-11-02 /
Transport / 8.75 / "Bus fare". Seed amounts are SQLite REAL, so 12.50 is
stored as 12.5 — numeric assertions compare against 12.5, and the prefilled
form is expected to format it with 2 decimals as "12.50".
"""

import re

import database.db as database_db

DEMO_CREDENTIALS = {"email": "demo@spendly.com", "password": "demo123"}

SEED_ROW_COUNT = 8
EDITED_EXPENSE_ID = 1
UNTOUCHED_EXPENSE_ID = 2

SEED_ROW_1 = {
    "user_id": 1,
    "amount": 12.5,
    "category": "Food",
    "date": "2026-11-01",
    "description": "Lunch at cafeteria",
}

FIXED_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

# The error div rendered by edit_expense.html when validation fails.
ERROR_MARKER = "auth-error"

LOGIN_URL = "/login"
LOGOUT_URL = "/logout"
REGISTER_URL = "/register"
PROFILE_URL = "/profile"
ADD_EXPENSE_URL = "/expenses/add"


def _edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


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


def _valid_payload(**overrides):
    """A valid edit-expense POST body for seed row 1, overridable per test."""
    payload = {
        "amount": "13.00",
        "category": "Transport",
        "date": "2026-11-05",
        "description": "Updated lunch note",
    }
    payload.update(overrides)
    return payload


def _input_value(body, field_name):
    """The value="..." attribute of the input with the given name, or None."""
    match = re.search(
        r'<input[^>]*name="' + re.escape(field_name) + r'"[^>]*>', body
    )
    if not match:
        return None
    value_match = re.search(r'value="([^"]*)"', match.group(0))
    return value_match.group(1) if value_match else None


def _assert_row_unchanged(expense_id, expected=SEED_ROW_1):
    row = _fetch_expense(expense_id)
    assert row is not None, f"Expense {expense_id} must still exist"
    assert row == expected, (
        f"Expense {expense_id} must be unchanged: expected {expected}, got {row}"
    )


# ------------------------------------------------------------------ #
# Auth guard (DoD 2)                                                  #
# ------------------------------------------------------------------ #


def test_edit_expense_get_redirects_to_login_when_logged_out(client):
    response = client.get(_edit_url(EDITED_EXPENSE_ID))
    assert response.status_code == 302, "Logged-out GET must redirect"
    assert response.headers["Location"].endswith(LOGIN_URL), (
        "Logged-out GET must redirect to the login page"
    )


def test_edit_expense_post_redirects_to_login_when_logged_out_and_changes_nothing(client):
    response = client.post(_edit_url(EDITED_EXPENSE_ID), data=_valid_payload())
    assert response.status_code == 302, "Logged-out POST must redirect"
    assert response.headers["Location"].endswith(LOGIN_URL), (
        "Logged-out POST must redirect to the login page"
    )
    assert _expense_row_count() == SEED_ROW_COUNT, (
        "Logged-out POST must not add or remove any rows"
    )
    _assert_row_unchanged(EDITED_EXPENSE_ID)


# ------------------------------------------------------------------ #
# 404 scoping (DoD 9)                                                 #
# ------------------------------------------------------------------ #


def test_edit_expense_get_nonexistent_id_returns_404(client):
    _login(client)
    response = client.get(_edit_url(999))
    assert response.status_code == 404, (
        "GET on a nonexistent expense id must respond 404"
    )


def test_edit_expense_post_nonexistent_id_returns_404_and_changes_nothing(client):
    _login(client)
    response = client.post(_edit_url(999), data=_valid_payload())
    assert response.status_code == 404, (
        "POST on a nonexistent expense id must respond 404"
    )
    assert _expense_row_count() == SEED_ROW_COUNT, (
        "POST on a nonexistent expense id must not create any row"
    )


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


def test_edit_expense_get_another_users_expense_returns_404(client):
    rival_expense_id = _attack_expense_of_second_user(client)
    response = client.get(_edit_url(rival_expense_id))
    assert response.status_code == 404, (
        "GET on another user's expense must respond 404, not expose the row"
    )


def test_edit_expense_post_another_users_expense_returns_404_and_leaves_row_unchanged(client):
    rival_expense_id = _attack_expense_of_second_user(client)
    response = client.post(_edit_url(rival_expense_id), data=_valid_payload())
    assert response.status_code == 404, (
        "POST on another user's expense must respond 404"
    )
    assert _expense_row_count() == SEED_ROW_COUNT + 1, (
        "POST on another user's expense must not add or remove any rows"
    )
    rival_row = _fetch_expense(rival_expense_id)
    assert rival_row["user_id"] == 2, "The rival row must still belong to user 2"
    assert rival_row["amount"] == 42.0, "The rival row's amount must be untouched"
    assert rival_row["category"] == "Shopping", "The rival row's category must be untouched"
    assert rival_row["date"] == "2026-11-09", "The rival row's date must be untouched"
    assert rival_row["description"] == "Rival's private expense", (
        "The rival row's description must be untouched"
    )
    _assert_row_unchanged(EDITED_EXPENSE_ID)


# ------------------------------------------------------------------ #
# Form rendering (DoD 4)                                              #
# ------------------------------------------------------------------ #


def test_edit_expense_get_logged_in_renders_form_targeting_the_expense_edit_url(client):
    _login(client)
    response = client.get(_edit_url(EDITED_EXPENSE_ID))
    assert response.status_code == 200, "Logged-in GET must render the edit form"
    body = response.data.decode("utf-8")
    assert f'action="{_edit_url(EDITED_EXPENSE_ID)}"' in body, (
        "The form action must target this expense's /expenses/<id>/edit URL"
    )


def test_edit_expense_get_logged_in_shows_all_four_fields(client):
    _login(client)
    body = client.get(_edit_url(EDITED_EXPENSE_ID)).data.decode("utf-8")
    for field in ["amount", "category", "date", "description"]:
        assert f'name="{field}"' in body, f"Edit form must contain the {field} field"


def test_edit_expense_get_logged_in_prefills_all_fields_from_stored_row(client):
    _login(client)
    body = client.get(_edit_url(EDITED_EXPENSE_ID)).data.decode("utf-8")
    assert _input_value(body, "amount") == "12.50", (
        "Amount must be prefilled from the stored row formatted with 2 decimals"
    )
    assert _input_value(body, "date") == "2026-11-01", (
        "Date must be prefilled from the stored row"
    )
    assert _input_value(body, "description") == "Lunch at cafeteria", (
        "Description must be prefilled from the stored row"
    )
    assert '<option value="Food" selected>' in body, (
        "The stored category (Food) must be the selected option"
    )


def test_edit_expense_get_logged_in_category_select_has_exactly_seven_fixed_categories(client):
    _login(client)
    body = client.get(_edit_url(EDITED_EXPENSE_ID)).data.decode("utf-8")
    for category in FIXED_CATEGORIES:
        assert f'value="{category}"' in body, f"Category {category!r} missing from select"
    assert body.count("<option") == len(FIXED_CATEGORIES), (
        "Category select must offer exactly the 7 fixed categories"
    )


def test_edit_expense_get_renders_null_description_as_empty_field(client):
    _login(client)
    # Store a NULL description first via a real edit of seed row 1.
    response = client.post(
        _edit_url(EDITED_EXPENSE_ID), data=_valid_payload(description="")
    )
    assert response.status_code == 302, "Setup edit with empty description must succeed"
    body = client.get(_edit_url(EDITED_EXPENSE_ID)).data.decode("utf-8")
    assert _input_value(body, "description") == "", (
        "A NULL stored description must render as an empty description field"
    )


# ------------------------------------------------------------------ #
# Happy path (DoD 5, 6)                                               #
# ------------------------------------------------------------------ #


def test_edit_expense_submitting_unchanged_values_succeeds_and_keeps_row_intact(client):
    _login(client)
    response = client.post(
        _edit_url(EDITED_EXPENSE_ID),
        data={
            "amount": "12.50",
            "category": "Food",
            "date": "2026-11-01",
            "description": "Lunch at cafeteria",
        },
    )
    assert response.status_code == 302, "Submitting unchanged values must succeed"
    assert response.headers["Location"].endswith(PROFILE_URL), (
        "Successful edit must redirect to the profile page"
    )
    assert _expense_row_count() == SEED_ROW_COUNT, (
        "Editing must update in place, never insert a row"
    )
    _assert_row_unchanged(EDITED_EXPENSE_ID)


def test_edit_expense_valid_post_updates_all_fields_and_redirects_to_profile(client):
    _login(client)
    response = client.post(
        _edit_url(EDITED_EXPENSE_ID),
        data=_valid_payload(amount="13.00", description="Updated lunch note"),
    )
    assert response.status_code == 302, "A valid edit POST must redirect on success"
    assert response.headers["Location"].endswith(PROFILE_URL), (
        "Successful edit must redirect to the profile page"
    )
    assert _expense_row_count() == SEED_ROW_COUNT, (
        "Editing must update in place, never insert a row"
    )
    row = _fetch_expense(EDITED_EXPENSE_ID)
    assert row["user_id"] == 1, "The edited row must still belong to the demo user"
    assert row["amount"] == 13.0, "Amount must be updated in the DB"
    assert row["category"] == "Transport", "Category must be updated in the DB"
    assert row["date"] == "2026-11-05", "Date must be updated in the DB"
    assert row["description"] == "Updated lunch note", (
        "Description must be updated in the DB"
    )
    other = _fetch_expense(UNTOUCHED_EXPENSE_ID)
    assert other["amount"] == 8.75, "Other rows must not be touched by the edit"
    assert other["category"] == "Transport", "Other rows must not be touched by the edit"
    assert other["date"] == "2026-11-02", "Other rows must not be touched by the edit"
    assert other["description"] == "Bus fare", "Other rows must not be touched by the edit"


def test_edit_expense_updated_values_visible_on_profile(client):
    _login(client)
    client.post(
        _edit_url(EDITED_EXPENSE_ID),
        data=_valid_payload(amount="13.00", description="Updated lunch note"),
    )
    body = client.get(PROFILE_URL).data.decode("utf-8")
    assert "Updated lunch note" in body, (
        "The updated description must appear in the profile transactions table"
    )
    assert "13.00" in body, "The updated amount must appear on the profile page"


def test_edit_expense_amount_rounded_to_two_decimals(client):
    _login(client)
    response = client.post(
        _edit_url(EDITED_EXPENSE_ID), data=_valid_payload(amount="12.999")
    )
    assert response.status_code == 302, "Rounding a valid amount must still succeed"
    row = _fetch_expense(EDITED_EXPENSE_ID)
    assert row["amount"] == 13.0, "12.999 must be stored rounded to 13.0"


# ------------------------------------------------------------------ #
# Validation errors (DoD 7, 10)                                       #
# ------------------------------------------------------------------ #


def test_edit_expense_invalid_amount_rerenders_with_error_and_leaves_row_unchanged(client):
    _login(client)
    for amount in ["", "abc", "0", "-5", "0.001"]:
        response = client.post(_edit_url(EDITED_EXPENSE_ID), data=_valid_payload(amount=amount))
        body = response.data.decode("utf-8")
        assert response.status_code == 200, f"Amount {amount!r} must re-render the form"
        assert ERROR_MARKER in body, f"Amount {amount!r} must show an error message"
        assert _expense_row_count() == SEED_ROW_COUNT, (
            f"Amount {amount!r} must not change the row count"
        )
        _assert_row_unchanged(EDITED_EXPENSE_ID)


def test_edit_expense_invalid_category_rerenders_with_error_and_leaves_row_unchanged(client):
    _login(client)
    for category in ["", "Lifestyle"]:
        response = client.post(
            _edit_url(EDITED_EXPENSE_ID), data=_valid_payload(category=category)
        )
        body = response.data.decode("utf-8")
        assert response.status_code == 200, f"Category {category!r} must re-render the form"
        assert ERROR_MARKER in body, f"Category {category!r} must show an error message"
        assert _expense_row_count() == SEED_ROW_COUNT, (
            f"Category {category!r} must not change the row count"
        )
        _assert_row_unchanged(EDITED_EXPENSE_ID)


def test_edit_expense_malformed_date_rerenders_with_error_and_leaves_row_unchanged(client):
    _login(client)
    for bad_date in ["13/11/2026", "2026-02-30"]:
        response = client.post(
            _edit_url(EDITED_EXPENSE_ID), data=_valid_payload(date=bad_date)
        )
        body = response.data.decode("utf-8")
        assert response.status_code == 200, f"Date {bad_date!r} must re-render the form"
        assert ERROR_MARKER in body, f"Date {bad_date!r} must show an error message"
        assert _expense_row_count() == SEED_ROW_COUNT, (
            f"Date {bad_date!r} must not change the row count"
        )
        _assert_row_unchanged(EDITED_EXPENSE_ID)


def test_edit_expense_empty_date_is_rejected_and_leaves_row_unchanged(client):
    # Unlike the add form, the edit form has no "today" fallback: the
    # spec makes the date required on edit.
    _login(client)
    response = client.post(_edit_url(EDITED_EXPENSE_ID), data=_valid_payload(date=""))
    body = response.data.decode("utf-8")
    assert response.status_code == 200, "Empty date must re-render the form"
    assert ERROR_MARKER in body, "Empty date must show an error message"
    assert _expense_row_count() == SEED_ROW_COUNT, (
        "Empty date must not change the row count"
    )
    _assert_row_unchanged(EDITED_EXPENSE_ID)


def test_edit_expense_description_over_200_chars_rejected_and_leaves_row_unchanged(client):
    _login(client)
    response = client.post(
        _edit_url(EDITED_EXPENSE_ID), data=_valid_payload(description="x" * 201)
    )
    body = response.data.decode("utf-8")
    assert response.status_code == 200, "A 201-char description must re-render the form"
    assert ERROR_MARKER in body, "A 201-char description must show an error message"
    assert _expense_row_count() == SEED_ROW_COUNT, (
        "A 201-char description must not change the row count"
    )
    _assert_row_unchanged(EDITED_EXPENSE_ID)


def test_edit_expense_description_exactly_200_chars_succeeds(client):
    _login(client)
    description = "x" * 200
    response = client.post(
        _edit_url(EDITED_EXPENSE_ID), data=_valid_payload(description=description)
    )
    assert response.status_code == 302, "A 200-char description must be accepted"
    row = _fetch_expense(EDITED_EXPENSE_ID)
    assert row["description"] == description, (
        "The 200-char description must be stored verbatim"
    )


# ------------------------------------------------------------------ #
# Empty description stores NULL (DoD 10)                              #
# ------------------------------------------------------------------ #


def test_edit_expense_empty_description_succeeds_and_stores_null(client):
    _login(client)
    response = client.post(
        _edit_url(EDITED_EXPENSE_ID), data=_valid_payload(description="")
    )
    assert response.status_code == 302, "Empty description must still succeed"
    row = _fetch_expense(EDITED_EXPENSE_ID)
    assert row["description"] is None, "Empty description must be stored as NULL"


# ------------------------------------------------------------------ #
# Repopulation on validation failure (DoD 8)                          #
# ------------------------------------------------------------------ #


def test_edit_expense_failed_post_keeps_typed_values_and_targets_same_expense(client):
    _login(client)
    response = client.post(
        _edit_url(EDITED_EXPENSE_ID),
        data=_valid_payload(
            amount="abc",
            date="2026-11-10",
            description="Taxi to airport",
        ),
    )
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert ERROR_MARKER in body, "Failed POST must show an error"
    assert _input_value(body, "amount") == "abc", "Typed amount must be kept in the form"
    assert _input_value(body, "date") == "2026-11-10", "Typed date must be kept in the form"
    assert _input_value(body, "description") == "Taxi to airport", (
        "Typed description must be kept in the form"
    )
    assert f'action="{_edit_url(EDITED_EXPENSE_ID)}"' in body, (
        "After a failed POST the form must still target the same expense id"
    )


# ------------------------------------------------------------------ #
# Profile integration (DoD 3)                                         #
# ------------------------------------------------------------------ #


def test_profile_shows_actions_column_with_edit_link_for_each_row(client):
    _login(client)
    body = client.get(PROFILE_URL).data.decode("utf-8")
    assert "<th>Actions</th>" in body, (
        "The profile transactions table must have an Actions column"
    )
    assert _edit_url(EDITED_EXPENSE_ID) in body, (
        "Each row must have an Edit link to its /expenses/<id>/edit URL"
    )
    edit_links = body.count('class="table-action"')
    assert edit_links == SEED_ROW_COUNT, (
        f"Each of the {SEED_ROW_COUNT} rows must have one Edit link, found {edit_links}"
    )


def test_profile_shows_no_edit_links_for_user_with_no_expenses(client):
    _register_and_login(client, name="Empty User", email="empty@spendly.com")
    body = client.get(PROFILE_URL).data.decode("utf-8")
    assert 'class="table-action"' not in body, (
        "A user with no expenses must not see any Edit links"
    )
    assert "/edit" not in body, (
        "A user with no expenses must not see any Edit links"
    )
