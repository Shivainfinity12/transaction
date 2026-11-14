# Spec: Delete Expense

## Overview

Step 09 completes the expense CRUD cycle that Spendly has been building toward: expenses can be created (Step 07), read and filtered on the profile page (Steps 05–06), and updated (Step 08) — but there is still no way to remove an entry. Today `/expenses/<int:id>/delete` is a raw-string stub that returns `"Delete expense — coming in Step 9"`. This step replaces that stub with a real delete flow: a new `delete_expense()` helper in `database/db.py`, a GET confirmation page so a click on "Delete" never destroys data instantly, and a POST action that permanently removes the row after re-checking ownership. A Delete action link is added next to Edit in the profile table's Actions column, reusing the `expense.id` field that Step 08 exposed in recent transactions. Because deletion is permanent (no soft delete, no undo), the confirmation page is the safety net against accidental clicks, and ownership checks ensure a user can only ever delete their own expenses.

## Depends on

- **Step 01 — Database setup**: the `expenses` table exists; `get_db()` runs `PRAGMA foreign_keys = ON`.
- **Step 03 — Login and logout**: session-based auth; `session["user_id"]` is available and the manual guard pattern is established.
- **Steps 04–06 — Profile page, backend, date filter**: `profile.html` is the only expense list; the Recent Transactions table is where the Delete entry point lives.
- **Step 07 — Add expense**: establishes the GET-renders-form / POST-mutates route convention and the `auth-section`/`auth-card` template structure.
- **Step 08 — Edit expense**: provides `get_expense_by_id(expense_id, user_id)` (ownership lookup + 404), the per-row Actions column, and `expense.id` in recent transactions — all reused directly here.

## Routes

- `GET /expenses/<int:id>/delete` — replaces the stub; renders a confirmation page summarising the expense (date, description, category, amount) with a "Delete expense" confirm button and a "Cancel" link back to the profile — **logged-in**
- `POST /expenses/<int:id>/delete` — deletes the expense row permanently and redirects to the profile — **logged-in**

Both routes require an authenticated session. Unauthenticated requests redirect to `url_for("login")`. A missing expense id, or an id belonging to another user, is a `404` on both routes — never reveal another user's rows.

> Note: `GET` renders only — the mutation happens on `POST` only. This mirrors the add (Step 07) and edit (Step 08) convention and prevents destructive actions from firing on a plain link load. AGENTS.md's route-table row (which lists only `GET`) is updated in this step to reflect the pair.

## Database changes

No database changes. The `expenses` table from Step 01 already holds everything needed, and deletion is a row removal — no soft-delete column, no new constraints.

One new helper (DB logic lives in `database/db.py`, never inline in routes):

- `delete_expense(expense_id, user_id)` — parameterised `DELETE FROM expenses WHERE id = ? AND user_id = ?`; returns `cursor.rowcount`. Structure mirrors `update_expense()` (own connection via `get_db()`, commit, close in `finally`).
- Do **not** touch `init_db()` or `seed_db()` — the seed dataset (8 demo expenses) is depended on by earlier test suites.

## Templates

**Create:**

- `templates/delete_expense.html` — confirmation page extending `base.html`, using the same `auth-section`/`auth-card`/`form-group` structure as `edit_expense.html` (loads `static/css/add_expense.css`, exactly as the edit page does). Shows the expense's date, description, category and amount, a form POSTing to `url_for('delete_expense', id=expense_id)` with a danger-styled confirm button, and a "Cancel" link back to `url_for('profile')`.

**Modify:**

- `templates/profile.html` — in the Recent Transactions Actions column, add a Delete link next to the existing Edit link: `<a href="{{ url_for('delete_expense', id=expense.id) }}" class="table-action table-action-danger">Delete</a>`.

## Files to change

- `app.py` — replace the `delete_expense(id)` stub with `GET`/`POST` routes following the `edit_expense` pattern: manual session guard → ownership lookup via `get_expense_by_id(id, user_id)` → `abort(404)` when absent → POST calls the DB helper and, if `rowcount == 0` (row vanished concurrently), `abort(404)` → redirect to `url_for("profile")`. Import the helper with an alias to avoid clashing with the route function name, following the existing aliasing style in the imports.
- `database/db.py` — add the `delete_expense(expense_id, user_id)` helper described above.
- `templates/profile.html` — add the Delete link in the Actions column.
- `static/css/style.css` — add `.table-action-danger` (red per-row action) and a danger confirm-button class for the confirmation page, built **only** from the existing `--danger` / `--danger-light` variables. Update the `.table-action` comment that says Delete "will reuse this in Step 09".
- `AGENTS.md` — update the route-table row for `/expenses/<id>/delete` from "Stub — Step 9" to "Implemented".

## Files to create

- `templates/delete_expense.html`
- `tests/test_09-delete-expense.py` — pytest file using the existing `tests/conftest.py` fixtures (`seeded_db`, `client`).

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py` only — the route calls `delete_expense(expense_id, user_id)`; no inline SQL in `app.py`
- Manual session guard (`if not session.get("user_id"): return redirect(url_for("login"))`) — do not introduce a decorator
- Ownership check before any deletion: `get_expense_by_id(id, user_id)` returning `None` means `abort(404)`; this holds on GET and POST alike
- `GET` renders only; state is mutated exclusively on `POST`
- `rowcount == 0` after the DELETE on POST → `abort(404)` (handles stale/concurrent deletes)
- Use `url_for()` for every internal link and form action — never hardcode URLs
- Error handling uses `abort()`, never bare string returns
- Reuse existing UI primitives: `auth-section`/`auth-card`/`form-group`, `.table-action`, `.btn-*`; style the delete button only with existing CSS variables
- Do not touch any other route, `init_db()`, `seed_db()`, or `requirements.txt`
- The app keeps running on port 5001 — do not change it

## Definition of done

1. `GET /expenses/<int:id>/delete` while logged out redirects to `/login` — the confirmation page is never visible unauthenticated.
2. Logged in, visiting `GET /expenses/<id>/delete` for one of your own expenses shows a confirmation page displaying that expense's date, description, category and amount, with a confirm (delete) button and a Cancel link back to the profile.
3. `GET` on a nonexistent expense id returns `404`; `GET` on another user's expense id also returns `404` (ownership enforced).
4. `GET` alone never deletes anything — after visiting the confirmation page and then going "Back" to `/profile`, the expense is still listed.
5. Submitting the confirmation form (`POST`) removes the expense from the database and redirects to `/profile`.
6. After deletion, the expense no longer appears in the profile table for the logged-in user, and the profile summary numbers reflect its removal.
7. `POST` on a nonexistent id or another user's id returns `404` and deletes nothing.
8. `POST` for an expense already deleted returns `404` rather than crashing (stale-delete safety).
9. The profile table's Actions column shows both Edit and Delete links for each row, built with `url_for('edit_expense', ...)` and `url_for('delete_expense', ...)`.
10. The Delete link/action styles come from CSS variables (`--danger`, `--danger-light`) — no hardcoded hex values introduced.
11. `pytest` passes, including the new `tests/test_09-delete-expense.py`, without modifying `seed_db()` or earlier test suites.
12. The app still starts with `python app.py` on port 5001 and the raw-string stub text no longer appears anywhere.
