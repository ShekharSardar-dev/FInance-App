import sqlite3
import hashlib
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
            balance REAL NOT NULL DEFAULT 0,
            category TEXT NOT NULL DEFAULT 'bank',
            account_type TEXT,
            account_number TEXT
        )
    """)

    # Migration: add new columns if this accounts table predates them.
    existing_account_cols = [row[1] for row in cur.execute("PRAGMA table_info(accounts)").fetchall()]
    if "category" not in existing_account_cols:
        cur.execute("ALTER TABLE accounts ADD COLUMN category TEXT NOT NULL DEFAULT 'bank'")
    if "account_type" not in existing_account_cols:
        cur.execute("ALTER TABLE accounts ADD COLUMN account_type TEXT")
    if "account_number" not in existing_account_cols:
        cur.execute("ALTER TABLE accounts ADD COLUMN account_number TEXT")
    # Any pre-existing account literally named "Cash" should be tagged as cash,
    # not bank, so it's correctly excluded from the Invest tab.
    cur.execute("UPDATE accounts SET category = 'cash' WHERE name = 'Cash' AND category != 'cash'")

    # Simple key-value settings store \u2014 used for the account-number PIN.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
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
            type TEXT NOT NULL DEFAULT 'Other',
            amount_invested REAL NOT NULL,
            current_value REAL NOT NULL,
            date_added TEXT NOT NULL
        )
    """)

    # Migration: if you already had an investments table from before the
    # "type" column existed, add it now without losing existing data.
    existing_cols = [row[1] for row in cur.execute("PRAGMA table_info(investments)").fetchall()]
    if "type" not in existing_cols:
        cur.execute("ALTER TABLE investments ADD COLUMN type TEXT NOT NULL DEFAULT 'Other'")

    # Every buy/withdraw against an investment, for history + realized gain tracking.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS investment_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investment_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('buy', 'withdraw')),
            amount REAL NOT NULL,
            realized_gain REAL NOT NULL DEFAULT 0,
            account_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (investment_id) REFERENCES investments(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
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

def add_account(name, starting_balance=0, category="bank", account_type=None, account_number=None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO accounts (name, balance, category, account_type, account_number) VALUES (?, ?, ?, ?, ?)",
        (name, starting_balance, category, account_type, account_number),
    )
    conn.commit()
    conn.close()


def get_accounts():
    """Returns (id, name, balance) for every account \u2014 used by dropdowns
    that don't care about bank details (Add Transaction, Loans)."""
    conn = get_connection()
    rows = conn.execute("SELECT id, name, balance FROM accounts ORDER BY id").fetchall()
    conn.close()
    return rows


def get_bank_accounts():
    """Same as get_accounts(), but bank accounts only \u2014 used for the
    Invest tab, since investing from/to a Cash account doesn't make sense here."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, balance FROM accounts WHERE category = 'bank' ORDER BY id"
    ).fetchall()
    conn.close()
    return rows


def get_default_account_id(prefer_category="bank"):
    """Returns the id of the account that should be pre-selected by default
    in dropdowns \u2014 the earliest-created account of the preferred category,
    falling back to any account at all if none match."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM accounts WHERE category = ? ORDER BY id LIMIT 1", (prefer_category,)
    ).fetchone()
    if not row:
        row = conn.execute("SELECT id FROM accounts ORDER BY id LIMIT 1").fetchone()
    conn.close()
    return row[0] if row else None


def get_accounts_full():
    """Returns full account details as dicts \u2014 used by the Manage Accounts
    section on Home, which needs to show/mask the account number."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, balance, category, account_type, account_number FROM accounts ORDER BY id"
    ).fetchall()
    conn.close()
    columns = ["id", "name", "balance", "category", "account_type", "account_number"]
    return [dict(zip(columns, row)) for row in rows]


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
# SECURITY PIN (protects revealing full account numbers)
# ---------------------------------------------------------------------

def _hash_pin(pin):
    return hashlib.sha256(pin.encode()).hexdigest()


def has_pin_set():
    conn = get_connection()
    row = conn.execute("SELECT value FROM app_settings WHERE key = 'pin_hash'").fetchone()
    conn.close()
    return row is not None


def set_pin(pin):
    conn = get_connection()
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('pin_hash', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_hash_pin(pin),),
    )
    conn.commit()
    conn.close()


def verify_pin(pin):
    conn = get_connection()
    row = conn.execute("SELECT value FROM app_settings WHERE key = 'pin_hash'").fetchone()
    conn.close()
    if not row:
        return False
    return row[0] == _hash_pin(pin)


def mask_account_number(account_number):
    """Turns '1234567890123456' into '**** **** **** 3456'."""
    if not account_number:
        return ""
    last4 = account_number[-4:]
    return f"**** **** **** {last4}"


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


# ---------------------------------------------------------------------
# INVESTMENTS
# ---------------------------------------------------------------------

def add_investment(name, amount_invested, account_id, investment_type="Other", current_value=None, date_added=None):
    """Buying a new investment moves real cash out of an account \u2014 so we
    deduct the account balance, same as we do for loans (it's not counted
    as an 'expense' in cash flow, since it's converted into an asset, not spent)."""
    current_value = current_value if current_value is not None else amount_invested
    date_added = date_added or date.today().isoformat()
    conn = get_connection()

    cur = conn.execute(
        "INSERT INTO investments (name, type, amount_invested, current_value, date_added) VALUES (?, ?, ?, ?, ?)",
        (name, investment_type, amount_invested, current_value, date_added),
    )
    investment_id = cur.lastrowid

    conn.execute(
        "INSERT INTO investment_transactions (investment_id, type, amount, realized_gain, account_id, date) VALUES (?, 'buy', ?, 0, ?, ?)",
        (investment_id, amount_invested, account_id, date_added),
    )
    _adjust_account_balance(conn, account_id, -amount_invested)

    conn.commit()
    conn.close()


def buy_more_investment(investment_id, amount, account_id, buy_date=None):
    """Adds to an existing investment. Assumes you're buying at the current
    market price, so both invested amount and current value go up by the
    same amount (no instant paper gain/loss from the purchase itself)."""
    buy_date = buy_date or date.today().isoformat()
    conn = get_connection()

    conn.execute(
        "UPDATE investments SET amount_invested = amount_invested + ?, current_value = current_value + ? WHERE id = ?",
        (amount, amount, investment_id),
    )
    conn.execute(
        "INSERT INTO investment_transactions (investment_id, type, amount, realized_gain, account_id, date) VALUES (?, 'buy', ?, 0, ?, ?)",
        (investment_id, amount, account_id, buy_date),
    )
    _adjust_account_balance(conn, account_id, -amount)

    conn.commit()
    conn.close()


def withdraw_investment(investment_id, amount, account_id, withdraw_date=None):
    """Withdraws (sells) part or all of an investment. `amount` is based on
    CURRENT value (what it's worth now), not the original cost. We shrink
    the cost basis proportionally, so gain/loss tracking stays accurate,
    and credit the withdrawn cash back into an account."""
    withdraw_date = withdraw_date or date.today().isoformat()
    conn = get_connection()

    row = conn.execute(
        "SELECT amount_invested, current_value FROM investments WHERE id = ?", (investment_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("Investment not found")

    amount_invested, current_value = row
    if amount > current_value:
        conn.close()
        raise ValueError("Cannot withdraw more than the current value")

    proportion = amount / current_value if current_value else 0
    invested_reduction = amount_invested * proportion
    realized_gain = amount - invested_reduction

    conn.execute(
        "UPDATE investments SET amount_invested = amount_invested - ?, current_value = current_value - ? WHERE id = ?",
        (invested_reduction, amount, investment_id),
    )
    conn.execute(
        "INSERT INTO investment_transactions (investment_id, type, amount, realized_gain, account_id, date) VALUES (?, 'withdraw', ?, ?, ?, ?)",
        (investment_id, amount, realized_gain, account_id, withdraw_date),
    )
    _adjust_account_balance(conn, account_id, amount)

    conn.commit()
    conn.close()
    return realized_gain


def get_investments():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, type, amount_invested, current_value, date_added FROM investments ORDER BY date_added DESC, id DESC"
    ).fetchall()
    conn.close()
    columns = ["id", "name", "type", "amount_invested", "current_value", "date_added"]
    return [dict(zip(columns, row)) for row in rows]


def get_investment_transactions(investment_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT it.type, it.amount, it.realized_gain, it.date, a.name
           FROM investment_transactions it
           JOIN accounts a ON it.account_id = a.id
           WHERE it.investment_id = ?
           ORDER BY it.date DESC, it.id DESC""",
        (investment_id,),
    ).fetchall()
    conn.close()
    columns = ["type", "amount", "realized_gain", "date", "account_name"]
    return [dict(zip(columns, row)) for row in rows]


def update_investment_value(investment_id, new_current_value):
    conn = get_connection()
    conn.execute(
        "UPDATE investments SET current_value = ? WHERE id = ?",
        (new_current_value, investment_id),
    )
    conn.commit()
    conn.close()


def delete_investment(investment_id):
    conn = get_connection()
    conn.execute("DELETE FROM investment_transactions WHERE investment_id = ?", (investment_id,))
    conn.execute("DELETE FROM investments WHERE id = ?", (investment_id,))
    conn.commit()
    conn.close()


def get_investment_totals():
    """Returns (total_invested, total_current_value, total_gain_loss)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_invested), 0), COALESCE(SUM(current_value), 0) FROM investments"
    ).fetchone()
    conn.close()
    total_invested, total_current = row
    return total_invested, total_current, total_current - total_invested