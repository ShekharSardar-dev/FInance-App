import sqlite3
from datetime import date

DB_NAME = "finance.db"


def get_connection():
    """Opens a connection to our SQLite database file.
    SQLite stores everything in a single file — no server to install or run."""
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")  # enforce relationships between tables
    return conn


def init_db():
    """Creates all tables if they don't already exist. Safe to call every time
    the app starts — it won't wipe existing data."""
    conn = get_connection()
    cur = conn.cursor()

    # Bank, Cash, or any other "place" money lives.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            balance REAL NOT NULL DEFAULT 0
        )
    """)

    # Every income/expense entry. account_id links to which account it affected.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            sub_category TEXT,
            note TEXT,
            date TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """)

    # Recurring items like SIPs and subscriptions, used to remind you and
    # auto-tag matching transactions.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recurring_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            due_day INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """)

    # Money lent to or borrowed from someone.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_name TEXT NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('lent', 'borrowed')),
            amount REAL NOT NULL,
            remaining_amount REAL NOT NULL,
            reason TEXT,
            account_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            settled INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """)

    # Partial repayments against a loan, so we can track the running balance.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS loan_repayments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            account_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (loan_id) REFERENCES loans(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """)

    # Manually tracked investments.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            amount_invested REAL NOT NULL,
            current_value REAL NOT NULL,
            date_added TEXT NOT NULL
        )
    """)

    # Monthly spending limit per category.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL UNIQUE,
            monthly_limit REAL NOT NULL
        )
    """)

    conn.commit()
    conn.close()

# ---------------------------------------------------------------------
# ACCOUNTS
# ---------------------------------------------------------------------

def add_account(name, starting_balance=0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO accounts (name, balance) VALUES (?, ?)",
        (name, starting_balance),
    )
    conn.commit()
    conn.close()


def get_accounts():
    """Returns a list of (id, name, balance) tuples for every account."""
    conn = get_connection()
    rows = conn.execute("SELECT id, name, balance FROM accounts").fetchall()
    conn.close()
    return rows


def get_account_balance(account_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT balance FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def _adjust_account_balance(conn, account_id, delta):
    """Internal helper: changes an account's balance by `delta`
    (positive to add money, negative to subtract). Takes an existing
    connection so it can be part of a larger transaction."""
    conn.execute(
        "UPDATE accounts SET balance = balance + ? WHERE id = ?",
        (delta, account_id),
    )


# ---------------------------------------------------------------------
# TRANSACTIONS
# ---------------------------------------------------------------------

def add_transaction(account_id, type_, amount, category, note="", sub_category=None, txn_date=None):
    """Records an income/expense AND updates the account balance to match,
    in one go, so the two never drift out of sync."""
    txn_date = txn_date or date.today().isoformat()
    conn = get_connection()

    conn.execute(
        """INSERT INTO transactions (account_id, type, amount, category, sub_category, note, date)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (account_id, type_, amount, category, sub_category, note, txn_date),
    )

    # Income increases the account balance, expense decreases it.
    delta = amount if type_ == "income" else -amount
    _adjust_account_balance(conn, account_id, delta)

    conn.commit()
    conn.close()


def get_transactions(limit=None):
    """Returns recent transactions, newest first, joined with account name
    so we don't have to look it up separately for display."""
    conn = get_connection()
    query = """
        SELECT t.id, t.type, t.amount, t.category, t.sub_category, t.note, t.date, a.name
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        ORDER BY t.date DESC, t.id DESC
    """
    if limit:
        query += f" LIMIT {limit}"
    rows = conn.execute(query).fetchall()
    conn.close()
    return rows


def get_monthly_cash_flow(year_month=None):
    """Returns (total_income, total_expense, net) for a given 'YYYY-MM'.
    Defaults to the current month."""
    year_month = year_month or date.today().isoformat()[:7]
    conn = get_connection()

    income = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'income' AND date LIKE ?",
        (f"{year_month}%",),
    ).fetchone()[0]

    expense = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'expense' AND date LIKE ?",
        (f"{year_month}%",),
    ).fetchone()[0]

    conn.close()
    return income, expense, income - expense


if __name__ == "__main__":
    init_db()
    print("Database initialized: finance.db created with all tables.")

# ---------------------------------------------------------------------
# LOANS (lending / borrowing)
# ---------------------------------------------------------------------

def add_loan(person_name, direction, amount, account_id, reason="", loan_date=None):
    """direction is 'lent' (you gave money) or 'borrowed' (you received money).
    Adjusts the account balance immediately, same logic as a transaction:
    lending money OUT reduces your balance, borrowing money IN increases it."""
    loan_date = loan_date or date.today().isoformat()
    conn = get_connection()

    conn.execute(
        """INSERT INTO loans (person_name, direction, amount, remaining_amount, reason, account_id, date, settled)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
        (person_name, direction, amount, amount, reason, account_id, loan_date),
    )

    delta = -amount if direction == "lent" else amount
    _adjust_account_balance(conn, account_id, delta)

    conn.commit()
    conn.close()


def get_loans(direction=None, include_settled=False):
    """Returns loans as a list of dicts for easy field access in the UI."""
    conn = get_connection()
    query = "SELECT id, person_name, direction, amount, remaining_amount, reason, account_id, date, settled FROM loans"
    conditions = []
    params = []
    if direction:
        conditions.append("direction = ?")
        params.append(direction)
    if not include_settled:
        conditions.append("settled = 0")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY date DESC, id DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    columns = ["id", "person_name", "direction", "amount", "remaining_amount", "reason", "account_id", "date", "settled"]
    return [dict(zip(columns, row)) for row in rows]


def add_loan_repayment(loan_id, amount, account_id, repay_date=None):
    """Records a (possibly partial) repayment against a loan, updates the
    loan's remaining balance, marks it settled if fully paid off, and
    adjusts the account balance to reflect the actual cash movement."""
    repay_date = repay_date or date.today().isoformat()
    conn = get_connection()

    loan_row = conn.execute(
        "SELECT direction, remaining_amount FROM loans WHERE id = ?", (loan_id,)
    ).fetchone()
    if not loan_row:
        conn.close()
        raise ValueError("Loan not found")

    direction, remaining = loan_row
    new_remaining = max(0, remaining - amount)
    settled = 1 if new_remaining == 0 else 0

    conn.execute(
        "INSERT INTO loan_repayments (loan_id, amount, account_id, date) VALUES (?, ?, ?, ?)",
        (loan_id, amount, account_id, repay_date),
    )
    conn.execute(
        "UPDATE loans SET remaining_amount = ?, settled = ? WHERE id = ?",
        (new_remaining, settled, loan_id),
    )

    # If you lent money and get repaid, your balance goes UP.
    # If you borrowed money and repay it, your balance goes DOWN.
    delta = amount if direction == "lent" else -amount
    _adjust_account_balance(conn, account_id, delta)

    conn.commit()
    conn.close()


def get_loan_totals():
    """Returns (total_owed_to_you, total_you_owe) across unsettled loans."""
    conn = get_connection()
    owed_to_you = conn.execute(
        "SELECT COALESCE(SUM(remaining_amount), 0) FROM loans WHERE direction = 'lent' AND settled = 0"
    ).fetchone()[0]
    you_owe = conn.execute(
        "SELECT COALESCE(SUM(remaining_amount), 0) FROM loans WHERE direction = 'borrowed' AND settled = 0"
    ).fetchone()[0]
    conn.close()
    return owed_to_you, you_owe