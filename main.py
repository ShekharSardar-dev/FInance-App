import flet as ft
import flet_charts as fch
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

        page.pop_dialog()
        if pin_state["on_success"]:
            pin_state["on_success"]()
        else:
            revealed_accounts[pin_state["account_id"]] = True
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

    def open_pin_dialog(account_id=None, on_success=None):
        pin_state["account_id"] = account_id
        pin_state["on_success"] = on_success
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

    def actually_save_new_bank():
        db.add_account(
            name=new_bank_name_field.value,
            starting_balance=float(new_bank_balance_field.value),
            category="bank",
            account_type=new_bank_type_dropdown.value,
            account_number=new_bank_number_field.value or None,
        )
        new_bank_name_field.value = ""
        new_bank_type_dropdown.value = None
        new_bank_number_field.value = ""
        new_bank_balance_field.value = ""
        build_home()

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

        # Form is valid \u2014 close this dialog and require the PIN before
        # the bank account (with its account number) actually gets saved.
        page.pop_dialog()
        open_pin_dialog(on_success=actually_save_new_bank)

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

    # --- Edit Account dialog (reused for any account) ---
    edit_acc_name_field = ft.TextField(label="Name", border_color=ft.Colors.OUTLINE)
    edit_acc_type_dropdown = ft.Dropdown(
        label="Account type",
        options=[ft.dropdown.Option("Savings"), ft.dropdown.Option("Current")],
        border_color=ft.Colors.OUTLINE,
    )
    edit_acc_number_field = ft.TextField(label="Account number", border_color=ft.Colors.OUTLINE)
    edit_acc_balance_field = ft.TextField(label="Balance", prefix=ft.Text("\u20b9"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    edit_acc_error = ft.Text("", color=ft.Colors.RED)
    edit_acc_state = {"id": None}

    def close_edit_account_dialog(e=None):
        page.pop_dialog()

    def confirm_edit_account(e):
        edit_acc_error.value = ""
        try:
            balance = float(edit_acc_balance_field.value)
        except (ValueError, TypeError):
            edit_acc_error.value = "Enter a valid balance"
            page.update()
            return
        if not edit_acc_name_field.value:
            edit_acc_error.value = "Enter a name"
            page.update()
            return

        db.update_account(
            edit_acc_state["id"],
            name=edit_acc_name_field.value,
            account_type=edit_acc_type_dropdown.value,
            account_number=edit_acc_number_field.value or None,
            balance=balance,
        )
        page.pop_dialog()
        build_home()
        page.update()

    edit_account_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Edit Account"),
        content=ft.Column(
            [edit_acc_name_field, edit_acc_type_dropdown, edit_acc_number_field, edit_acc_balance_field, edit_acc_error],
            tight=True,
            spacing=12,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=close_edit_account_dialog),
            ft.TextButton("Save", on_click=confirm_edit_account),
        ],
    )

    def show_edit_account_dialog(acc):
        edit_acc_state["id"] = acc["id"]
        edit_acc_name_field.value = acc["name"]
        edit_acc_balance_field.value = str(acc["balance"])
        edit_acc_error.value = ""
        is_bank = acc["category"] == "bank"
        edit_acc_type_dropdown.visible = is_bank
        edit_acc_number_field.visible = is_bank
        edit_acc_type_dropdown.value = acc["account_type"]
        edit_acc_number_field.value = acc["account_number"] or ""
        page.show_dialog(edit_account_dialog)

    def open_edit_account_dialog(acc):
        # Require the PIN before even opening the edit form, since it
        # shows the full account number.
        open_pin_dialog(on_success=lambda: show_edit_account_dialog(acc))

    # --- Delete Account confirmation ---
    delete_acc_error = ft.Text("", color=ft.Colors.RED)
    delete_acc_state = {"id": None, "name": None}

    def close_delete_account_dialog(e=None):
        page.pop_dialog()

    def confirm_delete_account(e):
        try:
            db.delete_account(delete_acc_state["id"])
        except ValueError as err:
            delete_acc_error.value = str(err)
            page.update()
            return
        page.pop_dialog()
        build_home()
        page.update()

    delete_account_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Delete Account"),
        content=ft.Column([ft.Text(""), delete_acc_error], tight=True, spacing=12),
        actions=[
            ft.TextButton("Cancel", on_click=close_delete_account_dialog),
            ft.TextButton("Delete", on_click=confirm_delete_account),
        ],
    )

    def open_delete_account_dialog(acc):
        delete_acc_state["id"] = acc["id"]
        delete_acc_state["name"] = acc["name"]
        delete_acc_error.value = ""
        delete_account_dialog.content = ft.Column(
            [ft.Text(f"Delete '{acc['name']}'? This can't be undone."), delete_acc_error],
            tight=True,
            spacing=12,
        )
        page.show_dialog(delete_account_dialog)

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
                        ft.PopupMenuButton(
                            icon=ft.Icons.MORE_VERT,
                            items=[
                                ft.PopupMenuItem(content=ft.Text("Edit"), on_click=lambda e, a=acc: open_edit_account_dialog(a)),
                                ft.PopupMenuItem(content=ft.Text("Delete"), on_click=lambda e, a=acc: open_delete_account_dialog(a)),
                            ],
                        ),
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

    EXPENSE_CATEGORIES = db.get_category_names("expense")
    INCOME_CATEGORIES = db.get_category_names("income")

    def reload_categories():
        """Re-reads the lists from the database IN PLACE, so every dropdown
        and function that already points at these lists sees the change."""
        EXPENSE_CATEGORIES[:] = db.get_category_names("expense")
        INCOME_CATEGORIES[:] = db.get_category_names("income")

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

    def _set_dropdown_options(dropdown, names):
        dropdown.options = [ft.dropdown.Option(c) for c in names]
        if dropdown.value not in names:
            dropdown.value = None  # the selected category was deleted

    def refresh_category_dropdowns():
        reload_categories()
        add_is_income = type_toggle.selected_index == 0
        _set_dropdown_options(category_dropdown, INCOME_CATEGORIES if add_is_income else EXPENSE_CATEGORIES)
        rec_is_income = recurring_type_toggle.selected_index == 0
        _set_dropdown_options(recurring_category_dropdown, INCOME_CATEGORIES if rec_is_income else EXPENSE_CATEGORIES)
        _set_dropdown_options(budget_category_dropdown, EXPENSE_CATEGORIES)

    def refresh_account_dropdown():
        account_dropdown.options = [
            ft.dropdown.Option(key=str(a_id), text=name) for (a_id, name, _bal) in db.get_accounts()
        ]
        set_default_account(account_dropdown)
        refresh_category_dropdowns()
        refresh_recurring_chips()

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

    recurring_chips_row = ft.Row(wrap=True, spacing=8)

    def apply_recurring_item(item):
        is_income = item["type"] == "income"
        type_toggle.selected_index = 0 if is_income else 1
        cat_list = INCOME_CATEGORIES if is_income else EXPENSE_CATEGORIES
        category_dropdown.options = [ft.dropdown.Option(c) for c in cat_list]
        category_dropdown.value = item["category"] if item["category"] in cat_list else None
        counterparty_field.label = "Received From (optional)" if is_income else "Paid To (optional)"
        account_dropdown.label = "Received In" if is_income else "Paid Via"
        amount_field.value = str(item["amount"])
        account_dropdown.value = str(item["account_id"])
        page.update()

    def refresh_recurring_chips():
        items = db.get_recurring_items()
        chips = [
            ft.Container(
                content=ft.Text(f"{item['name']} \u20b9{item['amount']:,.0f}", size=12, color=ft.Colors.WHITE),
                bgcolor=ft.Colors.GREEN if item["type"] == "income" else ft.Colors.BLUE,
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                border_radius=16,
                on_click=lambda e, it=item: apply_recurring_item(it),
                ink=True,
            )
            for item in items
        ] or [ft.Text("No recurring items yet \u2014 add some in Settings", size=12, color=ft.Colors.GREY)]

        recurring_chips_row.controls.clear()
        recurring_chips_row.controls.extend(chips)

    add_content = ft.Column(
        [
            ft.Text("Add Transaction", size=22, weight=ft.FontWeight.BOLD),
            card(
                ft.Column(
                    [
                        ft.Text("Quick Add", size=12, color=ft.Colors.GREY),
                        recurring_chips_row,
                        ft.Divider(height=1),
                        type_toggle,
                        amount_field,
                        account_dropdown,
                        category_dropdown,
                        counterparty_field,
                        note_field,
                        ft.Button("Add", on_click=submit_transaction, width=200),
                        add_feedback,
                    ],
                    spacing=16,
                )
            ),
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
                    ft.Button("Add", on_click=submit_loan, width=200),
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

    # --- Edit Investment dialog (name + type only) ---
    edit_inv_name_field = ft.TextField(label="Investment name", border_color=ft.Colors.OUTLINE)
    edit_inv_type_dropdown = ft.Dropdown(
        label="Type", options=[ft.dropdown.Option(t) for t in INVESTMENT_TYPES], border_color=ft.Colors.OUTLINE
    )
    edit_inv_error = ft.Text("", color=ft.Colors.RED)
    edit_inv_state = {"id": None}

    def close_edit_invest_dialog(e=None):
        page.pop_dialog()

    def confirm_edit_invest(e):
        if not edit_inv_name_field.value:
            edit_inv_error.value = "Enter a name"
            page.update()
            return
        db.update_investment_details(
            edit_inv_state["id"],
            name=edit_inv_name_field.value,
            investment_type=edit_inv_type_dropdown.value,
        )
        page.pop_dialog()
        build_invest()
        page.update()

    edit_invest_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Edit Investment"),
        content=ft.Column([edit_inv_name_field, edit_inv_type_dropdown, edit_inv_error], tight=True, spacing=12),
        actions=[
            ft.TextButton("Cancel", on_click=close_edit_invest_dialog),
            ft.TextButton("Save", on_click=confirm_edit_invest),
        ],
    )

    def open_edit_invest_dialog(inv):
        edit_inv_state["id"] = inv["id"]
        edit_inv_name_field.value = inv["name"]
        edit_inv_type_dropdown.value = inv["type"]
        edit_inv_error.value = ""
        page.show_dialog(edit_invest_dialog)

    # --- Delete Investment confirmation ---
    delete_inv_state = {"id": None}

    def close_delete_invest_dialog(e=None):
        page.pop_dialog()

    def confirm_delete_invest(e):
        db.delete_investment(delete_inv_state["id"])
        page.pop_dialog()
        build_invest()
        build_home()
        page.update()

    delete_invest_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Delete Investment"),
        content=ft.Text(""),
        actions=[
            ft.TextButton("Cancel", on_click=close_delete_invest_dialog),
            ft.TextButton("Delete", on_click=confirm_delete_invest),
        ],
    )

    def open_delete_invest_dialog(inv):
        delete_inv_state["id"] = inv["id"]
        delete_invest_dialog.content = ft.Text(
            f"Delete '{inv['name']}'? Any money moved into/out of it will be returned to the original accounts."
        )
        page.show_dialog(delete_invest_dialog)

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
                    ft.Button("Add", on_click=submit_investment, width=200),
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
                                    ft.PopupMenuItem(content=ft.Text("Edit Details"), on_click=lambda e, i=inv: open_edit_invest_dialog(i)),
                                    ft.PopupMenuItem(content=ft.Text("Delete"), on_click=lambda e, i=inv: open_delete_invest_dialog(i)),
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

    stats_content = ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    CATEGORY_COLORS = [
        ft.Colors.BLUE, ft.Colors.ORANGE, ft.Colors.PURPLE, ft.Colors.TEAL,
        ft.Colors.PINK, ft.Colors.INDIGO, ft.Colors.AMBER, ft.Colors.CYAN,
    ]

    def category_color(category, all_categories):
        idx = all_categories.index(category) if category in all_categories else 0
        return CATEGORY_COLORS[idx % len(CATEGORY_COLORS)]

    # --- Add Budget dialog ---
    budget_category_dropdown = ft.Dropdown(
        label="Category",
        options=[ft.dropdown.Option(c) for c in EXPENSE_CATEGORIES],
        border_color=ft.Colors.OUTLINE,
    )
    budget_limit_field = ft.TextField(label="Monthly limit", prefix=ft.Text("\u20b9"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    budget_error = ft.Text("", color=ft.Colors.RED)

    def close_budget_dialog(e=None):
        page.pop_dialog()

    def confirm_budget(e):
        budget_error.value = ""
        try:
            limit = float(budget_limit_field.value)
            if limit <= 0:
                raise ValueError
        except (ValueError, TypeError):
            budget_error.value = "Enter a valid amount"
            page.update()
            return
        if not budget_category_dropdown.value:
            budget_error.value = "Pick a category"
            page.update()
            return

        db.set_budget(budget_category_dropdown.value, limit)
        budget_category_dropdown.value = None
        budget_limit_field.value = ""
        page.pop_dialog()
        build_stats()
        page.update()

    budget_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Set Budget"),
        content=ft.Column([budget_category_dropdown, budget_limit_field, budget_error], tight=True, spacing=12),
        actions=[
            ft.TextButton("Cancel", on_click=close_budget_dialog),
            ft.TextButton("Save", on_click=confirm_budget),
        ],
    )

    def open_budget_dialog(e=None):
        budget_error.value = ""
        page.show_dialog(budget_dialog)

    def delete_budget_clicked(budget_id):
        db.delete_budget(budget_id)
        build_stats()

    # --- Category transactions dialog (tap a category to see what's in it) ---
    category_txns_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(""),
        content=ft.Column([], tight=True, scroll=ft.ScrollMode.AUTO, height=300),
        actions=[ft.TextButton("Close", on_click=lambda e: page.pop_dialog())],
    )

    def open_category_txns_dialog(category):
        txns = db.get_transactions_by_category(category)
        category_txns_dialog.title = ft.Text(f"{category} \u2014 This Month")

        if not txns:
            rows = [ft.Text("No transactions found", color=ft.Colors.GREY)]
        else:
            rows = []
            for t in txns:
                rows.append(
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(t["note"] or "No note", size=13),
                                    ft.Text(f"{t['account_name']} \u00b7 {t['date']}", size=11, color=ft.Colors.GREY),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Text(f"\u20b9{t['amount']:,.2f}", weight=ft.FontWeight.BOLD, color=ft.Colors.RED),
                        ]
                    )
                )
                rows.append(ft.Divider(height=1))

        category_txns_dialog.content = ft.Column(rows, tight=True, scroll=ft.ScrollMode.AUTO, height=300, spacing=8)
        page.show_dialog(category_txns_dialog)

    def build_stats():
        stats_content.controls.clear()

        # --- Net worth snapshot ---
        nw = db.get_net_worth()
        net_worth_card = card(
            ft.Column(
                [
                    ft.Text("Net Worth", size=14, color=ft.Colors.GREY),
                    ft.Text(f"\u20b9{nw['net_worth']:,.2f}", size=24, weight=ft.FontWeight.BOLD),
                    ft.Divider(height=1),
                    ft.Row([ft.Text("Bank + Cash", size=12, color=ft.Colors.GREY, expand=True), ft.Text(f"\u20b9{nw['cash_and_bank']:,.2f}", size=12)]),
                    ft.Row([ft.Text("Investments", size=12, color=ft.Colors.GREY, expand=True), ft.Text(f"\u20b9{nw['investments_value']:,.2f}", size=12)]),
                    ft.Row([ft.Text("Owed to you", size=12, color=ft.Colors.GREY, expand=True), ft.Text(f"+\u20b9{nw['owed_to_you']:,.2f}", size=12, color=ft.Colors.GREEN)]),
                    ft.Row([ft.Text("You owe", size=12, color=ft.Colors.GREY, expand=True), ft.Text(f"-\u20b9{nw['you_owe']:,.2f}", size=12, color=ft.Colors.RED)]),
                ],
                spacing=8,
            )
        )

        # --- Savings rate ---
        income, expense, net = db.get_monthly_cash_flow()
        savings_rate = (net / income * 100) if income else 0
        savings_color = ft.Colors.GREEN if savings_rate >= 0 else ft.Colors.RED
        savings_card = card(
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text("Savings Rate (This Month)", size=14, color=ft.Colors.GREY),
                            ft.Text(f"{savings_rate:.0f}%", size=24, weight=ft.FontWeight.BOLD, color=savings_color),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    ft.Text(
                        f"You kept \u20b9{net:,.2f} of \u20b9{income:,.2f} earned" if income else "No income recorded yet this month",
                        size=12,
                        color=ft.Colors.GREY,
                    ),
                ]
            )
        )

        # --- Category breakdown pie chart ---
        spending = db.get_category_spending()
        categories = [c for c, _ in spending]
        total_spent = sum(amt for _, amt in spending)

        prev_month = db.shift_month(1)
        prev_spending = dict(db.get_category_spending(prev_month))

        if spending:
            sections = []
            legend_rows = []
            for cat, amt in spending:
                color = category_color(cat, categories)
                pct = (amt / total_spent * 100) if total_spent else 0
                sections.append(
                    fch.PieChartSection(
                        value=amt,
                        color=color,
                        radius=60,
                        title=f"{pct:.0f}%",
                        title_style=ft.TextStyle(size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    )
                )

                prev_amt = prev_spending.get(cat, 0)
                if prev_amt:
                    change = (amt - prev_amt) / prev_amt * 100
                    change_text = f"{'\u2191' if change >= 0 else '\u2193'}{abs(change):.0f}%"
                    change_color = ft.Colors.RED if change >= 0 else ft.Colors.GREEN
                else:
                    change_text = "New"
                    change_color = ft.Colors.GREY

                legend_rows.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(width=10, height=10, bgcolor=color, border_radius=5),
                                ft.Text(cat, size=12, expand=True),
                                ft.Text(change_text, size=11, color=change_color),
                                ft.Text(f"\u20b9{amt:,.2f}", size=12, weight=ft.FontWeight.BOLD),
                            ],
                            spacing=8,
                        ),
                        on_click=lambda e, c=cat: open_category_txns_dialog(c),
                        ink=True,
                        border_radius=6,
                        padding=ft.Padding.symmetric(vertical=2),
                    )
                )

            pie_chart = fch.PieChart(
                sections=sections,
                sections_space=2,
                center_space_radius=30,
                height=220,
            )
            category_card = card(
                ft.Column(
                    [
                        ft.Text("Spending by Category (This Month)", size=14, color=ft.Colors.GREY),
                        pie_chart,
                        ft.Column(legend_rows, spacing=6),
                    ],
                    spacing=12,
                )
            )
        else:
            category_card = card(
                ft.Column(
                    [
                        ft.Text("Spending by Category (This Month)", size=14, color=ft.Colors.GREY),
                        ft.Text("No expenses recorded yet this month", color=ft.Colors.GREY),
                    ],
                    spacing=8,
                )
            )

        # --- Cash flow trend (last 6 months) ---
        trend = db.get_cash_flow_trend(months=6)
        max_val = max([max(inc, exp) for (_ym, inc, exp) in trend] + [1])

        month_labels = []
        groups = []
        for i, (ym, income, expense) in enumerate(trend):
            year, month = ym.split("-")
            month_name = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(month) - 1]
            month_labels.append(fch.ChartAxisLabel(value=i, label=ft.Text(month_name, size=11)))
            groups.append(
                fch.BarChartGroup(
                    x=i,
                    rods=[
                        fch.BarChartRod(from_y=0, to_y=income, color=ft.Colors.GREEN, width=10, border_radius=ft.BorderRadius.all(3)),
                        fch.BarChartRod(from_y=0, to_y=expense, color=ft.Colors.RED, width=10, border_radius=ft.BorderRadius.all(3)),
                    ],
                )
            )

        trend_chart = fch.BarChart(
            groups=groups,
            max_y=max_val * 1.2,
            height=220,
            bottom_axis=fch.ChartAxis(labels=month_labels, label_size=24),
            border=ft.Border.all(1, ft.Colors.OUTLINE),
        )
        trend_card = card(
            ft.Column(
                [
                    ft.Text("Cash Flow Trend (Last 6 Months)", size=14, color=ft.Colors.GREY),
                    trend_chart,
                    ft.Row(
                        [
                            ft.Row([ft.Container(width=10, height=10, bgcolor=ft.Colors.GREEN, border_radius=5), ft.Text("Income", size=12)], spacing=6),
                            ft.Row([ft.Container(width=10, height=10, bgcolor=ft.Colors.RED, border_radius=5), ft.Text("Expense", size=12)], spacing=6),
                        ],
                        spacing=20,
                    ),
                ],
                spacing=12,
            )
        )

        # --- Top 5 biggest expenses this month ---
        top_expenses = db.get_top_expenses(limit=5)
        top_rows = []
        for t in top_expenses:
            top_rows.append(
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(t["category"], weight=ft.FontWeight.W_600, size=13),
                                ft.Text(f"{t['note'] or 'No note'} \u00b7 {t['date']}", size=11, color=ft.Colors.GREY),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Text(f"\u20b9{t['amount']:,.2f}", weight=ft.FontWeight.BOLD, color=ft.Colors.RED),
                    ]
                )
            )
            top_rows.append(ft.Divider(height=1))

        top_expenses_card = card(
            ft.Column(
                [ft.Text("Top 5 Expenses (This Month)", size=14, color=ft.Colors.GREY)]
                + (top_rows if top_expenses else [ft.Text("No expenses yet", color=ft.Colors.GREY)]),
                spacing=8,
            )
        )

        # --- Budgets ---
        budgets = db.get_budgets()

        def budget_row(b):
            progress = min(b["spent"] / b["monthly_limit"], 1) if b["monthly_limit"] else 0
            if b["spent"] >= b["monthly_limit"]:
                bar_color = ft.Colors.RED
            elif progress >= 0.7:
                bar_color = ft.Colors.ORANGE
            else:
                bar_color = ft.Colors.GREEN

            return ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(b["category"], weight=ft.FontWeight.W_600, expand=True),
                            ft.Text(f"\u20b9{b['spent']:,.2f} / \u20b9{b['monthly_limit']:,.2f}", size=12, color=ft.Colors.GREY),
                            ft.IconButton(icon=ft.Icons.CLOSE, icon_size=16, on_click=lambda e, bid=b["id"]: (delete_budget_clicked(bid), page.update())),
                        ]
                    ),
                    ft.ProgressBar(value=progress, color=bar_color, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST),
                ],
                spacing=4,
            )

        budget_rows = [budget_row(b) for b in budgets] or [ft.Text("No budgets set yet", color=ft.Colors.GREY)]
        budgets_card = card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Budgets", size=14, color=ft.Colors.GREY, expand=True),
                            ft.TextButton("+ Set Budget", on_click=open_budget_dialog),
                        ]
                    ),
                    ft.Divider(height=1),
                ]
                + budget_rows,
                spacing=12,
            )
        )

        stats_content.controls.extend([net_worth_card, savings_card, category_card, top_expenses_card, trend_card, budgets_card])
        page.update()

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
        elif index == 4:
            build_stats()
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

    # Hidden until the app is unlocked (or immediately if no PIN exists yet)
    settings_icon_button = ft.IconButton(icon=ft.Icons.SETTINGS_OUTLINED, visible=False)

    page.appbar = ft.AppBar(
        title=ft.Text("Finance Tracker"),
        actions=[settings_icon_button],
    )
    page.navigation_bar = nav_bar

    # ---------------------------------------------------------------
    # FIRST-RUN SETUP
    # ---------------------------------------------------------------
    onboarding_cash_field = ft.TextField(label="Cash in hand", prefix=ft.Text("\u20b9"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    onboarding_banks_list = ft.Column(spacing=8)
    onboarding_error = ft.Text("", color=ft.Colors.RED)

    onboard_bank_name_field = ft.TextField(label="Bank name", border_color=ft.Colors.OUTLINE)
    onboard_bank_type_dropdown = ft.Dropdown(
        label="Account type", options=[ft.dropdown.Option("Savings"), ft.dropdown.Option("Current")], border_color=ft.Colors.OUTLINE
    )
    onboard_bank_number_field = ft.TextField(label="Account number (optional)", border_color=ft.Colors.OUTLINE)
    onboard_bank_balance_field = ft.TextField(label="Available balance", prefix=ft.Text("\u20b9"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    onboard_bank_error = ft.Text("", color=ft.Colors.RED)

    def close_onboard_bank_dialog(e=None):
        page.pop_dialog()

    def actually_save_onboard_bank():
        db.add_account(
            name=onboard_bank_name_field.value,
            starting_balance=float(onboard_bank_balance_field.value),
            category="bank",
            account_type=onboard_bank_type_dropdown.value,
            account_number=onboard_bank_number_field.value or None,
        )
        onboard_bank_name_field.value = ""
        onboard_bank_type_dropdown.value = None
        onboard_bank_number_field.value = ""
        onboard_bank_balance_field.value = ""
        render_onboarding()

    def confirm_onboard_bank(e):
        onboard_bank_error.value = ""
        if not onboard_bank_name_field.value:
            onboard_bank_error.value = "Enter a bank name"
            page.update()
            return
        try:
            balance = float(onboard_bank_balance_field.value)
            if balance < 0:
                raise ValueError
        except (ValueError, TypeError):
            onboard_bank_error.value = "Enter a valid balance"
            page.update()
            return

        page.pop_dialog()
        open_pin_dialog(on_success=actually_save_onboard_bank)

    onboard_bank_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Add Bank Account"),
        content=ft.Column(
            [onboard_bank_name_field, onboard_bank_type_dropdown, onboard_bank_number_field, onboard_bank_balance_field, onboard_bank_error],
            tight=True,
            spacing=12,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=close_onboard_bank_dialog),
            ft.TextButton("Add", on_click=confirm_onboard_bank),
        ],
    )

    def open_onboard_bank_dialog(e=None):
        onboard_bank_error.value = ""
        page.show_dialog(onboard_bank_dialog)

    def finish_setup(e):
        onboarding_error.value = ""
        try:
            cash_value = float(onboarding_cash_field.value) if onboarding_cash_field.value else 0
            if cash_value < 0:
                raise ValueError
        except (ValueError, TypeError):
            onboarding_error.value = "Enter a valid cash amount"
            page.update()
            return

        db.add_account(name="Cash", starting_balance=cash_value, category="cash")
        db.mark_setup_complete()

        page.controls.clear()
        page.navigation_bar = nav_bar
        settings_icon_button.visible = True
        refresh_account_dropdown()
        build_home()
        page.add(body)
        page.update()

    onboarding_view = ft.Container(padding=20, expand=True)

    # --- Shared "Add Recurring Item" dialog (used by onboarding and Settings) ---
    recurring_name_field = ft.TextField(label="Name (e.g. Rent, Salary, Netflix)", border_color=ft.Colors.OUTLINE)
    recurring_type_toggle = ft.CupertinoSlidingSegmentedButton(
        selected_index=1, controls=[ft.Text("Income"), ft.Text("Expense")]
    )
    recurring_amount_field = ft.TextField(label="Amount", prefix=ft.Text("\u20b9"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    recurring_category_dropdown = ft.Dropdown(
        label="Category", options=[ft.dropdown.Option(c) for c in EXPENSE_CATEGORIES], border_color=ft.Colors.OUTLINE
    )
    recurring_account_dropdown = ft.Dropdown(label="Account", border_color=ft.Colors.OUTLINE)
    recurring_error = ft.Text("", color=ft.Colors.RED)
    recurring_dialog_state = {"on_success": None}

    def on_recurring_type_change(e):
        is_income = recurring_type_toggle.selected_index == 0
        recurring_category_dropdown.options = [
            ft.dropdown.Option(c) for c in (INCOME_CATEGORIES if is_income else EXPENSE_CATEGORIES)
        ]
        recurring_category_dropdown.value = None
        page.update()

    recurring_type_toggle.on_change = on_recurring_type_change

    def close_add_recurring_dialog(e=None):
        page.pop_dialog()

    def confirm_add_recurring(e):
        recurring_error.value = ""
        if not recurring_name_field.value:
            recurring_error.value = "Enter a name"
            page.update()
            return
        try:
            amount = float(recurring_amount_field.value)
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            recurring_error.value = "Enter a valid amount"
            page.update()
            return
        if not recurring_category_dropdown.value:
            recurring_error.value = "Pick a category"
            page.update()
            return
        if not recurring_account_dropdown.value:
            recurring_error.value = "Pick an account"
            page.update()
            return

        type_ = "income" if recurring_type_toggle.selected_index == 0 else "expense"
        db.add_recurring_item(
            name=recurring_name_field.value,
            amount=amount,
            type_=type_,
            category=recurring_category_dropdown.value,
            account_id=int(recurring_account_dropdown.value),
        )

        recurring_name_field.value = ""
        recurring_amount_field.value = ""
        recurring_category_dropdown.value = None
        recurring_account_dropdown.value = None
        page.pop_dialog()
        if recurring_dialog_state["on_success"]:
            recurring_dialog_state["on_success"]()
        page.update()

    add_recurring_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Add Recurring Item"),
        content=ft.Column(
            [recurring_name_field, recurring_type_toggle, recurring_amount_field, recurring_category_dropdown, recurring_account_dropdown, recurring_error],
            tight=True,
            spacing=12,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=close_add_recurring_dialog),
            ft.TextButton("Add", on_click=confirm_add_recurring),
        ],
    )

    def open_add_recurring_dialog(on_success=None):
        refresh_category_dropdowns()
        recurring_error.value = ""
        recurring_account_dropdown.options = [
            ft.dropdown.Option(key=str(a_id), text=name) for (a_id, name, _bal) in db.get_accounts()
        ]
        set_default_account(recurring_account_dropdown)
        recurring_dialog_state["on_success"] = on_success
        page.show_dialog(add_recurring_dialog)

    def delete_recurring_item_clicked(item_id, on_success=None):
        db.delete_recurring_item(item_id)
        if on_success:
            on_success()

    def recurring_items_rows(on_change):
        items = db.get_recurring_items()
        if not items:
            return [ft.Text("No recurring items added yet (optional)", size=12, color=ft.Colors.GREY)]
        rows = []
        for item in items:
            color = ft.Colors.GREEN if item["type"] == "income" else ft.Colors.RED
            rows.append(
                ft.Row(
                    [
                        ft.Text(item["name"], weight=ft.FontWeight.W_600, expand=True),
                        ft.Text(f"\u20b9{item['amount']:,.2f}", size=13, color=color),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE, icon_size=16,
                            on_click=lambda e, iid=item["id"]: delete_recurring_item_clicked(iid, on_change),
                        ),
                    ]
                )
            )
        return rows

    def render_onboarding():
        bank_rows = [
            ft.Row(
                [
                    ft.Text(name, weight=ft.FontWeight.W_600, expand=True),
                    ft.Text(f"\u20b9{balance:,.2f}", size=13, color=ft.Colors.GREY),
                ]
            )
            for (_id, name, balance) in db.get_bank_accounts()
        ]

        onboarding_view.content = ft.Column(
            [
                ft.Text("Welcome!", size=26, weight=ft.FontWeight.BOLD),
                ft.Text("Let's set up your accounts to get started.", size=14, color=ft.Colors.GREY),
                ft.Container(height=10),
                card(
                    ft.Column(
                        [
                            ft.Text("Cash", size=14, color=ft.Colors.GREY),
                            onboarding_cash_field,
                        ],
                        spacing=8,
                    )
                ),
                card(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("Bank Accounts", size=14, color=ft.Colors.GREY, expand=True),
                                    ft.TextButton("+ Add Bank", on_click=open_onboard_bank_dialog),
                                ]
                            ),
                            ft.Divider(height=1),
                        ]
                        + (bank_rows or [ft.Text("No bank accounts added yet (optional)", size=12, color=ft.Colors.GREY)]),
                        spacing=8,
                    )
                ),
                card(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("Recurring Income & Expenses", size=14, color=ft.Colors.GREY, expand=True),
                                    ft.TextButton("+ Add Recurring", on_click=lambda e: open_add_recurring_dialog(on_success=render_onboarding)),
                                ]
                            ),
                            ft.Divider(height=1),
                        ]
                        + recurring_items_rows(render_onboarding),
                        spacing=8,
                    )
                ),
                onboarding_error,
                ft.Button("Finish Setup", on_click=finish_setup, width=200),
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
        )
        page.update()

    def proceed_after_unlock():
        settings_icon_button.visible = True
        if db.has_completed_setup():
            refresh_account_dropdown()
            build_home()
            page.navigation_bar = nav_bar
            page.add(body)
        else:
            render_onboarding()
            page.add(onboarding_view)
        page.update()

    # ---------------------------------------------------------------
    # RESET PIN (verified by entering a bank account number)
    # ---------------------------------------------------------------
    reset_pin_number_field = ft.TextField(label="Enter any of your bank account numbers", border_color=ft.Colors.OUTLINE)
    reset_pin_new_field = ft.TextField(label="New PIN", password=True, can_reveal_password=True, keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    reset_pin_confirm_field = ft.TextField(label="Confirm new PIN", password=True, can_reveal_password=True, keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    reset_pin_error = ft.Text("", color=ft.Colors.RED)
    reset_pin_state = {"on_success": None}

    def close_reset_pin_dialog(e=None):
        page.pop_dialog()

    def confirm_reset_pin(e):
        reset_pin_error.value = ""
        if not db.verify_account_number(reset_pin_number_field.value):
            reset_pin_error.value = "That account number doesn't match any account on file"
            page.update()
            return
        new_pin = reset_pin_new_field.value or ""
        if len(new_pin) < 4:
            reset_pin_error.value = "PIN must be at least 4 digits"
            page.update()
            return
        if new_pin != (reset_pin_confirm_field.value or ""):
            reset_pin_error.value = "PINs don't match"
            page.update()
            return

        db.set_pin(new_pin)
        page.pop_dialog()
        if reset_pin_state["on_success"]:
            reset_pin_state["on_success"]()
        page.update()

    reset_pin_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Reset PIN"),
        content=ft.Column(
            [reset_pin_number_field, reset_pin_new_field, reset_pin_confirm_field, reset_pin_error],
            tight=True,
            spacing=12,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=close_reset_pin_dialog),
            ft.TextButton("Reset", on_click=confirm_reset_pin),
        ],
    )

    def open_reset_pin_dialog(on_success=None):
        reset_pin_number_field.value = ""
        reset_pin_new_field.value = ""
        reset_pin_confirm_field.value = ""
        reset_pin_error.value = ""
        reset_pin_state["on_success"] = on_success
        page.show_dialog(reset_pin_dialog)

    # ---------------------------------------------------------------
    # APP LOCK SCREEN
    # ---------------------------------------------------------------
    lock_pin_field = ft.TextField(label="Enter PIN", password=True, can_reveal_password=True, keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    lock_error = ft.Text("", color=ft.Colors.RED)
    lock_view = ft.Container(padding=20, alignment=ft.Alignment.CENTER, expand=True)

    def confirm_unlock(e):
        lock_error.value = ""
        if db.verify_pin(lock_pin_field.value or ""):
            page.controls.clear()
            proceed_after_unlock()
        else:
            lock_error.value = "Incorrect PIN"
            page.update()

    def unlocked_after_reset():
        page.controls.clear()
        proceed_after_unlock()

    lock_view.content = ft.Column(
        [
            ft.Icon(ft.Icons.LOCK_OUTLINE, size=48, color=ft.Colors.GREY),
            ft.Text("Enter your PIN to continue", size=16),
            lock_pin_field,
            lock_error,
            ft.Button("Unlock", on_click=confirm_unlock, width=200),
            ft.TextButton("Forgot PIN?", on_click=lambda e: open_reset_pin_dialog(on_success=unlocked_after_reset)),
        ],
        spacing=14,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # ---------------------------------------------------------------
    # SETTINGS SCREEN
    # ---------------------------------------------------------------
    dark_mode_switch = ft.Switch(value=False)

    def on_dark_mode_switch(e):
        page.theme_mode = ft.ThemeMode.DARK if dark_mode_switch.value else ft.ThemeMode.LIGHT
        page.update()

    dark_mode_switch.on_change = on_dark_mode_switch

    reset_confirm_field = ft.TextField(label="Type DELETE to confirm", border_color=ft.Colors.OUTLINE)
    reset_confirm_error = ft.Text("", color=ft.Colors.RED)

    def close_reset_data_dialog(e=None):
        page.pop_dialog()

    def do_reset_all_data():
        db.reset_all_data()
        refresh_category_dropdowns()  # categories are back to the defaults
        page.controls.clear()
        page.navigation_bar = None
        settings_icon_button.visible = False
        render_onboarding()
        page.add(onboarding_view)
        page.update()

    def confirm_reset_data(e):
        reset_confirm_error.value = ""
        if reset_confirm_field.value != "DELETE":
            reset_confirm_error.value = "Type DELETE exactly to confirm"
            page.update()
            return
        page.pop_dialog()
        do_reset_all_data()

    reset_data_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Reset All Data?"),
        content=ft.Column(
            [
                ft.Text("This permanently deletes every account, transaction, loan, and investment. This cannot be undone."),
                reset_confirm_field,
                reset_confirm_error,
            ],
            tight=True,
            spacing=12,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=close_reset_data_dialog),
            ft.TextButton("Reset Everything", on_click=confirm_reset_data),
        ],
    )

    def open_reset_data_dialog():
        reset_confirm_field.value = ""
        reset_confirm_error.value = ""
        if db.has_pin_set():
            open_pin_dialog(on_success=lambda: page.show_dialog(reset_data_dialog))
        else:
            page.show_dialog(reset_data_dialog)

    settings_view = ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    # --- Manage Categories (Settings) ---
    new_category_name_field = ft.TextField(label="Category name", border_color=ft.Colors.OUTLINE)
    new_category_type_toggle = ft.CupertinoSlidingSegmentedButton(
        selected_index=1, controls=[ft.Text("Income"), ft.Text("Expense")]
    )
    new_category_error = ft.Text("", color=ft.Colors.RED)
    category_message = {"text": ""}  # shown once in Settings, e.g. "Keep at least one..."

    def close_add_category_dialog(e=None):
        page.pop_dialog()

    def confirm_add_category(e):
        new_category_error.value = ""
        type_ = "income" if new_category_type_toggle.selected_index == 0 else "expense"
        try:
            db.add_category(new_category_name_field.value, type_)
        except ValueError as err:
            new_category_error.value = str(err)
            page.update()
            return
        new_category_name_field.value = ""
        page.pop_dialog()
        build_settings()

    add_category_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Add Category"),
        content=ft.Column(
            [new_category_name_field, new_category_type_toggle, new_category_error],
            tight=True,
            spacing=12,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=close_add_category_dialog),
            ft.TextButton("Add", on_click=confirm_add_category),
        ],
    )

    def open_add_category_dialog(e=None):
        new_category_error.value = ""
        new_category_name_field.value = ""
        page.show_dialog(add_category_dialog)

    def delete_category_clicked(category_id):
        try:
            db.delete_category(category_id)
        except ValueError as err:
            category_message["text"] = str(err)
        build_settings()

    def category_rows(type_):
        rows = []
        for cat in db.get_categories_full(type_):
            rows.append(
                ft.Row(
                    [
                        ft.Text(cat["name"], size=13, expand=True),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE, icon_size=16,
                            on_click=lambda e, cid=cat["id"]: delete_category_clicked(cid),
                        ),
                    ]
                )
            )
        return rows

    def lock_now(e=None):
        if not db.has_pin_set():
            return  # nothing to lock with yet
        page.controls.clear()
        page.navigation_bar = None
        settings_icon_button.visible = False
        lock_pin_field.value = ""
        lock_error.value = ""
        page.add(lock_view)
        page.update()

    def build_settings():
        dark_mode_switch.value = page.theme_mode == ft.ThemeMode.DARK
        category_message_text = category_message["text"]
        category_message["text"] = ""  # show it once, then clear
        settings_view.controls = [
            ft.Row([ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=lambda e: go_back_from_settings()), ft.Text("Settings", size=22, weight=ft.FontWeight.BOLD)]),
            card(
                ft.Row(
                    [ft.Text("Dark Mode", expand=True), dark_mode_switch]
                )
            ),
            card(
                ft.Column(
                    [
                        ft.Text("Security", size=14, color=ft.Colors.GREY),
                        ft.TextButton("Reset PIN", on_click=lambda e: open_reset_pin_dialog(on_success=lambda: None)),
                        ft.TextButton("Lock Now", on_click=lambda e: lock_now()),
                    ],
                    spacing=8,
                )
            ),
            card(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("Recurring Income & Expenses", size=14, color=ft.Colors.GREY, expand=True),
                                ft.TextButton("+ Add Recurring", on_click=lambda e: open_add_recurring_dialog(on_success=build_settings)),
                            ]
                        ),
                        ft.Divider(height=1),
                    ]
                    + recurring_items_rows(build_settings),
                    spacing=8,
                )
            ),
            card(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("Categories", size=14, color=ft.Colors.GREY, expand=True),
                                ft.TextButton("+ Add Category", on_click=open_add_category_dialog),
                            ]
                        ),
                        ft.Divider(height=1),
                        ft.Text("Expense", size=12, color=ft.Colors.RED),
                    ]
                    + category_rows("expense")
                    + [ft.Text("Income", size=12, color=ft.Colors.GREEN)]
                    + category_rows("income")
                    + ([ft.Text(category_message_text, size=12, color=ft.Colors.RED)] if category_message_text else []),
                    spacing=4,
                )
            ),
            card(
                ft.Column(
                    [
                        ft.Text("Danger Zone", size=14, color=ft.Colors.RED),
                        ft.TextButton("Reset All App Data", on_click=lambda e: open_reset_data_dialog(), style=ft.ButtonStyle(color=ft.Colors.RED)),
                    ],
                    spacing=8,
                )
            ),
            card(
                ft.Column(
                    [
                        ft.Text("About", size=14, color=ft.Colors.GREY),
                        ft.Text("Finance Tracker", weight=ft.FontWeight.BOLD),
                        ft.Text("Version 1.0.0", size=12, color=ft.Colors.GREY),
                        ft.Text("Built with Python + Flet", size=12, color=ft.Colors.GREY),
                    ],
                    spacing=4,
                )
            ),
        ]
        page.update()

    def go_back_from_settings():
        body.content = home_content
        build_home()
        nav_bar.selected_index = 0
        page.update()

    def open_settings(e=None):
        build_settings()
        body.content = settings_view
        page.update()

    settings_icon_button.on_click = open_settings

    # ---------------------------------------------------------------
    # STARTUP: lock screen first if a PIN exists, otherwise go straight in
    # ---------------------------------------------------------------
    if db.has_pin_set():
        page.add(lock_view)
    else:
        proceed_after_unlock()


ft.run(main)