import calendar
import math
from datetime import date, datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
# insert_expense is database.db.add_expense, aliased because the route
# function below is itself named add_expense.
from database.db import add_expense as insert_expense
from database.db import get_db, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    get_user_name,
)

app = Flask(__name__)
app.secret_key = 'spendly-secret-key-change-in-production'


# ------------------------------------------------------------------ #
# Template globals (navbar avatar — Step 07)                          #
# ------------------------------------------------------------------ #

@app.context_processor
def inject_avatar_initial():
    """Expose the logged-in user's initial to every template.

    base.html renders it inside the navbar avatar that links to the
    profile page. Logged-out renders pass nothing (no avatar shown).
    """
    if not session.get("user_id"):
        return {}
    name = get_user_name(session["user_id"])
    initial = name.strip()[:1].upper() if name and name.strip() else "?"
    return {"avatar_initial": initial}


# ------------------------------------------------------------------ #
# Date filter helpers (profile page — Step 06)                        #
# ------------------------------------------------------------------ #

# (query-param value, human label) for every preset the filter supports.
# Single source of truth for both the form's <select> options and the
# set of keys _resolve_date_range understands.
DATE_PRESETS = (
    ("all", "All time"),
    ("month", "This month"),
    ("30d", "Last 30 days"),
    ("custom", "Custom range"),
)


def _resolve_date_range(range_key, start_raw, end_raw):
    """Resolve the profile date filter into inclusive YYYY-MM-DD bounds.

    Returns (start_date, end_date) as strings, or (None, None) for
    All time. Presets are computed against today's date; custom bounds
    must both parse as YYYY-MM-DD and satisfy start <= end. Invalid
    input never raises — it falls back to All time.
    """
    if range_key == "month":
        today = date.today()
        month_start = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        month_end = month_start.replace(day=last_day)
        return month_start.isoformat(), month_end.isoformat()

    if range_key == "30d":
        today = date.today()
        return (today - timedelta(days=29)).isoformat(), today.isoformat()

    if range_key == "custom":
        try:
            start = datetime.strptime(start_raw or "", "%Y-%m-%d").date()
            end = datetime.strptime(end_raw or "", "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None, None
        if start > end:
            return None, None
        return start.isoformat(), end.isoformat()

    return None, None


def _format_date_label(date_str):
    """Format a YYYY-MM-DD string as a short label, e.g. "Nov 1, 2026"."""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %d, %Y")


# ------------------------------------------------------------------ #
# Add expense (Step 07)                                               #
# ------------------------------------------------------------------ #

# Fixed expense categories from Step 01 — the add-expense form's
# <select> options and the POST validation whitelist share this list.
EXPENSE_CATEGORIES = ["Food", "Transport", "Bills", "Health",
                      "Entertainment", "Shopping", "Other"]


def _render_add_expense(error=None, amount_value="", category_value="Food",
                        date_value=None, description_value=""):
    """Render the add-expense form, prefilled with the given values.

    GET passes no values (date defaults to today); POST re-renders pass
    back whatever the user submitted so the form keeps their input.
    """
    return render_template(
        "add_expense.html",
        categories=EXPENSE_CATEGORIES,
        error=error,
        amount_value=amount_value,
        category_value=category_value,
        date_value=date_value or date.today().isoformat(),
        description_value=description_value,
    )


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("landing"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        # Validate inputs
        if not name or not email or not password:
            return render_template("register.html", error="All fields are required")

        if len(password) < 8:
            return render_template("register.html", error="Password must be at least 8 characters")

        # Check for duplicate email
        db = get_db()
        existing = db.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        db.close()

        if existing:
            return render_template("register.html", error="Email already registered")

        # Hash password and create user
        from werkzeug.security import generate_password_hash
        password_hash = generate_password_hash(password)

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, password_hash),
            )
            db.commit()
        except Exception:
            db.rollback()
            db.close()
            return render_template("register.html", error="Registration failed. Please try again.")
        finally:
            db.close()

        return redirect(url_for('login'))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("landing"))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not email or not password:
            return render_template("login.html", error="All fields are required")

        db = get_db()
        user = db.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
        db.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            return redirect(url_for("landing"))
        else:
            return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # Date filter — resolved from GET params; invalid input falls back
    # to All time, so the page never errors on bad query strings.
    range_key = request.args.get("range", "all")
    start_date, end_date = _resolve_date_range(
        range_key, request.args.get("start"), request.args.get("end")
    )
    # _resolve_date_range returns both bounds or neither.
    filter_active = start_date is not None
    if not filter_active:
        # Invalid input was normalised to the All time view — reflect
        # that in the form so the select never contradicts the data.
        range_key = "all"

    # User info card — query helpers live in database/queries.py
    user = get_user_by_id(user_id)

    expenses = get_recent_transactions(
        user_id, start_date=start_date, end_date=end_date
    )

    stats = get_summary_stats(user_id, start_date=start_date, end_date=end_date)
    total_spent = stats["total_spent"]
    transaction_count = stats["transaction_count"]
    top_category = stats["top_category"]

    category_breakdown = get_category_breakdown(
        user_id, start_date=start_date, end_date=end_date
    )

    # Human-readable label for the active period (both bounds are set
    # whenever the filter is active).
    filter_label = None
    if filter_active:
        filter_label = (
            f"{_format_date_label(start_date)} – {_format_date_label(end_date)}"
        )

    return render_template(
        "profile.html",
        user=user,
        expenses=expenses,
        total_spent=total_spent,
        transaction_count=transaction_count,
        top_category=top_category,
        category_breakdown=category_breakdown,
        filter_range=range_key,
        filter_start=start_date,
        filter_end=end_date,
        filter_active=filter_active,
        filter_label=filter_label,
        date_presets=DATE_PRESETS,
    )


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]

    if request.method == "POST":
        amount_raw = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        date_raw = request.form.get("date", "").strip()
        description_raw = request.form.get("description", "").strip()

        # Amount — parsed and rounded to 2 decimals, and the rounded
        # value must still be positive (rejects "0", "-5", "abc" and
        # sub-cent inputs like "0.001" that round to nothing).
        try:
            amount = round(float(amount_raw), 2)
        except ValueError:
            amount = None
        if amount is None or not math.isfinite(amount) or amount <= 0:
            return _render_add_expense(
                error="Amount must be a positive number",
                amount_value=amount_raw,
                category_value=category,
                date_value=date_raw,
                description_value=description_raw,
            )

        # Category — must be exactly one of the fixed list.
        if category not in EXPENSE_CATEGORIES:
            return _render_add_expense(
                error="Please choose a valid category",
                amount_value=amount_raw,
                category_value=category,
                date_value=date_raw,
                description_value=description_raw,
            )

        # Date — empty means today; anything else must parse as YYYY-MM-DD.
        if date_raw:
            try:
                expense_date = datetime.strptime(date_raw, "%Y-%m-%d").date().isoformat()
            except ValueError:
                return _render_add_expense(
                    error="Date must be in YYYY-MM-DD format",
                    amount_value=amount_raw,
                    category_value=category,
                    date_value=date_raw,
                    description_value=description_raw,
                )
        else:
            expense_date = date.today().isoformat()

        # Description — optional; empty becomes a real NULL in the DB.
        if len(description_raw) > 200:
            return _render_add_expense(
                error="Description must be 200 characters or fewer",
                amount_value=amount_raw,
                category_value=category,
                date_value=date_raw,
                description_value=description_raw,
            )
        description = description_raw or None

        insert_expense(user_id, amount, category, expense_date, description)
        return redirect(url_for("profile"))

    return _render_add_expense(date_value=date.today().isoformat())


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


with app.app_context():
    init_db()
    seed_db()


if __name__ == "__main__":
    app.run(debug=True, port=5001)
