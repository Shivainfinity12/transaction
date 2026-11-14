# Spec: Edit Expense

## Overview

After Step 07, a logged-in user can create expenses, but any mistake — a typo
in the amount, a wrong category, a misdated entry — is permanent: the profile
table is display-only and there is no way to correct a row. Step 08 adds the
first update path: each row in the profile's Recent Transactions table gets an
Edit link to `/expenses/<id>/edit`, which renders a form prefilled with that
expense's current values and, on submit, validates them with exactly the same
rules as the add form and rewrites the row in the existing `expenses` table.
This step exists now because it directly extends Step 07's write path with the
"fix what you typed" flow, and it prepares the ownership + 404 handling that
Step 09 (delete) will reuse for the second per-row action.

## Depends on

- Step 01 — Database setup (`expenses` table with `id`, `user_id`, `amount`,
  `category`, `date`, `description`; `get_db()` with `PRAGMA foreign_keys = ON`)
- Step 03 — Login and Logout (the `session["user_id"]` auth-guard pattern)
- Step 05/06 — Profile page + backend routes (the transactions table this
  feature links from; redirect target after a successful edit)
- Step 07 — Add Expense (the form markup, validation rules and
  `EXPENSE_CATEGORIES` list this feature mirrors; the row being edited is
  typically one created here)

## Routes

The existing `GET /expenses/<int:id>/edit` stub in `app.py` (raw string return)
is replaced entirely by one route function registered for both methods:

- `GET /expenses/<int:id>/edit` — looks up the expense scoped to the logged-in
  user (`WHERE id = ? AND user_id = ?`); renders the edit form prefilled with
  its current amount, category, date and description — logged-in
- `POST /expenses/<int:id>/edit` — validates the submitted fields with the
  Step 07 rules, runs the parameterized UPDATE, and redirects to the profile
  page on success or re-renders the form with an error — logged-in

Guard both methods with the existing manual pattern
(`if not session.get("user_id"): return redirect(url_for("login"))`). When the
expense id does not exist, or exists but belongs to a different user, respond
with `abort(404)` — never expose other users' rows. `app.py` does not import
`abort` yet, so the import list from `flask` must be extended.

## Database changes

No database changes. Verified against `database/db.py`: the `expenses` table
created in Step 01 already holds every field the edit form needs, and an
UPDATE requires no schema edits, no migration, and no changes to `seed_db()`.

The only new DB code is two helpers in `database/db.py` (AGENTS.md rule: DB
logic never inline in routes):

- `get_expense_by_id(expense_id, user_id)` — parameterized SELECT on
  `expenses` scoped by both `id` and `user_id`; returns the row (sqlite3.Row
  or dict) or `None` when missing or not owned by `user_id`
- `update_expense(expense_id, user_id, amount, category, date, description)`
  — parameterized `UPDATE ... WHERE id = ? AND user_id = ?`; `description`
  may be `None` (stored as NULL), mirroring `add_expense()`

Additionally, `database/queries.py` needs one change so the Edit link can be
built: `get_recent_transactions()` currently selects only `date, description,
category, amount` — add `id` to the SELECT and to each returned dict. Adding a
key is backward compatible with the Step 06 filter bounds, the summary/breakdown
helpers and the existing tests.

## Templates

- **Create:**
  - `templates/edit_expense.html` — the edit-expense page: the same form card
    structure and classes as `add_expense.html` (`auth-section`,
    `auth-container`, `auth-card`, `form-row`, `form-group`, `form-input`,
    `btn-submit`, `auth-error`, `auth-switch`), with heading "Edit expense"
    and a "Save changes" submit button. Every field is prefilled from the
    fetched expense; on a failed POST it instead repopulates the user's
    submitted values and shows the server-passed `error`. The form action is
    `{{ url_for('edit_expense', id=expense.id) }}` — never a hardcoded URL.
    Loads `css/add_expense.css` via the `head` block — the markup is identical
    to the add page, so no new stylesheet is created (no inline `<style>`
    tags either).
- **Modify:**
  - `templates/profile.html` — the Recent Transactions table gets an Actions
    column: a new `<th>` after Amount and, per row, an Edit link built with
    `url_for('edit_expense', id=expense.id)`. Without this, the edit page is
    unreachable through the UI.
  - `static/css/style.css` — one small `.table-action` rule beside the
    `.profile-table` styles (colors from `:root` variables only) so the
    per-row Edit link matches the design system. (Planning addition — a bare
    link inside the table had no styling.)

`base.html` needs no changes — edit is reached from the profile table, not the
nav.

## Files to change

- `app.py` — replace the `edit_expense()` stub with the real GET/POST route
  (auth guard, `get_expense_by_id` lookup + `abort(404)`, server-side
  validation, calls the update helper, redirect or re-render); extend the
  `flask` import with `abort`; follow the `_render_add_expense()` pattern with
  a small `_render_edit_expense()` helper that receives the expense id and the
  prefill values
- `database/db.py` — add `get_expense_by_id()` and `update_expense()`
  helpers (parameterized, own connection per call, closed before returning —
  same style as `add_expense()`)
- `database/queries.py` — include `id` in the `get_recent_transactions()`
  SELECT and in each returned dict
- `templates/profile.html` — add the Actions column with per-row Edit link
- `static/css/style.css` — add the `.table-action` link rule (variables only)
- `tests/test_backend_connection.py` and
  `tests/test_06-date-filter-for-profile-page.py` — update the two exact
  key-set assertions to include `"id"` (the agreed resolution, Option A, of
  the test-contract conflict found during planning: the old assertions
  contradicted the `get_recent_transactions()` key addition)

## Files to create

- `templates/edit_expense.html`
- `tests/test_08-edit-expense.py`

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`

Specific to this step:

- No blueprints: the route lives in `app.py`; the SELECT and UPDATE belong in
  the `database/db.py` helpers — no SQL inline in the route
- Both helpers scope by `id` AND `user_id`; a row that is missing or owned by
  someone else is `abort(404)`, not a flash or a bare string return
- Do not introduce a decorator for the auth guard and do not touch any other
  route or the `delete_expense` stub (that is Step 09)
- Validation rules are exactly the Step 07 ones, applied on POST:
  - amount — required, must parse as a finite number > 0, stored rounded to
    2 decimals
  - category — required, must be exactly one of `EXPENSE_CATEGORIES` (Food,
    Transport, Bills, Health, Entertainment, Shopping, Other)
  - date — required, must parse as `YYYY-MM-DD`
  - description — optional, trimmed, at most 200 characters, stored as NULL
    when left empty
- Errors follow the established pattern: pass an `error` string as template
  context (no `flash()`), and re-render with the values the user submitted
- On success redirect to `url_for('profile')` — that is where the updated row
  is verified
- The form action must use `{{ url_for('edit_expense', id=expense.id) }}`; all
  other internal links keep using `url_for()`
- Do not modify `seed_db()`, the schema, or the add-expense route/template.
  Existing tests change only in the two exact key-set assertions noted above
  (now expecting `"id"` as well) — the `get_recent_transactions()` key
  addition must leave the Step 05/06/07 suites green
- Keep the dev server on port 5001; install no pip packages

## Definition of done

1. `python app.py` starts cleanly on port 5001 with no errors.
2. Logged out, both `GET /expenses/<id>/edit` and `POST /expenses/<id>/edit`
   respond 302 and redirect to `/login`.
3. Logged in, the profile table shows an Actions column with an Edit link on
   every row.
4. Following the Edit link renders the form prefilled with that expense's
   exact current values (amount, category, date, description).
5. Submitting unchanged values succeeds and returns to `/profile` with the row
   intact.
6. Changing a field (e.g. amount 12.50 → 13.00, or a new description) updates
   the row: the profile table reflects the change and the DB row matches.
7. Submitting an invalid amount (empty, non-numeric, zero, negative),
   an unknown category, or a malformed date re-renders the form with an error
   message and leaves the stored row unchanged.
8. When validation fails, the form keeps the values the user submitted.
9. Editing a nonexistent id, or another user's expense id, responds 404 — the
   DB is not modified in either case.
10. Empty description on submit stores NULL; a description longer than 200
    characters is rejected.
11. `pytest tests/test_08-edit-expense.py` passes, and the full `pytest` suite
    (including the Step 05, 06 and 07 test files) remains green.
