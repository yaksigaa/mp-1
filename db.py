"""SQLite database module for FinLens.
Manages users, statements, transactions, and user isolation.
"""
import sqlite3
import json
import os
from typing import Optional, Dict, Any, List
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "finlens.db")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initialize SQLite database tables and indexes."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. Uploaded statements table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS statements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        safe_filename TEXT NOT NULL,
        s3_key TEXT,
        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tx_count INTEGER NOT NULL DEFAULT 0,
        total_spend REAL NOT NULL DEFAULT 0.0,
        date_from TEXT,
        date_to TEXT,
        status TEXT DEFAULT 'processed',
        analysis_json TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # 3. Transactions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        statement_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        description TEXT NOT NULL,
        merchant TEXT NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        FOREIGN KEY (statement_id) REFERENCES statements(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Indexes for fast lookup
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_statements_user ON statements(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_stmt ON transactions(statement_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)")

    conn.commit()
    conn.close()


def create_user(name: str, email: str, password: str) -> Optional[Dict[str, Any]]:
    """Register a new user with secure password hash."""
    name = (name or "").strip()
    email = (email or "").strip().lower()

    if not name or not email or not password:
        raise ValueError("Name, email, and password are required.")

    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters long.")

    pw_hash = generate_password_hash(password)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, pw_hash)
        )
        conn.commit()
        user_id = cursor.lastrowid
        return get_user_by_id(user_id)
    except sqlite3.IntegrityError:
        raise ValueError("An account with this email address already exists.")
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def verify_user_login(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Verify user credentials."""
    user = get_user_by_email(email)
    if not user:
        return None
    if check_password_hash(user["password_hash"], password):
        return {"id": user["id"], "name": user["name"], "email": user["email"]}
    return None


def save_user_statement(user_id: int, filename: str, safe_filename: str, s3_key: str,
                        tx_df, analysis_dict: dict) -> int:
    """Save statement metadata, transactions, and analysis JSON for a specific user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        total_spend = float(tx_df["amount"].sum()) if "amount" in tx_df.columns else 0.0
        date_from = str(tx_df["date"].min())[:10] if "date" in tx_df.columns and len(tx_df) else ""
        date_to = str(tx_df["date"].max())[:10] if "date" in tx_df.columns and len(tx_df) else ""
        tx_count = len(tx_df)

        cursor.execute("""
        INSERT INTO statements (user_id, filename, safe_filename, s3_key, tx_count, total_spend, date_from, date_to, status, analysis_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'processed', ?)
        """, (
            user_id, filename, safe_filename, s3_key, tx_count, round(total_spend, 2),
            date_from, date_to, json.dumps(analysis_dict)
        ))
        statement_id = cursor.lastrowid

        # Insert transactions in bulk
        tx_rows = []
        for _, r in tx_df.iterrows():
            d_str = str(r["date"])[:10]
            desc_str = str(r.get("description", ""))
            merch_str = str(r.get("merchant", desc_str))
            cat_str = str(r.get("category", "Others"))
            amt_val = round(float(r.get("amount", 0.0)), 2)
            tx_rows.append((statement_id, user_id, d_str, desc_str, merch_str, cat_str, amt_val))

        cursor.executemany("""
        INSERT INTO transactions (statement_id, user_id, date, description, merchant, category, amount)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, tx_rows)

        conn.commit()
        return statement_id
    finally:
        conn.close()


def get_user_statements(user_id: int) -> List[Dict[str, Any]]:
    """Retrieve all uploaded statements for a user in reverse chronological order."""
    conn = get_db_connection()
    try:
        rows = conn.execute("""
        SELECT id, filename, s3_key, upload_date, tx_count, total_spend, date_from, date_to, status
        FROM statements
        WHERE user_id = ?
        ORDER BY id DESC
        """, (user_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_statement_by_id(statement_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a statement ensuring it belongs to the given user."""
    conn = get_db_connection()
    try:
        row = conn.execute("""
        SELECT id, filename, s3_key, upload_date, tx_count, total_spend, date_from, date_to, status, analysis_json
        FROM statements
        WHERE id = ? AND user_id = ?
        """, (statement_id, user_id)).fetchone()
        if not row:
            return None
        res = dict(row)
        if res.get("analysis_json"):
            try:
                res["analysis"] = json.loads(res["analysis_json"])
            except Exception:
                res["analysis"] = None
        return res
    finally:
        conn.close()


def get_statement_transactions(statement_id: int, user_id: int) -> List[Dict[str, Any]]:
    """Retrieve transactions for a statement ensuring user ownership."""
    conn = get_db_connection()
    try:
        rows = conn.execute("""
        SELECT id, date, description, merchant, category, amount
        FROM transactions
        WHERE statement_id = ? AND user_id = ?
        ORDER BY date DESC, id DESC
        """, (statement_id, user_id)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_user_all_transactions(user_id: int) -> List[Dict[str, Any]]:
    """Retrieve all transactions across all statements for the given user."""
    conn = get_db_connection()
    try:
        rows = conn.execute("""
        SELECT id, statement_id, date, description, merchant, category, amount
        FROM transactions
        WHERE user_id = ?
        ORDER BY date DESC, id DESC
        """, (user_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_statement_analysis(statement_id: int, user_id: int, analysis: dict) -> bool:
    """Update stored analysis JSON for a user's statement."""
    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE statements SET analysis_json = ? WHERE id = ? AND user_id = ?",
            (json.dumps(analysis), statement_id, user_id)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB Error] update_statement_analysis failed: {e}")
        return False
    finally:
        conn.close()

