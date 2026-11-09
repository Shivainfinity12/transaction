import sqlite3

db = sqlite3.connect("spendly.db")
db.row_factory = sqlite3.Row
db.execute("PRAGMA foreign_keys = ON")

# Test 1: Basic table without AUTOINCREMENT and without datetime default
db.execute("CREATE TABLE IF NOT EXISTS users_basic (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
db.commit()
print("Test 1 passed: basic table")

# Test 2: With AUTOINCREMENT but no datetime
db.execute("CREATE TABLE IF NOT EXISTS users_autoincrement (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)")
db.commit()
print("Test 2 passed: AUTOINCREMENT table")

# Test 3: With AUTOINCREMENT and datetime default using double quotes for the whole string
db.execute("CREATE TABLE IF NOT EXISTS users_full (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT DEFAULT datetime('now'))")
db.commit()
print("Test 3 passed: full table")

# Verify tables
cur = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", cur.fetchall())

db.close()