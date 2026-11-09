import sqlite3

db = sqlite3.connect("spendly.db")
print("Tables:", db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())

# Check users table schema
users_schema = db.execute("PRAGMA table_info(users)").fetchall()
print("Users schema:", users_schema)

# Check expenses table schema
expenses_schema = db.execute("PRAGMA table_info(expenses)").fetchall()
print("Expenses schema:", expenses_schema)

# Check data
user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
print("User count:", user_count)

expense_count = db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
print("Expense count:", expense_count)

# Check demo user
demo = db.execute("SELECT * FROM users WHERE email='demo@spendly.com'").fetchone()
print("Demo user:", dict(demo) if demo else None)

# Check expenses categories
categories = db.execute("SELECT DISTINCT category FROM expenses").fetchall()
print("Categories:", [c[0] for c in categories])

db.close()