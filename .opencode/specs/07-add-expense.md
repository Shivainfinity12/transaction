# Spec: Add Expense

## Overview

Everything in Spendly so far is read-only: Steps 01–06 built the database,
authentication, and a profile dashboard, but the data it displays is only the
seeded demo expenses — no user can record anything of their own. Step 07 turns
on the first write path: a logged-in user can add an expense (amount, category,
date, optional description) through a form page at `/expenses/add`, which is
validated server-side and inserted into the existing `expenses` table with the
session user's `user_id`. This step exists now because it is the foundation the
rest of the expense-management roadmap depends on — Steps 08 (edit) and 09
(delete) operate on rows created here, and the Step 06 filtered profile view is
the place where a newly added expense is verified to exist.

## Depends on

- Step 01 — Database setup (`users` and `expenses` tables, `get_db()` with
  `PRAGMA foreign_keys = ON`, seed data)
- Step 02 — Registration (users exist to own expenses)
- Step 03 — Login and Logout (the `session["user_id"]` auth-guard pattern)
- Step 04/05 — Profile page + backend routes (redirect target after a
  successful add; renders the inserted row)
- Step 06 — Date filter (optional but expected: the filtered profile view is
  the verification surface for this feature)

## Routes

Two routes share the function that currently exists as the `GET /expenses/add`
stub. The stub (raw string return) is replaced entirely.

- `GET /expenses/add` — renders the add-expense form (amount, category, date,
  description) with the date field prefilled with today — logged-in
- `POST /expenses/add` — validates the submitted fields and inserts the new
  expense, then redirects to the profile page on success or re-renders the
  form with an error — logged-in

Both methods are guarded: if `session.get("user_id")` is not set, redirect to
the login page (same manual pattern as `/profile`).

## Database changes

No database changes. Verified against `database/db.py`: the `expenses` table
created in Step 01 already has exactly the columns this feature needs —

- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `user_id` INTEGER NOT NULL (FK → `users.id`, enforced via the
  `PRAGMA foreign_keys = ON` in `get_db()`)
- `amount` REAL NOT NULL
- `category` TEXT NOT NULL
- `date` TEXT NOT NULL (YYYY-MM-DD, lexicographically comparable — matches the
  Step 06 filter helpers)
- `description` TEXT (nullable)
- `created_at` TEXT DEFAULT CURRENT_TIMESTAMP

The only new DB code is an INSERT helper in `database/db.py`. No schema edits,
no migration, no changes to `seed_db()`.

## Templates

- **Create:**
  - `templates/add_expense.html` — the add-expense page: a single form card
    with amount (`type="number"`, step `0.01`), category (a `select` listing
    exactly the seven fixed categories), date (`type="date"`, prefilled with
    today), and an optional description field. Displays a server-passed
    `error` message and repopulates the user's previously entered values when
    validation fails. Loads `css/add_expense.css` via the `head` block.
- **Modify:**
  - `templates/base.html` — inside the logged-in branch of the nav, add an
    "Add Expense" link via `url_for('add_expense')`. Today a logged-in user's
    nav shows only "Logout", so without this change the new page would be
    unreachable through the UI.

## Files to change

- `app.py` — replace the `GET /expenses/add` stub with the real
  `add_expense()` route registered for `methods=["GET", "POST"]` (auth guard,
  server-side validation, calls the insert helper, redirect or re-render)
- `database/db.py` — add a parameterized `add_expense(user_id, amount,
  category, date, description)` insert helper that returns the new row id
- `templates/base.html` — add the logged-in "Add Expense" nav link

## Files to create

- `templates/add_expense.html`
- `static/css/add_expense.css`
- `tests/test_07-add-expense.py`

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`

Specific to this step:

- No blueprints: the route lives in `app.py`; DB logic never appears inline in
  the route — the INSERT belongs in the `database/db.py` helper
- Guard both GET and POST with the existing manual pattern
  (`if not session.get("user_id"): return redirect(url_for("login"))`) — do
  not introduce a decorator and do not touch any other route
- The form's action must use `{{ url_for('add_expense') }}` — do not copy the
  hardcoded `action="/login"` / `action="/register"` pattern from the existing
  auth templates
- Errors follow the codebase's established pattern: pass an `error` string as
  template context (no `flash()` — it is not used anywhere yet)
- Server-side validation rules:
  - amount — required, must parse as a positive number greater than 0; stored
    rounded to 2 decimals
  - category — required, must be exactly one of the fixed Step 01 list: Food,
    Transport, Bills, Health, Entertainment, Shopping, Other
  - date — required, defaults to today, must parse as `YYYY-MM-DD`
  - description — optional, trimmed, at most 200 characters, stored as NULL
    when left empty
- On success redirect to the profile page (`url_for('profile')`) — that is
  where the new row is verified
- Reuse the existing global form classes from `style.css`
  (`.form-group`, `.form-input`, `.btn-submit`, `.auth-card`); the new
  `add_expense.css` only adds page-specific layout and must use the `:root`
  variables (e.g. `--auth-width`, `--radius-md`, `--border`) — same approach as
  `profile-filter.css`
- Do not modify `seed_db()`, the schema, the profile routes or template
  (beyond the one nav line in `base.html`), or any existing tests
- Keep the dev server on port 5001; install no pip packages

## Definition of done

1. `python app.py` starts cleanly on port 5001 with no errors.
2. Logged out, both `GET /expenses/add` and `POST /expenses/add` respond 302
   and redirect to `/login`.
3. Logged in, `GET /expenses/add` responds 200 and shows the form with the
   amount field, a category select containing exactly the 7 fixed categories,
   a date field prefilled with today, and an optional description field.
4. Submitting a valid expense (e.g. 12.50 / Food / today / "Lunch") inserts a
   row in `expenses` with the logged-in user's `user_id`, then redirects to
   `/profile`, where the new expense appears in the transactions list and is
   reflected in the summary stats.
5. Submitting an invalid amount (empty, non-numeric, zero, or negative)
   re-renders the form with an error message and creates no row.
6. Submitting an empty or unknown category, or a malformed date (not
   YYYY-MM-DD), re-renders the form with an error message and creates no row.
7. When validation fails, the form keeps the values the user already typed.
8. Leaving the description empty still succeeds (row stored with a NULL
   description); a description longer than 200 characters is rejected.
9. When logged in, the navbar shows "Add Expense"; when logged out, it does
   not.
10. `pytest tests/test_07-add-expense.py` passes, and the full `pytest` suite
    (including the Step 05 and 06 test files) remains green.
