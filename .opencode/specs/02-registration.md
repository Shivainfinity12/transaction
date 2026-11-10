# Spec: Registration

## Overview

Implement user registration functionality for Spendly, allowing new users to create accounts with name, email, and password. This feature provides the foundational authentication capability required for subsequent steps like login, logout, and profile management. The registration route and user database table already exist, but this step ensures the full flow is complete with proper validation, password hashing, and template integration.

## Depends on

No previous steps required — this feature builds on the existing database schema and can be implemented independently. Subsequent steps (login, logout, profile) will depend on registration being complete.

## Routes

No new routes — `/register` and `/login` already exist and are implemented.

## Database changes

No database changes — the `users` table already exists with the required columns (`id`, `name`, `email`, `password_hash`, `created_at`). The `email` column has a UNIQUE constraint already defined.

## Templates

- **Create:** No new templates needed — `register.html` already exists and extends `base.html`.
- **Modify:** No existing templates require modifications for this step.

## Files to change

No files will be modified.

## Files to create

No new files will be created.

## New dependencies

No new dependencies — the feature uses existing Flask, SQLite, and werkzeug dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs — use parameterised queries only
- Passwords must be hashed with werkzeug's `generate_password_hash` and verified with `check_password_hash`
- All templates must extend `base.html`
- Use CSS variables — never hardcode hex values
- Validate form input on the server side using parameterised queries

## Definition of done

- [ ] Registration form submits successfully to `/register` route
- [ ] New user is inserted into the `users` table with a hashed password
- [ ] Duplicate email registration is prevented (UNIQUE constraint enforced)
- [ ] Successful registration redirects or shows confirmation
- [ ] Registration template extends `base.html` and uses consistent styling
- [ ] No raw SQL strings — all queries use `?` placeholders