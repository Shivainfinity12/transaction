# Spec: Date Filter for Profile Page

## Overview

After Step 5 the profile page always shows lifetime data: the summary stats,
recent transactions, and category breakdown are computed over every expense
the user has ever recorded. Step 06 adds a date-range filter to the profile
page so the user can focus the whole dashboard on a period — All time, This
month, Last 30 days, or a Custom range with start/end dates. The filter is
implemented as GET query parameters on the existing `/profile` route and is
applied server-side, so all three dashboard sections (stats, transactions,
breakdown) stay consistent with each other. This matters now because the
upcoming expense-management steps (07–09) will need a filtered view to verify
add/edit/delete results, and because lifetime-only totals become less useful
as the user's history grows.

## Depends on

- Step 01 — Database setup (`database/db.py`, `users` and `expenses` tables, seed data)
- Step 02 — Registration (a logged-in user exists to own expenses)
- Step 03 — Login and Logout (session guard for `/profile`)
- Step 04 — Profile page design (`templates/profile.html`)
- Step 05 — Backend routes for profile page (`database/queries.py` helpers)

## Routes

No new routes.

Modified route:

- `GET /profile` — already exists and renders `profile.html`; gains **optional**
  query parameters. Access level: logged-in only (unchanged).
  - `range` — one of `all` (default), `month`, `30d`, `custom`
  - `start`, `end` — dates in strict `YYYY-MM-DD`, used only when `range=custom`
  - Semantics (inclusive bounds, computed server-side in app.py):
    - `all` → no date restriction (identical to current behaviour)
    - `month` → first day of the current month through the last day of the current month
    - `30d` → today minus 29 days through today
    - `custom` → `start` through `end` as given
  - Invalid input never crashes the page: unknown `range` values, malformed or
    missing `start`/`end`, or `start > end` all fall back to **All time**
    (input normalisation, not an HTTP error — do not `abort()` here).

## Database changes

No database changes.

- `expenses.date` is already `TEXT NOT NULL` in strict `YYYY-MM-DD` format
  (Step 01), so `WHERE date >= ? AND date <= ?` comparisons are correct
  lexicographically.
- `seed_db()` is intentionally left untouched so existing tests keep their
  expected values (8 seed expenses, ₹209.54 total, top category "Shopping").
  Note for testing: the seed data only spans 2026-11-01 to 2026-11-08, so
  custom ranges outside November 2026 exercise the empty state.

## Templates

- **Create:** none.
- **Modify:**
  - `templates/profile.html`
    - Add a filter bar between the user info card and the stats row:
      a `<form method="get" action="{{ url_for('profile') }}">` containing
      a preset `<select>` (All time / This month / Last 30 days / Custom range),
      `start` and `end` `<input type="date">` fields, and an Apply button.
    - Add a "Clear filter" link to `{{ url_for('profile') }}` shown only when
      a filter is active.
    - Prefill the form from the currently active filter values passed by the
      route (`range`, `start`, `end`).
    - Show a one-line summary of the active period (e.g. "Showing: Nov 1, 2026 – Nov 3, 2026").
    - Add an empty-state message inside the transactions table section when
      the filtered result is empty (e.g. "No expenses found for this period").
    - Include the new page stylesheet via the existing `{% block head %}`:
      `{% block head %}<link rel="stylesheet" href="{{ url_for('static', filename='css/profile-filter.css') }}">{% endblock %}`.

## Files to change

- `app.py` — the `profile()` route reads `request.args`, resolves the filter,
  passes optional date bounds to the three query helpers, and passes the
  active filter values to the template. Add a small module-level helper
  `resolve_date_range(range_key, start_raw, end_raw)` returning
  `(start_date, end_date)` as `YYYY-MM-DD` strings or `(None, None)` for
  All time; route functions stay one-responsibility (fetch data, render).
- `database/queries.py` — extend the three profile helpers with optional
  date bounds, **backward-compatible defaults** so existing behaviour and
  tests are unchanged:
  - `get_recent_transactions(user_id, limit=10, start_date=None, end_date=None)`
  - `get_summary_stats(user_id, start_date=None, end_date=None)`
  - `get_category_breakdown(user_id, start_date=None, end_date=None)`
  Each adds conditional `AND date >= ?` / `AND date <= ?` clauses with `?`
  placeholders when the bound is not `None`. Empty filtered results keep the
  module's existing empty-data contract (zeros / `[]` / `"—"`, never exceptions).
- `templates/profile.html` — as listed under Templates.

## Files to create

- `static/css/profile-filter.css` — styles for the filter bar and empty-state
  message. Loaded only by `profile.html` through `base.html`'s `head` block.
  Use CSS variables from `style.css`; no hardcoded hex values, no inline
  `<style>` tags.

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs — raw sqlite3 via `get_db()` only.
- Parameterised queries only — `?` placeholders for every value, never f-strings in SQL.
- Passwords hashed with werkzeug (no password logic in this step, but the rule stands).
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html` — the filter UI lives inside `profile.html`'s `content` block.
- Do not add new routes, blueprints, or tables; extend `GET /profile` only.
- Do not modify `seed_db()`, the table schemas, or any existing test's expectations —
  new helper parameters must default to `None` so current call sites behave identically.
- Validate dates with `datetime.strptime(value, "%Y-%m-%d")`; on any
  `ValueError`, missing value, or inverted range, fall back to All time —
  never raise and never render a raw error string.
- Filtering is form-driven (GET submission) and requires no JavaScript;
  if any JS is added it must be vanilla and belong in `static/js/main.js` —
  no frameworks, no npm packages.
- Use `url_for()` for the form action and the Clear-filter link — never hardcode URLs.
- The app runs on port 5001 — do not change it.

## Definition of done

Run the app with `python app.py` (port 5001) and verify, using the seeded
demo account (`demo@spendly.com` / `demo123`):

1. `python app.py` starts without errors on port 5001; `pytest` passes with
   no modifications to existing tests.
2. Logged out, `GET /profile` redirects to the login page.
3. Logged in, `/profile` with no query params renders exactly as before the
   feature: 8 transactions, Total Spent ₹209.54, Top Category "Shopping".
4. `/profile?range=month` shows only current-month (November 2026) expenses —
   all 8 with current seed data — and stats/breakdown match the filtered rows.
5. `/profile?range=30d` shows only expenses from the last 30 days up to and
   including today (all 8 seed rows fall in this window as of the seed dates).
6. `/profile?range=custom&start=2026-11-01&end=2026-11-03` shows exactly
   3 transactions with Total Spent ₹66.25 and Top Category "Bills".
7. `/profile?range=custom&start=2026-10-01&end=2026-10-31` shows the empty
   state in the transactions section, Total Spent ₹0.00, 0 Transactions, and
   the helpers' existing empty-data behaviour for Top Category ("—") and
   breakdown (no crash).
8. Malformed input — `/profile?range=custom&start=oops`,
   `/profile?range=custom&end=2026-11-03` (missing start),
   and `/profile?range=custom&start=2026-11-05&end=2026-11-01` (inverted) —
   each falls back to the All time view with no 500 error.
9. The filter form is prefilled with the active selection, the active period
   summary line is shown while filtering, and "Clear filter" returns the page
   to the All time view.
10. `static/css/profile-filter.css` is the only new stylesheet, is linked via
    the `head` block, uses CSS variables, and no `<style>` tag is added to any template.
11. `git diff` shows no changes to `database/db.py`, `requirements.txt`, or existing tests.
