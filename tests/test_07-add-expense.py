"""Step 7 — Add Expense tests.

Route tests cover GET/POST /expenses/add (auth guard, form rendering,
server-side validation, DB inserts) against the seeded temp database from
conftest's seeded_db/client fixtures.

Baseline (seed data): demo user id=1 owns 8 expenses totalling 209.54.
Expected values follow the ACTUAL seed data, not the spec's example numbers
where they differ.

Known implementation bug at time of writing: app.py references
math.isfinite() without importing math, so any POST whose amount parses
(e.g. "12.50", "0", "-5") currently 500s. These tests encode the spec;
add `import math` to app.py to make the success-path tests pass.
"""

import database.db as database_db
from datetime import date

DEMO_CREDENTIALS = {"email": "demo@spendly.com", "password": "demo123"}

SEED_ROW_COUNT = 8
SEED_TOTAL = 209.54
NEW_EXPENSE_AMOUNT = 12.50

FIXED_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

# The error div rendered by add_expense.html when validation fails.
ERROR_MARKER = "auth-error"

ADD_EXPENSE_URL = "/expenses/add"
PROFILE_URL = "/profile"
LOGIN_URL = "/login"


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #


def _login(client, credentials=DEMO_CREDENTIALS):
    return client.post("/login", data=credentials)


def _expense_row_count():
    """Total rows in the expenses table (routed to the patched temp DB)."""
    db = database_db.get_db()
    try:
        return db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        db.close()


def _latest_expense_row():
    """The most recently inserted expense row as a plain dict."""
    db = database_db.get_db()
    try:
        row = db.execute(
            "SELECT user_id, amount, category, date, description "
            "FROM expenses ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def _valid_payload(**overrides):
    """A valid add-expense POST body, overridable per test."""
    payload = {
        "amount": "12.50",
        "category": "Food",
        "date": date.today().isoformat(),
        "description": "Team lunch after demo",
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #


def test_add_expense_get_redirects_to_login_when_logged_out(client):
    response = client.get(ADD_EXPENSE_URL)
    assert response.status_code == 302, "Logged-out GET must redirect"
    assert response.headers["Location"].endswith(LOGIN_URL)


def test_add_expense_post_redirects_to_login_when_logged_out_and_inserts_nothing(client):
    response = client.post(ADD_EXPENSE_URL, data=_valid_payload())
    assert response.status_code == 302, "Logged-out POST must redirect"
    assert response.headers["Location"].endswith(LOGIN_URL)
    assert _expense_row_count() == SEED_ROW_COUNT, "Logged-out POST must not insert a row"


# ------------------------------------------------------------------ #
# Form rendering (logged in)                                          #
# ------------------------------------------------------------------ #


def test_add_expense_get_logged_in_shows_form_with_amount_date_and_description(client):
    _login(client)
    response = client.get(ADD_EXPENSE_URL)
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert 'name="amount"' in body, "Amount input missing"
    assert 'name="date"' in body, "Date input missing"
    assert 'name="description"' in body, "Optional description input missing"
    assert "(optional)" in body, "Description should be marked optional"


def test_add_expense_get_logged_in_prefills_date_with_today(client):
    _login(client)
    body = client.get(ADD_EXPENSE_URL).data.decode("utf-8")
    assert f'value="{date.today().isoformat()}"' in body, (
        "Date field must be prefilled with today's date"
    )


def test_add_expense_get_logged_in_category_select_has_exactly_seven_fixed_categories(client):
    _login(client)
    body = client.get(ADD_EXPENSE_URL).data.decode("utf-8")
    for category in FIXED_CATEGORIES:
        assert f'value="{category}"' in body, f"Category {category!r} missing from select"
    assert body.count("<option") == len(FIXED_CATEGORIES), (
        "Category select must offer exactly the 7 fixed categories"
    )


# ------------------------------------------------------------------ #
# Happy path                                                          #
# ------------------------------------------------------------------ #


def test_add_expense_valid_post_inserts_row_for_logged_in_user_and_redirects_to_profile(client):
    _login(client)
    response = client.post(ADD_EXPENSE_URL, data=_valid_payload())
    assert response.status_code == 302, "Valid POST must redirect on success"
    assert response.headers["Location"].endswith(PROFILE_URL)

    assert _expense_row_count() == SEED_ROW_COUNT + 1, "Exactly one row should be added"
    row = _latest_expense_row()
    assert row["user_id"] == 1, "Row must belong to the logged-in demo user"
    assert row["amount"] == NEW_EXPENSE_AMOUNT
    assert row["category"] == "Food"
    assert row["date"] == date.today().isoformat()
    assert row["description"] == "Team lunch after demo"


def test_add_expense_valid_post_appears_on_profile_with_updated_stats(client):
    _login(client)
    client.post(ADD_EXPENSE_URL, data=_valid_payload())
    body = client.get(PROFILE_URL).data.decode("utf-8")
    assert "₹222.04" in body, f"Total should be {SEED_TOTAL} + {NEW_EXPENSE_AMOUNT} = 222.04"
    assert '<div class="stat-value">9</div>' in body, "Transaction count should be 9"
    assert "Team lunch after demo" in body, "New expense should be in the transactions list"


def test_add_expense_amount_rounded_to_two_decimals(client):
    _login(client)
    response = client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(amount="12.999", category="Transport"),
    )
    assert response.status_code == 302, "Rounding a valid amount must still succeed"
    row = _latest_expense_row()
    assert row["amount"] == 13.0, "12.999 must be stored rounded to 13.0"


# ------------------------------------------------------------------ #
# Validation errors: amount                                           #
# ------------------------------------------------------------------ #


def test_add_expense_invalid_amount_rerenders_with_error_and_inserts_nothing(client):
    _login(client)
    for amount in ["", "abc", "0", "-5", "0.001"]:
        response = client.post(ADD_EXPENSE_URL, data=_valid_payload(amount=amount))
        body = response.data.decode("utf-8")
        assert response.status_code == 200, f"Amount {amount!r} must re-render the form"
        assert ERROR_MARKER in body, f"Amount {amount!r} must show an error message"
        assert _expense_row_count() == SEED_ROW_COUNT, (
            f"Amount {amount!r} must not insert a row"
        )


# ------------------------------------------------------------------ #
# Validation errors: category                                         #
# ------------------------------------------------------------------ #


def test_add_expense_invalid_category_rerenders_with_error_and_inserts_nothing(client):
    _login(client)
    for category in ["", "Lifestyle"]:
        response = client.post(ADD_EXPENSE_URL, data=_valid_payload(category=category))
        body = response.data.decode("utf-8")
        assert response.status_code == 200, f"Category {category!r} must re-render the form"
        assert ERROR_MARKER in body, f"Category {category!r} must show an error message"
        assert _expense_row_count() == SEED_ROW_COUNT, (
            f"Category {category!r} must not insert a row"
        )


# ------------------------------------------------------------------ #
# Validation errors: date                                             #
# ------------------------------------------------------------------ #


def test_add_expense_malformed_date_rerenders_with_error_and_inserts_nothing(client):
    _login(client)
    for bad_date in ["13/11/2026", "2026-02-30"]:
        response = client.post(ADD_EXPENSE_URL, data=_valid_payload(date=bad_date))
        body = response.data.decode("utf-8")
        assert response.status_code == 200, f"Date {bad_date!r} must re-render the form"
        assert ERROR_MARKER in body, f"Date {bad_date!r} must show an error message"
        assert _expense_row_count() == SEED_ROW_COUNT, (
            f"Date {bad_date!r} must not insert a row"
        )


def test_add_expense_empty_date_defaults_to_today_in_stored_row(client):
    _login(client)
    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(date=""))
    assert response.status_code == 302, "Empty date must default to today, not fail"
    row = _latest_expense_row()
    assert row["date"] == date.today().isoformat(), "Empty date must be stored as today"


# ------------------------------------------------------------------ #
# Validation: description                                             #
# ------------------------------------------------------------------ #


def test_add_expense_empty_description_succeeds_and_stores_null(client):
    _login(client)
    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(description=""))
    assert response.status_code == 302, "Empty description must still succeed"
    row = _latest_expense_row()
    assert row["description"] is None, "Empty description must be stored as NULL"


def test_add_expense_description_exactly_200_chars_succeeds(client):
    _login(client)
    description = "x" * 200
    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(description=description))
    assert response.status_code == 302, "A 200-char description must be accepted"
    row = _latest_expense_row()
    assert row["description"] == description, "The 200-char description must be stored verbatim"


def test_add_expense_description_over_200_chars_rejected_and_inserts_nothing(client):
    _login(client)
    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(description="x" * 201))
    body = response.data.decode("utf-8")
    assert response.status_code == 200, "A 201-char description must re-render the form"
    assert ERROR_MARKER in body, "A 201-char description must show an error message"
    assert _expense_row_count() == SEED_ROW_COUNT, "A 201-char description must not insert a row"


# ------------------------------------------------------------------ #
# Repopulation on validation failure                                  #
# ------------------------------------------------------------------ #


def test_add_expense_failed_post_keeps_user_typed_values(client):
    _login(client)
    response = client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(
            amount="abc",
            date="2026-11-10",
            description="Taxi to airport",
        ),
    )
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert ERROR_MARKER in body, "Failed POST must show an error"
    assert 'value="abc"' in body, "Typed amount must be kept in the form"
    assert 'value="Taxi to airport"' in body, "Typed description must be kept in the form"
    assert 'value="2026-11-10"' in body, "Typed date must be kept in the form"


# ------------------------------------------------------------------ #
# Navbar link                                                         #
# ------------------------------------------------------------------ #


def test_nav_shows_add_expense_link_when_logged_in_only(client):
    logged_out_body = client.get(LOGIN_URL).data.decode("utf-8")
    assert "Add Expense" not in logged_out_body, "Logged-out nav must not show Add Expense"

    _login(client)
    logged_in_body = client.get(ADD_EXPENSE_URL).data.decode("utf-8")
    assert "Add Expense" in logged_in_body, "Logged-in nav must show Add Expense"
    assert 'href="/expenses/add"' in logged_in_body, (
        "Add Expense nav link must point to /expenses/add"
    )


# ------------------------------------------------------------------ #
# Navbar avatar (context processor)                                   #
# ------------------------------------------------------------------ #


def _register_and_login(client, name, email, password="password123"):
    """Register a fresh user through the real POST /register, then log in."""
    client.post("/register", data={"name": name, "email": email, "password": password})
    return client.post("/login", data={"email": email, "password": password})


def test_nav_avatar_absent_when_logged_out(client):
    for url in ["/", LOGIN_URL, "/register"]:
        response = client.get(url)
        body = response.data.decode("utf-8")
        assert response.status_code == 200, f"Logged-out GET {url} must not error"
        assert "nav-avatar" not in body, (
            f"Logged-out page {url} must not contain a nav-avatar element"
        )


def test_nav_avatar_shows_uppercased_initial_for_demo_user(client):
    _login(client)
    body = client.get(PROFILE_URL).data.decode("utf-8")
    assert 'class="nav-avatar"' in body, "Logged-in nav must show the avatar"
    assert ">D</a>" in body, "Demo User's avatar must show initial 'D'"
    assert body.count("nav-avatar") == 1, "Exactly one avatar element per page"


def test_nav_avatar_links_to_profile_page(client):
    _login(client)
    body = client.get(PROFILE_URL).data.decode("utf-8")
    assert 'href="/profile"' in body, "Avatar must link to /profile"
    assert 'title="Your profile"' in body, "Avatar must have a profile tooltip"
    assert 'aria-label="Go to your profile"' in body, "Avatar must be accessible"


def test_nav_avatar_present_on_home_and_add_expense_pages(client):
    _login(client)
    for url in ["/", ADD_EXPENSE_URL]:
        body = client.get(url).data.decode("utf-8")
        assert 'class="nav-avatar"' in body, f"Avatar must appear on {url} too"
        assert ">D</a>" in body, f"Avatar on {url} must show Demo User's initial 'D'"


def test_nav_avatar_single_character_name_becomes_initial(client):
    _register_and_login(client, name="Q", email="single@spendly.com")
    body = client.get(PROFILE_URL).data.decode("utf-8")
    assert 'class="nav-avatar"' in body, "Fresh user must see the avatar"
    assert ">Q</a>" in body, "Single-character name 'Q' must render as initial 'Q'"


def test_nav_avatar_strips_leading_whitespace_from_name(client):
    _register_and_login(client, name="  Ivy", email="ivy@spendly.com")
    body = client.get(PROFILE_URL).data.decode("utf-8")
    assert 'class="nav-avatar"' in body, "Fresh user must see the avatar"
    assert ">I</a>" in body, "Name '  Ivy' must render initial 'I' after stripping"
    assert "> </a>" not in body, "Whitespace must never become the initial"
