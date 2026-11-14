import sqlite3
from werkzeug.security import generate_password_hash


def get_db():
    """Open a connection to spendly.db with row_factory and foreign keys enabled."""
    db = sqlite3.connect("spendly.db")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db():
    """Create both tables using CREATE TABLE IF NOT EXISTS. Safe to call multiple times."""
    db = get_db()
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        db.commit()
    finally:
        db.close()


def seed_db():
    """Insert demo user and 8 sample expenses if data already exists (idempotent)."""
    db = get_db()
    try:
        # Check if users table already has data
        existing = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if existing > 0:
            return  # already seeded

        # Insert demo user with hashed password
        password_hash = generate_password_hash("demo123")
        db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", password_hash),
        )
        db.commit()

        # Insert 8 sample expenses linked to demo user (user_id=1)
        # Categories: Food, Transport, Bills, Health, Entertainment, Shopping, Other
        # At least one expense per category, dates spread across current month
        expenses = [
            ("Food", 12.50, "2026-11-01", "Lunch at cafeteria"),
            ("Transport", 8.75, "2026-11-02", "Bus fare"),
            ("Bills", 45.00, "2026-11-03", "Electricity bill"),
            ("Health", 35.00, "2026-11-04", "Dental cleaning"),
            ("Entertainment", 25.00, "2026-11-05", "Movie tickets"),
            ("Shopping", 45.99, "2026-11-06", "New boots"),
            ("Other", 15.00, "2026-11-07", "Library fines"),
            ("Food", 22.30, "2026-11-08", "Groceries"),
        ]
        for category, amount, date, description in expenses:
            db.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
                (1, amount, category, date, description),
            )
        db.commit()
    finally:
        db.close()


def add_expense(user_id, amount, category, date, description):
    """Insert a new expense for user_id and return the new row id.

    date must be a YYYY-MM-DD string; description may be None (stored as NULL).
    """
    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
        )
        db.commit()
        return cursor.lastrowid
    finally:
        db.close()


def get_expense_by_id(expense_id, user_id):
    """Return the expense row with expense_id owned by user_id, or None.

    Scoped by both id and user_id: a row that does not exist, or that
    belongs to a different user, returns None — callers turn that into
    a 404 without revealing whether the row exists for someone else.
    """
    db = get_db()
    try:
        return db.execute(
            "SELECT id, user_id, amount, category, date, description "
            "FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
    finally:
        db.close()


def update_expense(expense_id, user_id, amount, category, date, description):
    """Update an expense owned by user_id; return the number of rows updated.

    Mirrors add_expense(): amount is a float rounded to 2 decimals, date
    a YYYY-MM-DD string, description may be None (stored as NULL). A
    return of 0 means the row was missing or not owned by user_id.
    """
    db = get_db()
    try:
        cursor = db.execute(
            "UPDATE expenses SET amount = ?, category = ?, date = ?, description = ? "
            "WHERE id = ? AND user_id = ?",
            (amount, category, date, description, expense_id, user_id),
        )
        db.commit()
        return cursor.rowcount
    finally:
        db.close()


def delete_expense(expense_id, user_id):
    """Delete an expense owned by user_id; return the number of rows deleted.

    Mirrors update_expense(): the DELETE is scoped by both id and
    user_id, so a row that does not exist, or that belongs to a
    different user, leaves rowcount at 0 — callers turn that into a
    404 without revealing whether the row exists for someone else.
    """
    db = get_db()
    try:
        cursor = db.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        db.commit()
        return cursor.rowcount
    finally:
        db.close()
