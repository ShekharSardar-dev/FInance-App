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

    # Recurring income/expenses (salary, rent, subscriptions, SIPs) \u2014
    # used as quick-add shortcuts on the Add Transaction screen.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recurring_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'expense',
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            due_day INTEGER NOT NULL DEFAULT 1,
            account_id INTEGER NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """)

    existing_recurring_cols = [row[1] for row in cur.execute("PRAGMA table_info(recurring_items)").fetchall()]
    if "type" not in existing_recurring_cols:
        cur.execute("ALTER TABLE recurring_items ADD COLUMN type TEXT NOT NULL DEFAULT 'expense'")

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

    # Categories you can pick from when adding transactions. Seeded with
    # the defaults the first time, then fully editable from Settings.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            UNIQUE(name, type)
        )
    """)
    _seed_default_categories(cur)

    conn.commit()
    conn.close()


DEFAULT_EXPENSE_CATEGORIES = ["Food", "Travel", "Rent", "Utilities", "Miscellaneous", "Other Expense"]
DEFAULT_INCOME_CATEGORIES = ["Salary", "Business", "Gift", "Interest", "Other Income"]


def _seed_default_categories(cur):
    """Fills the categories table with the defaults, but only if it's empty,
    so categories you've added or removed are never overwritten."""
    already = cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    if already:
        return
    for name in DEFAULT_EXPENSE_CATEGORIES:
        cur.execute("INSERT INTO categories (name, type) VALUES (?, 'expense')", (name,))
    for name in DEFAULT_INCOME_CATEGORIES:
        cur.execute("INSERT INTO categories (name, type) VALUES (?, 'income')", (name,))


# ---------------------------------------------------------------------
# CATEGORIES
# ---------------------------------------------------------------------

def get_category_names(type_):
    """Names only, in the order they were created \u2014 for dropdowns."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT name FROM categories WHERE type = ? ORDER BY id", (type_,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_categories_full(type_):
    """id + name, for the Settings list where each one has a delete button."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name FROM categories WHERE type = ? ORDER BY id", (type_,)
    ).fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1]} for r in rows]


def add_category(name, type_):
    name = (name or "").strip()
    if not name:
        raise ValueError("Enter a category name")
    conn = get_connection()
    try:
        conn.execute("INSERT INTO categories (name, type) VALUES (?, ?)", (name, type_))
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f"'{name}' already exists")
    finally:
        conn.close()


def delete_category(category_id):
    """Removes it from the pick-lists only. Past transactions keep their
    category text, so history and charts are unaffected."""
    conn = get_connection()
    row = conn.execute("SELECT type FROM categories WHERE id = ?", (category_id,)).fetchone()
    if row:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM categories WHERE type = ?", (row[0],)
        ).fetchone()[0]
        if remaining <= 1:
            conn.close()
            raise ValueError(f"Keep at least one {row[0]} category")
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
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


def has_completed_setup():
    conn = get_connection()
    row = conn.execute("SELECT value FROM app_settings WHERE key = 'setup_complete'").fetchone()
    conn.close()
    return row is not None


def mark_setup_complete():
    conn = get_connection()
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('setup_complete', '1') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    conn.commit()
    conn.close()


def verify_account_number(account_number):
    """Checks whether this exactly matches any account's stored number \u2014
    used to confirm identity when resetting a forgotten PIN."""
    if not account_number:
        return False
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM accounts WHERE account_number = ? LIMIT 1", (account_number,)
    ).fetchone()
    conn.close()
    return row is not None


def reset_all_data():
    """Wipes every table back to empty, including the PIN and the
    setup-complete flag \u2014 so the app behaves like a fresh install again
    the next time it starts. The table structures themselves are untouched."""
    conn = get_connection()
    # Order matters: tables that point at other tables (via foreign keys)
    # must be emptied BEFORE the tables they point at.
    tables = [
        "loan_repayments", "investment_transactions", "transactions",
        "recurring_items", "budgets", "loans", "investments",
        "accounts", "categories", "app_settings",
    ]
    for table in tables:
        conn.execute(f"DELETE FROM {table}")
    # Put the default categories back, so a fresh start has something to pick from.
    _seed_default_categories(conn.cursor())
    conn.commit()
    conn.close()


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


def account_has_history(account_id):
    """Checks whether an account is referenced anywhere else \u2014 transactions,
    loans, repayments, or investment purchases \u2014 so we don't delete an
    account and leave orphaned records pointing at nothing."""
    conn = get_connection()
    checks = [
        "SELECT 1 FROM transactions WHERE account_id = ? LIMIT 1",
        "SELECT 1 FROM loans WHERE account_id = ? LIMIT 1",
        "SELECT 1 FROM loan_repayments WHERE account_id = ? LIMIT 1",
        "SELECT 1 FROM investment_transactions WHERE account_id = ? LIMIT 1",
    ]
    found = any(conn.execute(q, (account_id,)).fetchone() for q in checks)
    conn.close()
    return found


def update_account(account_id, name=None, account_type=None, account_number=None, balance=None):
    conn = get_connection()
    fields, params = [], []
    if name is not None:
        fields.append("name = ?"); params.append(name)
    if account_type is not None:
        fields.append("account_type = ?"); params.append(account_type)
    if account_number is not None:
        fields.append("account_number = ?"); params.append(account_number)
    if balance is not None:
        fields.append("balance = ?"); params.append(balance)
    if fields:
        params.append(account_id)
        conn.execute(f"UPDATE accounts SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    conn.close()


def delete_account(account_id):
    """Only deletes if nothing else references this account, to keep the
    rest of your data intact."""
    if account_has_history(account_id):
        raise ValueError("Can't delete an account that already has transaction history.")
    conn = get_connection()
    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    conn.commit()
    conn.close()


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


def get_transactions_for_month(year_month):
    """Same shape as get_transactions(), but only one 'YYYY-MM' month \u2014
    used by the View All screen so it never has to load years of history."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.id, t.type, t.amount, t.category, t.sub_category, t.note, t.date, a.name
           FROM transactions t
           JOIN accounts a ON t.account_id = a.id
           WHERE t.date LIKE ?
           ORDER BY t.date DESC, t.id DESC""",
        (f"{year_month}%",),
    ).fetchall()
    conn.close()
    return rows


def get_transaction(transaction_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT id, account_id, type, amount, category, note, date FROM transactions WHERE id = ?",
        (transaction_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    columns = ["id", "account_id", "type", "amount", "category", "note", "date"]
    return dict(zip(columns, row))


def update_transaction(transaction_id, account_id, type_, amount, category, note, txn_date):
    """Edits a transaction AND keeps account balances right: the old
    transaction's effect is undone on its old account, then the new one is
    applied to the (possibly different) new account. All-or-nothing."""
    if type_ not in ("income", "expense"):
        raise ValueError("Type must be income or expense")
    if amount <= 0:
        raise ValueError("Amount must be more than zero")
    try:
        txn_date = date.fromisoformat((txn_date or "").strip()).isoformat()
    except ValueError:
        raise ValueError("Enter the date as YYYY-MM-DD")

    conn = get_connection()
    try:
        old = conn.execute(
            "SELECT account_id, type, amount FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if not old:
            raise ValueError("Transaction not found")
        old_account, old_type, old_amount = old

        # Undo the old effect, then apply the new one.
        _adjust_account_balance(conn, old_account, -old_amount if old_type == "income" else old_amount)
        _adjust_account_balance(conn, account_id, amount if type_ == "income" else -amount)

        conn.execute(
            """UPDATE transactions
               SET account_id = ?, type = ?, amount = ?, category = ?, note = ?, date = ?
               WHERE id = ?""",
            (account_id, type_, amount, category, note, txn_date, transaction_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_transaction(transaction_id):
    """Removes a transaction and puts its money back: deleting an expense
    returns it to the account, deleting income takes it back out."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT account_id, type, amount FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if not row:
            raise ValueError("Transaction not found")
        account_id, type_, amount = row
        _adjust_account_balance(conn, account_id, -amount if type_ == "income" else amount)
        conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        conn.commit()
    finally:
        conn.close()


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


# ---------------------------------------------------------------------
# STATS (category breakdown, trend, budgets)
# ---------------------------------------------------------------------

def get_category_spending(year_month=None):
    """Returns [(category, total_spent), ...] for expenses in a given
    month, highest spend first. Powers the Stats pie chart."""
    year_month = year_month or date.today().isoformat()[:7]
    conn = get_connection()
    rows = conn.execute(
        """SELECT category, SUM(amount) FROM transactions
           WHERE type = 'expense' AND date LIKE ?
           GROUP BY category ORDER BY SUM(amount) DESC""",
        (f"{year_month}%",),
    ).fetchall()
    conn.close()
    return rows


def shift_month(year_month, delta):
    """Shifts a 'YYYY-MM' string by `delta` months (negative = backward)."""
    year, month = (int(p) for p in year_month.split("-"))
    month += delta
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return f"{year:04d}-{month:02d}"


def get_available_months(back=12):
    """Returns the last `back` 'YYYY-MM' strings up to and including the
    current month, newest first \u2014 used to populate the month picker."""
    current = date.today().isoformat()[:7]
    return [shift_month(current, -i) for i in range(back)]


def get_cash_flow_trend(months=6):
    """Returns [(year_month, income, expense), ...] for the last `months`
    months in chronological order (oldest first), for the Stats trend chart."""
    conn = get_connection()
    today = date.today()
    results = []
    for i in range(months - 1, -1, -1):
        # Walk back month by month without needing extra libraries.
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        ym = f"{year:04d}-{month:02d}"

        income = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'income' AND date LIKE ?",
            (f"{ym}%",),
        ).fetchone()[0]
        expense = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'expense' AND date LIKE ?",
            (f"{ym}%",),
        ).fetchone()[0]
        results.append((ym, income, expense))

    conn.close()
    return results


def get_income_by_category(year_month=None):
    """Same idea as get_category_spending, but for income \u2014 powers the
    income breakdown pie chart."""
    year_month = year_month or date.today().isoformat()[:7]
    conn = get_connection()
    rows = conn.execute(
        """SELECT category, SUM(amount) FROM transactions
           WHERE type = 'income' AND date LIKE ?
           GROUP BY category ORDER BY SUM(amount) DESC""",
        (f"{year_month}%",),
    ).fetchall()
    conn.close()
    return rows


def get_month_comparison(year_month=None):
    """Returns [(category, this_month, last_month, pct_change), ...] for
    expense categories, comparing the given month to the one before it.
    pct_change is None when there's nothing to compare against (division by zero)."""
    year_month = year_month or date.today().isoformat()[:7]
    prev_month = shift_month(year_month, -1)

    this_month_rows = dict(get_category_spending(year_month))
    prev_month_rows = dict(get_category_spending(prev_month))

    categories = set(this_month_rows) | set(prev_month_rows)
    results = []
    for cat in categories:
        current = this_month_rows.get(cat, 0)
        previous = prev_month_rows.get(cat, 0)
        pct_change = ((current - previous) / previous * 100) if previous else None
        results.append((cat, current, previous, pct_change))

    results.sort(key=lambda r: r[1], reverse=True)
    return results


def get_category_trend(category, txn_type="expense", months=6):
    """Returns [(year_month, amount), ...] for one specific category across
    the last `months` months (oldest first) \u2014 powers the category trend line chart."""
    conn = get_connection()
    current = date.today().isoformat()[:7]
    results = []
    for i in range(months - 1, -1, -1):
        ym = shift_month(current, -i)
        amount = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = ? AND category = ? AND date LIKE ?",
            (txn_type, category, f"{ym}%"),
        ).fetchone()[0]
        results.append((ym, amount))
    conn.close()
    return results


def get_projected_month_end_spend(year_month=None):
    """Projects the full month's expense total based on the daily average
    spend so far. Only really meaningful for the CURRENT, in-progress month
    \u2014 returns None for any other month since there's nothing to project."""
    current = date.today().isoformat()[:7]
    year_month = year_month or current
    if year_month != current:
        return None

    today = date.today()
    days_elapsed = today.day

    import calendar
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    conn = get_connection()
    spent_so_far = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'expense' AND date LIKE ?",
        (f"{year_month}%",),
    ).fetchone()[0]
    conn.close()

    if days_elapsed == 0:
        return None
    daily_average = spent_so_far / days_elapsed
    return daily_average * days_in_month, spent_so_far, days_elapsed, days_in_month


def set_budget(category, monthly_limit):
    """Creates or updates the budget for a category (one budget per category)."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO budgets (category, monthly_limit) VALUES (?, ?) "
        "ON CONFLICT(category) DO UPDATE SET monthly_limit = excluded.monthly_limit",
        (category, monthly_limit),
    )
    conn.commit()
    conn.close()


def get_budgets(year_month=None):
    """Returns each budget along with how much was actually spent on that
    category in the given month (defaults to the current month), so the UI
    can draw a progress bar directly."""
    year_month = year_month or date.today().isoformat()[:7]
    conn = get_connection()
    budget_rows = conn.execute("SELECT id, category, monthly_limit FROM budgets ORDER BY category").fetchall()

    results = []
    for budget_id, category, limit in budget_rows:
        spent = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'expense' AND category = ? AND date LIKE ?",
            (category, f"{year_month}%"),
        ).fetchone()[0]
        results.append({"id": budget_id, "category": category, "monthly_limit": limit, "spent": spent})

    conn.close()
    return results


def delete_budget(budget_id):
    conn = get_connection()
    conn.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
    conn.commit()
    conn.close()


def shift_month(months_ago, from_year_month=None):
    """Returns the 'YYYY-MM' string for `months_ago` months before
    `from_year_month` (defaults to the current month). Used anywhere we
    need to look at a previous month, e.g. month-over-month comparisons."""
    if from_year_month:
        year, month = (int(x) for x in from_year_month.split("-"))
    else:
        today = date.today()
        year, month = today.year, today.month

    month -= months_ago
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:  # a negative months_ago moves forward in time
        month -= 12
        year += 1
    return f"{year:04d}-{month:02d}"


def get_net_worth():
    """Returns a breakdown dict: cash_and_bank, investments_value,
    owed_to_you, you_owe, and the total net_worth."""
    accounts = get_accounts_full()
    cash_and_bank = sum(a["balance"] for a in accounts)

    _invested, investments_value, _gain = get_investment_totals()
    owed_to_you, you_owe = get_loan_totals()

    net_worth = cash_and_bank + investments_value + owed_to_you - you_owe
    return {
        "cash_and_bank": cash_and_bank,
        "investments_value": investments_value,
        "owed_to_you": owed_to_you,
        "you_owe": you_owe,
        "net_worth": net_worth,
    }


def get_top_expenses(year_month=None, limit=5):
    """Returns the biggest individual expenses in a month, not grouped by
    category \u2014 useful for spotting one-off big spends."""
    year_month = year_month or date.today().isoformat()[:7]
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.category, t.amount, t.note, t.date, a.name
           FROM transactions t
           JOIN accounts a ON t.account_id = a.id
           WHERE t.type = 'expense' AND t.date LIKE ?
           ORDER BY t.amount DESC
           LIMIT ?""",
        (f"{year_month}%", limit),
    ).fetchall()
    conn.close()
    columns = ["category", "amount", "note", "date", "account_name"]
    return [dict(zip(columns, row)) for row in rows]


def get_transactions_by_category(category, year_month=None):
    """Every transaction in a given category for a given month \u2014 powers
    tapping a category in the Stats breakdown to see what's behind it."""
    year_month = year_month or date.today().isoformat()[:7]
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.amount, t.note, t.date, a.name
           FROM transactions t
           JOIN accounts a ON t.account_id = a.id
           WHERE t.type = 'expense' AND t.category = ? AND t.date LIKE ?
           ORDER BY t.date DESC, t.id DESC""",
        (category, f"{year_month}%"),
    ).fetchall()
    conn.close()
    columns = ["amount", "note", "date", "account_name"]
    return [dict(zip(columns, row)) for row in rows]



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


def update_investment_details(investment_id, name=None, investment_type=None):
    """Edits just the label/type \u2014 amount/value changes go through
    buy_more_investment / withdraw_investment / update_investment_value
    instead, so history and account balances stay accurate."""
    conn = get_connection()
    fields, params = [], []
    if name is not None:
        fields.append("name = ?"); params.append(name)
    if investment_type is not None:
        fields.append("type = ?"); params.append(investment_type)
    if fields:
        params.append(investment_id)
        conn.execute(f"UPDATE investments SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    conn.close()


def delete_investment(investment_id):
    """Deleting an investment reverses every buy/withdraw it ever had back
    into the accounts they came from/went to, so balances end up exactly
    as if the investment had never existed, then removes it entirely."""
    conn = get_connection()
    txns = conn.execute(
        "SELECT type, amount, account_id FROM investment_transactions WHERE investment_id = ?",
        (investment_id,),
    ).fetchall()

    for txn_type, amount, account_id in txns:
        # A 'buy' had taken money OUT of the account, so reverse = give it back.
        # A 'withdraw' had put money IN, so reverse = take it back out.
        delta = amount if txn_type == "buy" else -amount
        _adjust_account_balance(conn, account_id, delta)

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


# ---------------------------------------------------------------------
# RECURRING ITEMS (quick-add shortcuts for regular income/expenses)
# ---------------------------------------------------------------------

def add_recurring_item(name, amount, type_, category, account_id, due_day=1):
    conn = get_connection()
    conn.execute(
        "INSERT INTO recurring_items (name, type, amount, category, due_day, account_id) VALUES (?, ?, ?, ?, ?, ?)",
        (name, type_, amount, category, due_day, account_id),
    )
    conn.commit()
    conn.close()


def get_recurring_items(type_=None):
    conn = get_connection()
    query = """SELECT r.id, r.name, r.type, r.amount, r.category, r.due_day, r.account_id, a.name
               FROM recurring_items r JOIN accounts a ON r.account_id = a.id"""
    params = ()
    if type_:
        query += " WHERE r.type = ?"
        params = (type_,)
    query += " ORDER BY r.name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    columns = ["id", "name", "type", "amount", "category", "due_day", "account_id", "account_name"]
    return [dict(zip(columns, row)) for row in rows]


def delete_recurring_item(item_id):
    conn = get_connection()
    conn.execute("DELETE FROM recurring_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()