from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = 'spendly-secret-key-change-in-production'


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
    db = get_db()
    user = db.execute(
        "SELECT name, email, created_at FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    db.close()
    expenses = [
        {"date": "2026-11-01", "description": "Lunch at cafeteria", "category": "Food", "amount": 12.50},
        {"date": "2026-11-03", "description": "Electricity bill", "category": "Bills", "amount": 45.00},
        {"date": "2026-11-05", "description": "Movie tickets", "category": "Entertainment", "amount": 25.00},
    ]
    category_totals = {"Food": 37.80, "Bills": 45.00, "Entertainment": 25.00, "Other": 15.00}
    top_category = max(category_totals, key=category_totals.get)
    return render_template(
        "profile.html",
        user=user,
        expenses=expenses,
        total_spent=87.50,
        transaction_count=len(expenses),
        top_category=top_category,
        category_breakdown=sorted(
            [{"category": cat, "total": total} for cat, total in category_totals.items()],
            key=lambda x: x["total"],
            reverse=True,
        ),
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


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
