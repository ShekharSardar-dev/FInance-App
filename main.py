import flet as ft
import database as db

db.init_db()


def main(page: ft.Page):
    page.title = "Finance Tracker"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.padding = 0

    # ---------------------------------------------------------------
    # Small reusable "card" helper — gives us that clean, rounded,
    # Apple-ish look without repeating style code everywhere.
    # ---------------------------------------------------------------
    def card(content, padding=16):
        return ft.Container(
            content=content,
            padding=padding,
            border_radius=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            shadow=ft.BoxShadow(
                blur_radius=10,
                color=ft.Colors.with_opacity(0.08, ft.Colors.BLACK),
                offset=ft.Offset(0, 2),
            ),
        )

    # ---------------------------------------------------------------
    # HOME VIEW
    # ---------------------------------------------------------------
    home_content = ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    # Tracks which account numbers are currently revealed this session
    # (resets every time the app restarts \u2014 nothing stays unmasked permanently).
    revealed_accounts = {}

    def set_default_account(dropdown, prefer_category="bank"):
        """If a dropdown has no selection yet, default it to the primary
        bank account (or any account if no bank account exists)."""
        if not dropdown.value:
            default_id = db.get_default_account_id(prefer_category)
            if default_id is not None:
                dropdown.value = str(default_id)

    # --- PIN dialog: set a PIN the first time, verify it every time after ---
    pin_entry_field = ft.TextField(label="Enter PIN", password=True, can_reveal_password=True, keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    pin_confirm_field = ft.TextField(label="Confirm PIN", password=True, can_reveal_password=True, keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    pin_error = ft.Text("", color=ft.Colors.RED)
    pin_state = {"account_id": None}

    def close_pin_dialog(e=None):
        page.pop_dialog()

    def confirm_pin(e):
        pin_error.value = ""
        pin = pin_entry_field.value or ""
        if len(pin) < 4:
            pin_error.value = "PIN must be at least 4 digits"
            page.update()
            return

        if db.has_pin_set():
            if not db.verify_pin(pin):
                pin_error.value = "Incorrect PIN"
                page.update()
                return
        else:
            if pin != (pin_confirm_field.value or ""):
                pin_error.value = "PINs don't match"
                page.update()
                return
            db.set_pin(pin)

        revealed_accounts[pin_state["account_id"]] = True
        page.pop_dialog()
        build_home()
        page.update()

    pin_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Enter PIN"),
        content=ft.Column([pin_entry_field, pin_confirm_field, pin_error], tight=True, spacing=12),
        actions=[
            ft.TextButton("Cancel", on_click=close_pin_dialog),
            ft.TextButton("Confirm", on_click=confirm_pin),
        ],
    )

    def open_pin_dialog(account_id):
        pin_state["account_id"] = account_id
        pin_entry_field.value = ""
        pin_confirm_field.value = ""
        pin_error.value = ""
        first_time = not db.has_pin_set()
        pin_dialog.title = ft.Text("Set a PIN" if first_time else "Enter PIN")
        pin_confirm_field.visible = first_time
        page.show_dialog(pin_dialog)

    def hide_account_number(account_id):
        revealed_accounts[account_id] = False
        build_home()

    # --- Add Bank Account dialog ---
    new_bank_name_field = ft.TextField(label="Bank name", border_color=ft.Colors.OUTLINE)
    new_bank_type_dropdown = ft.Dropdown(
        label="Account type",
        options=[ft.dropdown.Option("Savings"), ft.dropdown.Option("Current")],
        border_color=ft.Colors.OUTLINE,
    )
    new_bank_number_field = ft.TextField(label="Account number (optional)", border_color=ft.Colors.OUTLINE)
    new_bank_balance_field = ft.TextField(label="Available balance", prefix=ft.Text("\u20b9"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    new_bank_error = ft.Text("", color=ft.Colors.RED)

    def close_add_bank_dialog(e=None):
        page.pop_dialog()

    def confirm_add_bank(e):
        new_bank_error.value = ""
        if not new_bank_name_field.value:
            new_bank_error.value = "Enter a bank name"
            page.update()
            return
        try:
            balance = float(new_bank_balance_field.value)
            if balance < 0:
                raise ValueError
        except (ValueError, TypeError):
            new_bank_error.value = "Enter a valid balance"
            page.update()
            return

        db.add_account(
            name=new_bank_name_field.value,
            starting_balance=balance,
            category="bank",
            account_type=new_bank_type_dropdown.value,
            account_number=new_bank_number_field.value or None,
        )

        new_bank_name_field.value = ""
        new_bank_type_dropdown.value = None
        new_bank_number_field.value = ""
        new_bank_balance_field.value = ""
        page.pop_dialog()
        build_home()
        page.update()

    add_bank_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Add Bank Account"),
        content=ft.Column(
            [new_bank_name_field, new_bank_type_dropdown, new_bank_number_field, new_bank_balance_field, new_bank_error],
            tight=True,
            spacing=12,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=close_add_bank_dialog),
            ft.TextButton("Add", on_click=confirm_add_bank),
        ],
    )

    def open_add_bank_dialog(e=None):
        new_bank_error.value = ""
        page.show_dialog(add_bank_dialog)

    def build_home():
        home_content.controls.clear()

        accounts_full = db.get_accounts_full()
        income, expense, net = db.get_monthly_cash_flow()

        # --- Combined balance cards: all banks summed into one, cash separate ---
        bank_total = sum(a["balance"] for a in accounts_full if a["category"] == "bank")
        cash_total = sum(a["balance"] for a in accounts_full if a["category"] == "cash")

        summary_cards = [("Bank (all accounts)", bank_total)]
        if any(a["category"] == "cash" for a in accounts_full):
            summary_cards.append(("Cash", cash_total))

        account_cards = ft.Row(
            [
                card(
                    ft.Column(
                        [
                            ft.Text(label, size=14, color=ft.Colors.GREY),
                            ft.Text(f"\u20b9{balance:,.2f}", size=20, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=4,
                    ),
                    padding=14,
                )
                for (label, balance) in summary_cards
            ],
            spacing=12,
            wrap=True,
        )

        # --- This month's cash flow summary ---
        net_color = ft.Colors.GREEN if net >= 0 else ft.Colors.RED
        cash_flow_card = card(
            ft.Column(
                [
                    ft.Text("This Month", size=14, color=ft.Colors.GREY),
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("Income", size=12, color=ft.Colors.GREY),
                                    ft.Text(f"\u20b9{income:,.2f}", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN),
                                ]
                            ),
                            ft.Column(
                                [
                                    ft.Text("Expense", size=12, color=ft.Colors.GREY),
                                    ft.Text(f"\u20b9{expense:,.2f}", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED),
                                ]
                            ),
                            ft.Column(
                                [
                                    ft.Text("Net", size=12, color=ft.Colors.GREY),
                                    ft.Text(f"\u20b9{net:,.2f}", size=16, weight=ft.FontWeight.BOLD, color=net_color),
                                ]
                            ),
                        ],
                        spacing=30,
                    ),
                ],
                spacing=8,
            )
        )

        # --- Recent transactions list ---
        recent = db.get_transactions(limit=10)
        txn_rows = []
        for (_id, ttype, amount, category, sub_category, note, txn_date, account_name) in recent:
            color = ft.Colors.GREEN if ttype == "income" else ft.Colors.RED
            sign = "+" if ttype == "income" else "-"
            txn_rows.append(
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(category, weight=ft.FontWeight.W_600),
                                ft.Text(f"{account_name} \u00b7 {note or ''}", size=12, color=ft.Colors.GREY),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Column(
                            [
                                ft.Text(f"{sign}\u20b9{amount:,.2f}", color=color, weight=ft.FontWeight.BOLD),
                                ft.Text(txn_date, size=11, color=ft.Colors.GREY),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            spacing=2,
                        ),
                    ]
                )
            )
            txn_rows.append(ft.Divider(height=1))

        recent_card = card(
            ft.Column(
                [ft.Text("Recent Transactions", size=14, color=ft.Colors.GREY)] + txn_rows,
                spacing=10,
            )
        )

        # --- Manage Accounts: list with masked bank numbers + add new ---
        def account_row(acc):
            is_bank = acc["category"] == "bank"
            revealed = revealed_accounts.get(acc["id"], False)

            details = []
            if is_bank:
                details.append(ft.Text(acc["account_type"] or "Bank", size=12, color=ft.Colors.GREY))
                if acc["account_number"]:
                    shown_number = acc["account_number"] if revealed else db.mask_account_number(acc["account_number"])
                    details.append(
                        ft.Row(
                            [
                                ft.Text(shown_number, size=12, color=ft.Colors.GREY),
                                ft.TextButton(
                                    "Hide" if revealed else "Show",
                                    on_click=(lambda e, aid=acc["id"]: hide_account_number(aid))
                                    if revealed
                                    else (lambda e, aid=acc["id"]: open_pin_dialog(aid)),
                                ),
                            ],
                            spacing=4,
                        )
                    )

            return ft.Container(
                content=ft.Row(
                    [
                        ft.Column(
                            [ft.Text(acc["name"], weight=ft.FontWeight.W_600)] + details,
                            spacing=2,
                            expand=True,
                        ),
                        ft.Text(f"\u20b9{acc['balance']:,.2f}", weight=ft.FontWeight.BOLD),
                    ]
                ),
                padding=ft.Padding.symmetric(vertical=6),
            )

        account_rows = [account_row(a) for a in accounts_full]
        manage_accounts_card = card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Manage Accounts", size=14, color=ft.Colors.GREY, expand=True),
                            ft.TextButton("+ Add Bank Account", on_click=open_add_bank_dialog),
                        ]
                    ),
                    ft.Divider(height=1),
                ]
                + account_rows,
                spacing=4,
            )
        )

        home_content.controls.extend([account_cards, cash_flow_card, manage_accounts_card, recent_card])
        page.update()

    # ---------------------------------------------------------------
    # ADD TRANSACTION VIEW
    # ---------------------------------------------------------------
    type_toggle = ft.CupertinoSlidingSegmentedButton(
        selected_index=1,
        controls=[ft.Text("Income"), ft.Text("Expense")],
    )
    amount_field = ft.TextField(label="Amount", prefix=ft.Text("\u20b9"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    account_dropdown = ft.Dropdown(label="Paid via", border_color=ft.Colors.OUTLINE)

    EXPENSE_CATEGORIES = ["Food", "Travel", "Rent", "Utilities", "Miscellaneous", "Other Expense"]
    INCOME_CATEGORIES = ["Salary", "Business", "Gift", "Interest", "Other Income"]

    category_dropdown = ft.Dropdown(
        label="Category",
        options=[ft.dropdown.Option(c) for c in EXPENSE_CATEGORIES],
        border_color=ft.Colors.OUTLINE,
    )
    counterparty_field = ft.TextField(label="Paid To (optional)", border_color=ft.Colors.OUTLINE)
    note_field = ft.TextField(label="Note (optional)", border_color=ft.Colors.OUTLINE)
    add_feedback = ft.Text("", color=ft.Colors.GREEN)

    def on_type_change(e):
        # Swap category list and relabel fields depending on whether this
        # is income or an expense.
        is_income = type_toggle.selected_index == 0
        category_dropdown.options = [
            ft.dropdown.Option(c) for c in (INCOME_CATEGORIES if is_income else EXPENSE_CATEGORIES)
        ]
        category_dropdown.value = None
        counterparty_field.label = "Received From (optional)" if is_income else "Paid To (optional)"
        account_dropdown.label = "Received In" if is_income else "Paid Via"
        page.update()

    type_toggle.on_change = on_type_change

    def refresh_account_dropdown():
        account_dropdown.options = [
            ft.dropdown.Option(key=str(a_id), text=name) for (a_id, name, _bal) in db.get_accounts()
        ]
        set_default_account(account_dropdown)

    def submit_transaction(e):
        add_feedback.value = ""
        try:
            amount = float(amount_field.value)
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            amount_field.error_text = "Enter a valid amount"
            page.update()
            return

        if not account_dropdown.value:
            add_feedback.value = "Pick an account"
            add_feedback.color = ft.Colors.RED
            page.update()
            return

        if not category_dropdown.value:
            add_feedback.value = "Pick a category"
            add_feedback.color = ft.Colors.RED
            page.update()
            return

        type_ = "income" if type_toggle.selected_index == 0 else "expense"

        # Combine the counterparty (Received From / Paid To) with the note
        # into a single note string, since our database doesn't need a
        # separate column for this.
        combined_note = note_field.value or ""
        if counterparty_field.value:
            prefix = "From" if type_ == "income" else "To"
            combined_note = f"{prefix}: {counterparty_field.value}" + (f" \u2014 {combined_note}" if combined_note else "")

        db.add_transaction(
            account_id=int(account_dropdown.value),
            type_=type_,
            amount=amount,
            category=category_dropdown.value,
            note=combined_note,
        )

        # Reset form
        amount_field.value = ""
        amount_field.error_text = None
        account_dropdown.value = None
        category_dropdown.value = None
        counterparty_field.value = ""
        note_field.value = ""
        add_feedback.value = "Added!"
        add_feedback.color = ft.Colors.GREEN

        build_home()  # refresh Home so it reflects the new transaction
        page.update()

    add_content = ft.Column(
        [
            ft.Text("Add Transaction", size=22, weight=ft.FontWeight.BOLD),
            type_toggle,
            amount_field,
            account_dropdown,
            category_dropdown,
            counterparty_field,
            note_field,
            ft.ElevatedButton("Add", on_click=submit_transaction, width=200),
            add_feedback,
        ],
        spacing=16,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    # ---------------------------------------------------------------
    # PLACEHOLDER VIEWS (built in later stages)
    # ---------------------------------------------------------------
    def placeholder(text):
        return ft.Column(
            [ft.Text(text, size=18, color=ft.Colors.GREY)],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

    # ---------------------------------------------------------------
    # LOANS VIEW
    # ---------------------------------------------------------------
    loans_content = ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    loan_direction_toggle = ft.CupertinoSlidingSegmentedButton(
        selected_index=0,
        controls=[ft.Text("Lent (owed to me)"), ft.Text("Borrowed (I owe)")],
    )
    loan_person_field = ft.TextField(label="Person's name", border_color=ft.Colors.OUTLINE)
    loan_amount_field = ft.TextField(label="Amount", prefix=ft.Text("\u20b9"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    loan_account_dropdown = ft.Dropdown(label="Account", border_color=ft.Colors.OUTLINE)
    loan_reason_field = ft.TextField(label="Reason (optional)", border_color=ft.Colors.OUTLINE)
    loan_feedback = ft.Text("", color=ft.Colors.GREEN)

    # --- Repayment dialog (reused for any loan) ---
    repay_amount_field = ft.TextField(label="Repayment amount", prefix=ft.Text("\u20b9"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    repay_account_dropdown = ft.Dropdown(label="Account", border_color=ft.Colors.OUTLINE)
    repay_error = ft.Text("", color=ft.Colors.RED)
    active_repay_loan_id = {"id": None}

    def close_repay_dialog(e=None):
        page.pop_dialog()

    def confirm_repayment(e):
        repay_error.value = ""
        try:
            amount = float(repay_amount_field.value)
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            repay_error.value = "Enter a valid amount"
            page.update()
            return

        if not repay_account_dropdown.value:
            repay_error.value = "Pick an account"
            page.update()
            return

        db.add_loan_repayment(
            loan_id=active_repay_loan_id["id"],
            amount=amount,
            account_id=int(repay_account_dropdown.value),
        )
        page.pop_dialog()
        build_loans()
        build_home()
        page.update()

    repay_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Record Repayment"),
        content=ft.Column(
            [repay_amount_field, repay_account_dropdown, repay_error],
            tight=True,
            spacing=12,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=close_repay_dialog),
            ft.TextButton("Confirm", on_click=confirm_repayment),
        ],
    )

    def open_repay_dialog(loan_id):
        active_repay_loan_id["id"] = loan_id
        repay_amount_field.value = ""
        repay_account_dropdown.value = None
        repay_account_dropdown.options = [
            ft.dropdown.Option(key=str(a_id), text=name) for (a_id, name, _bal) in db.get_accounts()
        ]
        set_default_account(repay_account_dropdown)
        repay_error.value = ""
        page.show_dialog(repay_dialog)

    def build_loans():
        loans_content.controls.clear()

        owed_to_you, you_owe = db.get_loan_totals()
        totals_card = card(
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text("Owed to you", size=12, color=ft.Colors.GREY),
                            ft.Text(f"\u20b9{owed_to_you:,.2f}", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN),
                        ]
                    ),
                    ft.Column(
                        [
                            ft.Text("You owe", size=12, color=ft.Colors.GREY),
                            ft.Text(f"\u20b9{you_owe:,.2f}", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED),
                        ]
                    ),
                ],
                spacing=40,
            )
        )

        # --- New loan form ---
        loan_account_dropdown.options = [
            ft.dropdown.Option(key=str(a_id), text=name) for (a_id, name, _bal) in db.get_accounts()
        ]
        set_default_account(loan_account_dropdown)
        new_loan_card = card(
            ft.Column(
                [
                    ft.Text("Add Lend / Borrow", size=14, color=ft.Colors.GREY),
                    loan_direction_toggle,
                    loan_person_field,
                    loan_amount_field,
                    loan_account_dropdown,
                    loan_reason_field,
                    ft.ElevatedButton("Add", on_click=submit_loan, width=200),
                    loan_feedback,
                ],
                spacing=12,
            )
        )

        # --- Active loans list ---
        def loan_row(loan):
            color = ft.Colors.GREEN if loan["direction"] == "lent" else ft.Colors.RED
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(loan["person_name"], weight=ft.FontWeight.W_600),
                                ft.Text(loan["reason"] or "No reason given", size=12, color=ft.Colors.GREY),
                                ft.Text(loan["date"], size=11, color=ft.Colors.GREY),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Column(
                            [
                                ft.Text(f"\u20b9{loan['remaining_amount']:,.2f}", color=color, weight=ft.FontWeight.BOLD),
                                ft.Text(f"of \u20b9{loan['amount']:,.2f}", size=11, color=ft.Colors.GREY),
                                ft.TextButton("Repay", on_click=lambda e, lid=loan["id"]: open_repay_dialog(lid)),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            spacing=2,
                        ),
                    ]
                ),
                padding=ft.Padding.symmetric(vertical=6),
            )

        lent_loans = db.get_loans(direction="lent")
        borrowed_loans = db.get_loans(direction="borrowed")

        lent_rows = [loan_row(l) for l in lent_loans] or [ft.Text("No active loans", color=ft.Colors.GREY)]
        borrowed_rows = [loan_row(l) for l in borrowed_loans] or [ft.Text("Nothing borrowed", color=ft.Colors.GREY)]

        lent_card = card(
            ft.Column([ft.Text("People who owe you", size=14, color=ft.Colors.GREY), ft.Divider(height=1)] + lent_rows, spacing=4)
        )
        borrowed_card = card(
            ft.Column([ft.Text("People you owe", size=14, color=ft.Colors.GREY), ft.Divider(height=1)] + borrowed_rows, spacing=4)
        )

        loans_content.controls.extend([totals_card, new_loan_card, lent_card, borrowed_card])
        page.update()

    def submit_loan(e):
        loan_feedback.value = ""
        try:
            amount = float(loan_amount_field.value)
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            loan_amount_field.error_text = "Enter a valid amount"
            page.update()
            return

        if not loan_person_field.value:
            loan_feedback.value = "Enter a person's name"
            loan_feedback.color = ft.Colors.RED
            page.update()
            return

        if not loan_account_dropdown.value:
            loan_feedback.value = "Pick an account"
            loan_feedback.color = ft.Colors.RED
            page.update()
            return

        direction = "lent" if loan_direction_toggle.selected_index == 0 else "borrowed"

        db.add_loan(
            person_name=loan_person_field.value,
            direction=direction,
            amount=amount,
            account_id=int(loan_account_dropdown.value),
            reason=loan_reason_field.value or "",
        )

        loan_person_field.value = ""
        loan_amount_field.value = ""
        loan_amount_field.error_text = None
        loan_account_dropdown.value = None
        loan_reason_field.value = ""
        loan_feedback.value = "Added!"
        loan_feedback.color = ft.Colors.GREEN

        build_loans()
        build_home()
        page.update()
    invest_content = ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    INVESTMENT_TYPES = ["Stocks", "Mutual Fund", "FD", "Gold", "Crypto", "Real Estate", "Other"]

    invest_name_field = ft.TextField(label="Investment name", border_color=ft.Colors.OUTLINE)
    invest_type_dropdown = ft.Dropdown(
        label="Type", options=[ft.dropdown.Option(t) for t in INVESTMENT_TYPES], value="Other", border_color=ft.Colors.OUTLINE
    )
    invest_amount_field = ft.TextField(label="Amount invested", prefix=ft.Text("\u20b9"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    invest_account_dropdown = ft.Dropdown(label="From account", border_color=ft.Colors.OUTLINE)
    invest_feedback = ft.Text("", color=ft.Colors.GREEN)

    # Tracks which investments have their history expanded, e.g. {3: True}
    expanded_history = {}

    # --- Shared dialog: used for Buy More, Withdraw, and Update Value ---
    dialog_amount_field = ft.TextField(prefix=ft.Text("\u20b9"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    dialog_account_dropdown = ft.Dropdown(label="Account", border_color=ft.Colors.OUTLINE)
    dialog_error = ft.Text("", color=ft.Colors.RED)
    dialog_state = {"mode": None, "investment_id": None}  # mode: "buy", "withdraw", "update"

    def close_invest_dialog(e=None):
        page.pop_dialog()

    def confirm_invest_dialog(e):
        dialog_error.value = ""
        try:
            value = float(dialog_amount_field.value)
            if value <= 0:
                raise ValueError
        except (ValueError, TypeError):
            dialog_error.value = "Enter a valid amount"
            page.update()
            return

        mode = dialog_state["mode"]
        investment_id = dialog_state["investment_id"]

        if mode in ("buy", "withdraw") and not dialog_account_dropdown.value:
            dialog_error.value = "Pick an account"
            page.update()
            return

        try:
            if mode == "buy":
                db.buy_more_investment(investment_id, value, int(dialog_account_dropdown.value))
                invest_feedback.value = "Added to investment!"
            elif mode == "withdraw":
                realized_gain = db.withdraw_investment(investment_id, value, int(dialog_account_dropdown.value))
                sign = "+" if realized_gain >= 0 else ""
                invest_feedback.value = f"Withdrawn! Realized gain: {sign}\u20b9{realized_gain:,.2f}"
            elif mode == "update":
                db.update_investment_value(investment_id, value)
                invest_feedback.value = "Value updated!"
        except ValueError as err:
            dialog_error.value = str(err)
            page.update()
            return

        invest_feedback.color = ft.Colors.GREEN
        page.pop_dialog()
        build_invest()
        build_home()
        page.update()

    invest_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(""),
        content=ft.Column([dialog_amount_field, dialog_account_dropdown, dialog_error], tight=True, spacing=12),
        actions=[
            ft.TextButton("Cancel", on_click=close_invest_dialog),
            ft.TextButton("Confirm", on_click=confirm_invest_dialog),
        ],
    )

    def open_invest_dialog(mode, investment_id, current_value=None):
        dialog_state["mode"] = mode
        dialog_state["investment_id"] = investment_id
        dialog_error.value = ""
        dialog_amount_field.value = str(current_value) if mode == "update" else ""

        titles = {"buy": "Buy More", "withdraw": "Withdraw", "update": "Update Current Value"}
        labels = {"buy": "Amount to add", "withdraw": "Amount to withdraw", "update": "New current value"}
        invest_dialog.title = ft.Text(titles[mode])
        dialog_amount_field.label = labels[mode]

        if mode == "update":
            dialog_account_dropdown.visible = False
        else:
            dialog_account_dropdown.visible = True
            dialog_account_dropdown.value = None
            dialog_account_dropdown.options = [
                ft.dropdown.Option(key=str(a_id), text=name) for (a_id, name, _bal) in db.get_bank_accounts()
            ]
            set_default_account(dialog_account_dropdown)

        page.show_dialog(invest_dialog)

    def toggle_history(investment_id):
        expanded_history[investment_id] = not expanded_history.get(investment_id, False)
        build_invest()

    def build_invest():
        invest_content.controls.clear()

        total_invested, total_current, gain_loss = db.get_investment_totals()
        gain_color = ft.Colors.GREEN if gain_loss >= 0 else ft.Colors.RED
        gain_pct = (gain_loss / total_invested * 100) if total_invested else 0

        totals_card = card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("Invested", size=12, color=ft.Colors.GREY),
                                    ft.Text(f"\u20b9{total_invested:,.2f}", size=18, weight=ft.FontWeight.BOLD),
                                ]
                            ),
                            ft.Column(
                                [
                                    ft.Text("Current Value", size=12, color=ft.Colors.GREY),
                                    ft.Text(f"\u20b9{total_current:,.2f}", size=18, weight=ft.FontWeight.BOLD),
                                ]
                            ),
                        ],
                        spacing=40,
                    ),
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.TRENDING_UP if gain_loss >= 0 else ft.Icons.TRENDING_DOWN,
                                color=gain_color,
                            ),
                            ft.Text(
                                f"{'+' if gain_loss >= 0 else ''}\u20b9{gain_loss:,.2f} ({gain_pct:+.1f}%)",
                                color=gain_color,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ]
                    ),
                ],
                spacing=10,
            )
        )

        invest_account_dropdown.options = [
            ft.dropdown.Option(key=str(a_id), text=name) for (a_id, name, _bal) in db.get_bank_accounts()
        ]
        set_default_account(invest_account_dropdown)
        new_invest_card = card(
            ft.Column(
                [
                    ft.Text("Add Investment", size=14, color=ft.Colors.GREY),
                    invest_name_field,
                    invest_type_dropdown,
                    invest_amount_field,
                    invest_account_dropdown,
                    ft.ElevatedButton("Add", on_click=submit_investment, width=200),
                    invest_feedback,
                ],
                spacing=12,
            )
        )

        def history_rows(investment_id):
            txns = db.get_investment_transactions(investment_id)
            if not txns:
                return [ft.Text("No history yet", size=12, color=ft.Colors.GREY)]
            rows = []
            for t in txns:
                if t["type"] == "buy":
                    line = f"Bought \u20b9{t['amount']:,.2f} via {t['account_name']}"
                    color = ft.Colors.GREY
                else:
                    gain_txt = f" (gain {'+' if t['realized_gain'] >= 0 else ''}\u20b9{t['realized_gain']:,.2f})"
                    line = f"Withdrew \u20b9{t['amount']:,.2f} to {t['account_name']}{gain_txt}"
                    color = ft.Colors.GREEN if t["realized_gain"] >= 0 else ft.Colors.RED
                rows.append(
                    ft.Row(
                        [
                            ft.Text(line, size=12, color=color, expand=True),
                            ft.Text(t["date"], size=11, color=ft.Colors.GREY),
                        ]
                    )
                )
            return rows

        def investment_row(inv):
            gl = inv["current_value"] - inv["amount_invested"]
            gl_color = ft.Colors.GREEN if gl >= 0 else ft.Colors.RED
            gl_pct = (gl / inv["amount_invested"] * 100) if inv["amount_invested"] else 0
            is_expanded = expanded_history.get(inv["id"], False)

            main_row = ft.Row(
                [
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(inv["name"], weight=ft.FontWeight.W_600),
                                    ft.Container(
                                        content=ft.Text(inv["type"], size=10, color=ft.Colors.WHITE),
                                        bgcolor=ft.Colors.BLUE,
                                        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                                        border_radius=8,
                                    ),
                                ],
                                spacing=8,
                            ),
                            ft.Text(f"Invested \u20b9{inv['amount_invested']:,.2f} \u00b7 {inv['date_added']}", size=12, color=ft.Colors.GREY),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    ft.Column(
                        [
                            ft.Text(f"\u20b9{inv['current_value']:,.2f}", weight=ft.FontWeight.BOLD),
                            ft.Text(f"{'+' if gl >= 0 else ''}{gl_pct:.1f}%", size=12, color=gl_color),
                            ft.PopupMenuButton(
                                icon=ft.Icons.MORE_VERT,
                                items=[
                                    ft.PopupMenuItem(content=ft.Text("Buy More"), on_click=lambda e, iid=inv["id"]: open_invest_dialog("buy", iid)),
                                    ft.PopupMenuItem(content=ft.Text("Withdraw"), on_click=lambda e, iid=inv["id"]: open_invest_dialog("withdraw", iid)),
                                    ft.PopupMenuItem(content=ft.Text("Update Value"), on_click=lambda e, iid=inv["id"], cv=inv["current_value"]: open_invest_dialog("update", iid, cv)),
                                ],
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                        spacing=2,
                    ),
                ]
            )

            history_toggle = ft.TextButton(
                "Hide History" if is_expanded else "View History",
                on_click=lambda e, iid=inv["id"]: toggle_history(iid),
            )

            content_controls = [main_row, history_toggle]
            if is_expanded:
                content_controls.append(ft.Column(history_rows(inv["id"]), spacing=4))

            return ft.Container(
                content=ft.Column(content_controls, spacing=4),
                padding=ft.Padding.symmetric(vertical=6),
            )

        investments = db.get_investments()
        rows = [investment_row(i) for i in investments] or [ft.Text("No investments yet", color=ft.Colors.GREY)]
        list_card = card(
            ft.Column([ft.Text("Your Investments", size=14, color=ft.Colors.GREY), ft.Divider(height=1)] + rows, spacing=4)
        )

        invest_content.controls.extend([totals_card, new_invest_card, list_card])
        page.update()

    def submit_investment(e):
        invest_feedback.value = ""
        try:
            amount = float(invest_amount_field.value)
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            invest_amount_field.error_text = "Enter a valid amount"
            page.update()
            return

        if not invest_name_field.value:
            invest_feedback.value = "Enter an investment name"
            invest_feedback.color = ft.Colors.RED
            page.update()
            return

        if not invest_account_dropdown.value:
            invest_feedback.value = "Pick an account"
            invest_feedback.color = ft.Colors.RED
            page.update()
            return

        db.add_investment(
            name=invest_name_field.value,
            amount_invested=amount,
            account_id=int(invest_account_dropdown.value),
            investment_type=invest_type_dropdown.value or "Other",
        )

        invest_name_field.value = ""
        invest_amount_field.value = ""
        invest_amount_field.error_text = None
        invest_account_dropdown.value = None
        invest_type_dropdown.value = "Other"
        invest_feedback.value = "Added!"
        invest_feedback.color = ft.Colors.GREEN

        build_invest()
        build_home()
        page.update()

    stats_content = placeholder("Stats \u2014 coming next stage")

    # ---------------------------------------------------------------
    # NAVIGATION
    # ---------------------------------------------------------------
    body = ft.Container(content=home_content, padding=16, expand=True)

    views = [home_content, add_content, loans_content, invest_content, stats_content]

    def on_nav_change(e):
        index = e.control.selected_index
        if index == 0:
            build_home()
        elif index == 2:
            build_loans()
        elif index == 3:
            build_invest()
        refresh_account_dropdown()
        body.content = views[index]
        page.update()

    nav_bar = ft.NavigationBar(
        selected_index=0,
        on_change=on_nav_change,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.HOME_OUTLINED, selected_icon=ft.Icons.HOME, label="Home"),
            ft.NavigationBarDestination(icon=ft.Icons.ADD_CIRCLE_OUTLINE, selected_icon=ft.Icons.ADD_CIRCLE, label="Add"),
            ft.NavigationBarDestination(icon=ft.Icons.PEOPLE_OUTLINE, selected_icon=ft.Icons.PEOPLE, label="Loans"),
            ft.NavigationBarDestination(icon=ft.Icons.TRENDING_UP_OUTLINED, selected_icon=ft.Icons.TRENDING_UP, label="Invest"),
            ft.NavigationBarDestination(icon=ft.Icons.BAR_CHART_OUTLINED, selected_icon=ft.Icons.BAR_CHART, label="Stats"),
        ],
    )

    theme_icon_button = ft.IconButton(icon=ft.Icons.DARK_MODE_OUTLINED)

    def toggle_theme(e):
        if page.theme_mode == ft.ThemeMode.LIGHT:
            page.theme_mode = ft.ThemeMode.DARK
            theme_icon_button.icon = ft.Icons.LIGHT_MODE_OUTLINED
        else:
            page.theme_mode = ft.ThemeMode.LIGHT
            theme_icon_button.icon = ft.Icons.DARK_MODE_OUTLINED
        page.update()

    theme_icon_button.on_click = toggle_theme

    page.appbar = ft.AppBar(
        title=ft.Text("Finance Tracker"),
        actions=[theme_icon_button],
    )
    page.navigation_bar = nav_bar

    refresh_account_dropdown()
    build_home()
    page.add(body)


ft.run(main)