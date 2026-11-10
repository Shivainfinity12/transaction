# Spec: Login and Logout

## Overview

Implement user authentication functionality for Spendly, enabling registered users to log in and log out. This step builds on the existing registration system (Step 2) by adding the ability to authenticate existing users and manage their session state. The login route will verify credentials against the database, and the logout route will terminate the user's session. This is a prerequisite for subsequent steps like profile management and protected routes.

## Depends on

Step 2 — Registration — the `users` table with `password_hash` column must exist and contain user data before login can authenticate against it.

## Routes

- `GET /login` — renders the login form — public
- `POST /login` — authenticates user credentials and logs in — public (redirects to logged-in state)
- `GET /logout` — logs out the current user and redirects to landing — logged-in

No new routes — `/register` already exists from Step 2.

## Database changes

No database changes — the `users` table already exists with the required columns (`id`, `name`, `email`, `password_hash`, `created_at`) and the `email` UNIQUE constraint. Authentication will verify the provided password against the stored `password_hash` using parameterised queries.

## Templates

- **Create:** No new templates needed — `login.html` already exists and extends `base.html`.
- **Modify:** No existing templates require modifications for this step.

## Files to change

- `app.py` — update `/login` route to handle POST requests and authenticate users; update `/logout` route to properly log out the user

## Files to create

No new files will be created.

## New dependencies

No new pip packages — the feature uses existing Flask, SQLite, and werkzeug dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs — use parameterised queries only
- Passwords must be verified with werkzeug's `check_password_hash` against the stored `password_hash`
- All templates must extend `base.html`
- Use CSS variables — never hardcode hex values
- Validate form input on the server side using parameterised queries
- Implement login required protection for routes that need authentication
- After successful login, user session should be tracked (note: SQLite does not server-side sessions; implement manual tracking via a user_id approach or Flask session)

## Definition of done

- [ ] `POST /login` route authenticates user by verifying email and password against the `users` table
- [ ] Successful login results in the user being logged in (session/user_id tracked)
- [ ] `/logout` route logs out the current user and redirects to the landing page
- [ ] Duplicate login attempts with wrong credentials show an appropriate error message
- [ ] Login template extends `base.html` and uses consistent styling
- [ ] No raw SQL strings — all queries use `?` placeholders
- [ ] Passwords are verified (not stored or compared as plain text)