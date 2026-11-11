"""Step 06 — Date Filter for Profile Page tests.

Spec: .opencode/specs/06-date-filter-for-profile-page.md

Route-level tests exercise GET /profile with the optional query parameters
(range=month/30d/custom plus start/end): the auth guard, the unchanged
All-time baseline, the three filter presets, the empty state, the
invalid-input fallback, and the filter UI (prefill, summary line, clear
link). Helper-level tests call the three database/queries.py helpers with
explicit start_date/end_date strings against the seeded temp database.

Expected values come from the spec and the seed fixture data (the 8 expenses
seeded by database/db.py, dates 2026-11-01..2026-11-08 — hardcoded here, the
same practice as tests/test_backend_connection.py; never read from a live
database). The `month` and `30d` presets are relative to the day the tests
run, so those tests compute the expected window themselves and derive every
expectation from the hardcoded seed dates.

Run with: pytest tests/test_06-date-filter-for-profile-page.py
"""

import calendar
import re
from datetime import date, timedelta

import pytest

from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

DEMO_CREDENTIALS = {"email": "demo@spendly.com", "password": "demo123"}

# Fixture data: the 8 seeded expenses (user_id=1) as
# (date, category, amount, description), mirroring seed_db().
SEED_EXPENSES = (
    ("2026-11-01", "Food", 12.50, "Lunch at cafeteria"),
    ("2026-11-02", "Transport", 8.75, "Bus fare"),
    ("2026-11-03", "Bills", 45.00, "Electricity bill"),
    ("2026-11-04", "Health", 35.00, "Dental cleaning"),
    ("2026-11-05", "Entertainment", 25.00, "Movie tickets"),
    ("2026-11-06", "Shopping", 45.99, "New boots"),
    ("2026-11-07", "Other", 15.00, "Library fines"),
    ("2026-11-08", "Food", 22.30, "Groceries"),
)
SEED_DATES = frozenset(row[0] for row in SEED_EXPENSES)
SEED_BY_DATE = {row[0]: row[1:] for row in SEED_EXPENSES}
SEED_TOTAL = 209.54  # sum of the 8 seed amounts

# Spec DoD 6: the custom window 2026-11-01..2026-11-03 contains exactly the
# three seed rows dated inside it — ₹66.25 total, top category "Bills".
CUSTOM_WINDOW = ("2026-11-01", "2026-11-03")


# ------------------------------------------------------------------ #
# Fixtures & helpers                                                  #
# ------------------------------------------------------------------ #


def _login(client, credentials=DEMO_CREDENTIALS):
    """Post demo credentials to /login."""
    return client.post("/login", data=credentials)


def _stat_values(body):
    """Contents of the profile page's summary stat cells, in page order."""
    return [
        text.strip()
        for text in re.findall(
            r'<div class="stat-value">(.*?)</div>', body, re.DOTALL
        )
    ]


def _rendered_iso_dates(body):
    """Every YYYY-MM-DD date string rendered anywhere on the page."""
    return set(re.findall(r"\d{4}-\d{2}-\d{2}", body))


def _category_names(body):
    """Category labels rendered in category-name elements."""
    names = []
    for match in re.finditer(
        r'class="[^"]*category-name[^"]*"[^>]*>(.*?)</', body, re.DOTALL
    ):
        text = re.sub(r"<[^>]+>", " ", match.group(1))
        name = " ".join(text.split())
        if name:
            names.append(name)
    return names


def _selected_preset_value(body):
    """Value of the currently selected option in the filter preset select."""
    select_match = re.search(
        r"<select\b[^>]*>.*?</select>", body, re.IGNORECASE | re.DOTALL
    )
    assert select_match is not None, "filter preset <select> not found on the page"
    for option_match in re.finditer(
        r"<option\b([^>]*)>([^<]*)", select_match.group(0), re.IGNORECASE
    ):
        attrs = option_match.group(1)
        if re.search(r"\bselected\b", attrs, re.IGNORECASE):
            value_match = re.search(r'value\s*=\s*"([^"]*)"', attrs, re.IGNORECASE)
            if value_match:
                return value_match.group(1)
            return option_match.group(2).strip()
    return None


def _clear_filter_href(body):
    """href of the 'Clear filter' link, or None when the link is absent."""
    for anchor_match in re.finditer(
        r"<a\b([^>]*)>(.*?)</a>", body, re.IGNORECASE | re.DOTALL
    ):
        label = " ".join(re.sub(r"<[^>]+>", " ", anchor_match.group(2)).split())
        if label == "Clear filter":
            href_match = re.search(
                r'href\s*=\s*"([^"]*)"', anchor_match.group(1), re.IGNORECASE
            )
            if href_match:
                return href_match.group(1)
    return None


def _current_month_window():
    """Inclusive YYYY-MM-DD bounds of the current calendar month (spec)."""
    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return (
        today.replace(day=1).isoformat(),
        date(today.year, today.month, last_day).isoformat(),
    )


def _last_30_days_window():
    """Inclusive YYYY-MM-DD bounds of the last 30 days (spec: today-29..today)."""
    today = date.today()
    return (today - timedelta(days=29)).isoformat(), today.isoformat()


def _seed_rows_in_window(window_start, window_end):
    """Seed fixture rows whose date falls inside the inclusive window."""
    return [row for row in SEED_EXPENSES if window_start <= row[0] <= window_end]


def _expected_top_category(rows):
    """Top category by summed amount for the given seed rows, or '—'."""
    if not rows:
        return "—"
    totals = {}
    for _, category, amount, _ in rows:
        totals[category] = totals.get(category, 0.0) + amount
    best = max(totals.values())
    winners = [name for name, total in totals.items() if total == best]
    assert len(winners) == 1, f"ambiguous top category in test fixture: {winners}"
    return winners[0]


def _assert_filtered_dashboard(body, window_start, window_end, expected_rows, preset):
    """Assert the three dashboard sections agree on the filtered period.

    Every expectation is derived from the hardcoded seed fixture rows that
    fall inside [window_start, window_end]: the stats, the transaction list
    and the category breakdown must all describe the same period.
    """
    expected_dates = {row[0] for row in expected_rows}
    expected_categories = {row[1] for row in expected_rows}
    expected_total = sum(row[2] for row in expected_rows)

    # 1) Summary stats describe the filtered period.
    stats = _stat_values(body)
    assert f"₹{expected_total:.2f}" in stats
    assert str(len(expected_rows)) in stats
    assert _expected_top_category(expected_rows) in stats

    # 2) Transactions section: every expected seed date is rendered, and no
    #    date outside the window leaks in.
    found_dates = _rendered_iso_dates(body)
    assert expected_dates <= found_dates
    for found_date in found_dates:
        assert window_start <= found_date <= window_end, (
            f"{found_date} rendered outside the filtered window "
            f"{window_start}..{window_end}"
        )

    # 3) Category breakdown covers exactly the in-window categories.
    assert set(_category_names(body)) == expected_categories

    if not expected_rows:
        # Empty period: empty-state message instead of transactions.
        assert re.search(r"no expenses found", body, re.IGNORECASE)
        assert not (found_dates & SEED_DATES)

    # The filter UI reflects the active selection.
    assert "Clear filter" in body
    assert "Showing" in body
    assert _selected_preset_value(body) == preset
    if preset == "custom":
        assert f'value="{window_start}"' in body
        assert f'value="{window_end}"' in body


def _assert_baseline(body):
    """The unfiltered All time view: seeded stats and all 8 transactions."""
    stats = _stat_values(body)
    assert "₹209.54" in stats
    assert "8" in stats
    assert "Shopping" in stats
    assert SEED_DATES <= _rendered_iso_dates(body)


# ------------------------------------------------------------------ #
# Route tests: GET /profile — auth guard                              #
# ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?range=month",
        "?range=custom&start=2026-11-01&end=2026-11-03",
    ],
    ids=["no-params", "month-preset", "custom-range"],
)
def test_profile_redirects_to_login_when_logged_out(client, query):
    """Spec DoD 2 — /profile is logged-in only, with or without a filter."""
    response = client.get("/profile" + query)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


# ------------------------------------------------------------------ #
# Route tests: baseline (All time) is unchanged                       #
# ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    "query", ["", "?range=all"], ids=["no-params", "explicit-all"]
)
def test_profile_without_active_filter_renders_baseline(client, query):
    """Spec DoD 3 — without an active filter the page renders as before."""
    _login(client)
    response = client.get("/profile" + query)
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    _assert_baseline(body)

    # All 8 seed transactions, still newest first.
    assert body.index("2026-11-08") < body.index("2026-11-01")

    # Nothing is filtered, so no active-filter UI markers appear.
    assert "Clear filter" not in body
    assert "Showing" not in body


def test_profile_filter_bar_structure_on_all_time(client):
    """Spec DoD 9 / Templates — the filter form exists on the unfiltered page."""
    _login(client)
    body = client.get("/profile").data.decode("utf-8")

    assert re.search(r"<form\b[^>]*method=[\"']get[\"']", body, re.IGNORECASE)
    assert 'action="/profile"' in body  # url_for('profile'), never hardcoded
    assert 'name="range"' in body
    assert 'name="start"' in body
    assert 'name="end"' in body
    assert body.count('type="date"') >= 2
    for preset_label in ("All time", "This month", "Last 30 days", "Custom range"):
        assert preset_label in body
    assert "Apply" in body

    # All time is the default, so no active-filter markers yet.
    assert "Clear filter" not in body
    assert "Showing" not in body


# ------------------------------------------------------------------ #
# Route tests: happy paths for every filter mode                      #
# ------------------------------------------------------------------ #


def test_profile_range_month_shows_current_month_rows(client):
    """Spec DoD 4 — range=month restricts the whole dashboard to the current month."""
    _login(client)
    window_start, window_end = _current_month_window()
    expected_rows = _seed_rows_in_window(window_start, window_end)

    response = client.get("/profile?range=month")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    _assert_filtered_dashboard(
        body, window_start, window_end, expected_rows, "month"
    )


def test_profile_range_30d_shows_last_30_days_rows(client):
    """Spec DoD 5 — range=30d restricts the dashboard to today-29..today."""
    _login(client)
    window_start, window_end = _last_30_days_window()
    expected_rows = _seed_rows_in_window(window_start, window_end)

    response = client.get("/profile?range=30d")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    _assert_filtered_dashboard(
        body, window_start, window_end, expected_rows, "30d"
    )


def test_profile_custom_range_nov_1_to_3_shows_three_transactions(client):
    """Spec DoD 6 — custom 2026-11-01..2026-11-03: 3 transactions, ₹66.25, Bills."""
    _login(client)
    window_start, window_end = CUSTOM_WINDOW
    expected_rows = _seed_rows_in_window(window_start, window_end)
    assert len(expected_rows) == 3  # fixture sanity: 3 seed dates in window

    response = client.get("/profile?range=custom&start=2026-11-01&end=2026-11-03")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    _assert_filtered_dashboard(
        body, window_start, window_end, expected_rows, "custom"
    )

    # Spec DoD 6 numbers, pinned explicitly.
    stats = _stat_values(body)
    assert "₹66.25" in stats
    assert "3" in stats
    assert "Bills" in stats

    # Exactly the three seed dates inside the window are rendered.
    assert _rendered_iso_dates(body) == {row[0] for row in expected_rows}


# ------------------------------------------------------------------ #
# Route tests: empty period                                           #
# ------------------------------------------------------------------ #


def test_profile_custom_range_outside_seed_shows_empty_state(client):
    """Spec DoD 7 — a range with no seed data shows the empty state, no crash."""
    _login(client)
    response = client.get("/profile?range=custom&start=2026-10-01&end=2026-10-31")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    _assert_filtered_dashboard(body, "2026-10-01", "2026-10-31", [], "custom")

    # Spec DoD 7 numbers, pinned explicitly (helpers' empty-data contract).
    stats = _stat_values(body)
    assert "₹0.00" in stats
    assert "0" in stats
    assert "—" in stats
    assert _category_names(body) == []


# ------------------------------------------------------------------ #
# Route tests: validation / malformed input                           #
# ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    "query",
    [
        "?range=custom&start=oops",
        "?range=custom&end=2026-11-03",
        "?range=custom&start=2026-11-05&end=2026-11-01",
        "?range=bogus",
    ],
    ids=["malformed-start", "missing-start", "inverted-range", "unknown-range"],
)
def test_malformed_filter_falls_back_to_all_time(client, query):
    """Spec DoD 8 — invalid filter input normalises to All time, never a 500."""
    _login(client)
    response = client.get("/profile" + query)
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    _assert_baseline(body)

    # The fallback is the All time view, so no active-filter markers.
    assert "Clear filter" not in body
    assert "Showing" not in body
    assert 'name="range"' in body  # filter bar itself is still rendered

    # The form state matches the data: the select falls back to All time
    # (code-review Q1 — invalid custom ranges must not leave "custom"
    # selected over All time data).
    assert _selected_preset_value(body) == "all"


# ------------------------------------------------------------------ #
# Route tests: filter UI behaviour                                    #
# ------------------------------------------------------------------ #


def test_profile_form_prefills_active_custom_selection(client):
    """Spec DoD 9 — the form is prefilled with the active custom range."""
    _login(client)
    body = client.get(
        "/profile?range=custom&start=2026-11-01&end=2026-11-03"
    ).data.decode("utf-8")

    assert 'name="start"' in body
    assert 'name="end"' in body
    assert 'value="2026-11-01"' in body
    assert 'value="2026-11-03"' in body
    assert _selected_preset_value(body) == "custom"
    assert "Showing" in body
    assert "Clear filter" in body


def test_clear_filter_link_returns_to_all_time_view(client):
    """Spec DoD 9 — 'Clear filter' leads back to the unfiltered All time view."""
    _login(client)
    filtered_body = client.get("/profile?range=month").data.decode("utf-8")
    href = _clear_filter_href(filtered_body)
    assert href is not None, "'Clear filter' link not found while filtering"

    response = client.get(href)
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    _assert_baseline(body)
    assert "Clear filter" not in body
    assert "Showing" not in body


def test_custom_range_url_still_renders_user_card(client):
    """Spec — the filtered /profile still renders the user info card unchanged."""
    _login(client)
    response = client.get("/profile?range=custom&start=2026-11-01&end=2026-11-03")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Demo User" in body
    assert "demo@spendly.com" in body


# ------------------------------------------------------------------ #
# Helper tests: database/queries.py with explicit date bounds          #
# ------------------------------------------------------------------ #


def test_db_summary_stats_filtered_to_nov_1_to_3(seeded_db):
    """Spec (queries.py contract) — stats restricted to an explicit window."""
    stats = get_summary_stats(
        1, start_date=CUSTOM_WINDOW[0], end_date=CUSTOM_WINDOW[1]
    )
    assert stats["total_spent"] == pytest.approx(66.25)
    assert stats["transaction_count"] == 3
    assert stats["top_category"] == "Bills"


def test_db_recent_transactions_filtered_to_nov_1_to_3(seeded_db):
    """Spec — filtered transactions are exactly the seed rows in the window."""
    rows = get_recent_transactions(
        1, start_date=CUSTOM_WINDOW[0], end_date=CUSTOM_WINDOW[1]
    )
    assert [row["date"] for row in rows] == [
        "2026-11-03",
        "2026-11-02",
        "2026-11-01",
    ]
    assert sum(row["amount"] for row in rows) == pytest.approx(66.25)
    for row in rows:
        assert set(row) == {"date", "description", "category", "amount"}
        category, amount, description = SEED_BY_DATE[row["date"]]
        assert row["category"] == category
        assert row["amount"] == pytest.approx(amount)
        assert row["description"] == description


def test_db_category_breakdown_filtered_to_nov_1_to_3(seeded_db):
    """Spec — breakdown percentages are computed within the filtered period."""
    breakdown = get_category_breakdown(
        1, start_date=CUSTOM_WINDOW[0], end_date=CUSTOM_WINDOW[1]
    )
    assert [item["name"] for item in breakdown] == ["Bills", "Food", "Transport"]
    assert [item["amount"] for item in breakdown] == pytest.approx(
        [45.00, 12.50, 8.75]
    )
    for item in breakdown:
        assert isinstance(item["pct"], int)
    assert sum(item["pct"] for item in breakdown) == 100


def test_db_filtered_helpers_return_empty_contracts_for_october(seeded_db):
    """Spec — an empty filtered period keeps the helpers' empty-data contract."""
    assert get_summary_stats(1, start_date="2026-10-01", end_date="2026-10-31") == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }
    assert (
        get_recent_transactions(1, start_date="2026-10-01", end_date="2026-10-31")
        == []
    )
    assert (
        get_category_breakdown(1, start_date="2026-10-01", end_date="2026-10-31")
        == []
    )


def test_db_bounds_are_inclusive_on_both_ends(seeded_db):
    """Spec — start/end bounds are inclusive (`date >= ? AND date <= ?`)."""
    stats = get_summary_stats(1, start_date="2026-11-01", end_date="2026-11-01")
    assert stats["total_spent"] == pytest.approx(12.50)
    assert stats["transaction_count"] == 1
    assert stats["top_category"] == "Food"

    rows = get_recent_transactions(
        1, start_date="2026-11-01", end_date="2026-11-01"
    )
    assert [row["date"] for row in rows] == ["2026-11-01"]

    # The full seed span matches the unfiltered (All time) numbers.
    stats = get_summary_stats(1, start_date="2026-11-01", end_date="2026-11-08")
    assert stats["total_spent"] == pytest.approx(SEED_TOTAL)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Shopping"


def test_db_helpers_apply_one_sided_bounds_independently(seeded_db):
    """Spec — each bound adds its own conditional clause when not None."""
    stats = get_summary_stats(1, end_date="2026-11-04")
    assert stats["total_spent"] == pytest.approx(101.25)
    assert stats["transaction_count"] == 4
    assert stats["top_category"] == "Bills"

    stats = get_summary_stats(1, start_date="2026-11-07")
    assert stats["total_spent"] == pytest.approx(37.30)
    assert stats["transaction_count"] == 2
    assert stats["top_category"] == "Food"

    rows = get_recent_transactions(1, start_date="2026-11-07")
    assert [row["date"] for row in rows] == ["2026-11-08", "2026-11-07"]

    breakdown = get_category_breakdown(1, end_date="2026-11-04")
    assert len(breakdown) == 4
    assert breakdown[0]["name"] == "Bills"
