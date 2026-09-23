import database

database.init_db()

# Add two accounts (only run this once — running it again will error,
# since account names must be unique)
database.add_account("Bank", starting_balance=10000)
database.add_account("Cash", starting_balance=2000)

print("Accounts:", database.get_accounts())

# Add a test transaction
bank_id = database.get_accounts()[0][0]  # id of the first account
database.add_transaction(bank_id, "expense", 500, "Food", note="Lunch with friends")

print("Accounts after expense:", database.get_accounts())
print("Transactions:", database.get_transactions())
print("This month's cash flow:", database.get_monthly_cash_flow())