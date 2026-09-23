import flet as ft
import database as db

db.init_db()


def main(page: ft.Page):
    page.title = "Finance Tracker"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.padding = 0

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

    def build_home():
        home_content.controls.clear()

        accounts = db.get_accounts()
        income, expense, net = db.get_monthly_cash_flow()

        account_cards = ft.Row(
            [
                card(
                    ft.Column(
                        [
                            ft.Text(name, size=14, color=ft.Colors.GREY),
                            ft.Text(f"₹{balance:,.2f}", size=20, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=4,
                    ),
                    padding=14,
                )
                for (_id, name, balance) in accounts
            ],
            spacing=12,
            wrap=True,
        )

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
                                    ft.Text(f"₹{income:,.2f}", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN),
                                ]
                            ),
                            ft.Column(
                                [
                                    ft.Text("Expense", size=12, color=ft.Colors.GREY),
                                    ft.Text(f"₹{expense:,.2f}", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED),
                                ]
                            ),
                            ft.Column(
                                [
                                    ft.Text("Net", size=12, color=ft.Colors.GREY),
                                    ft.Text(f"₹{net:,.2f}", size=16, weight=ft.FontWeight.BOLD, color=net_color),
                                ]
                            ),
                        ],
                        spacing=30,
                    ),
                ],
                spacing=8,
            )
        )

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
                                ft.Text(f"{account_name} · {note or ''}", size=12, color=ft.Colors.GREY),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Column(
                            [
                                ft.Text(f"{sign}₹{amount:,.2f}", color=color, weight=ft.FontWeight.BOLD),
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

        home_content.controls.extend([account_cards, cash_flow_card, recent_card])
        page.update()

    # ---------------------------------------------------------------
    # ADD TRANSACTION VIEW
    # ---------------------------------------------------------------
    type_toggle = ft.CupertinoSlidingSegmentedButton(
        selected_index=1,
        controls=[ft.Text("Income"), ft.Text("Expense")],
    )
    amount_field = ft.TextField(label="Amount", prefix=ft.Text("₹"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
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

        combined_note = note_field.value or ""
        if counterparty_field.value:
            prefix = "From" if type_ == "income" else "To"
            combined_note = f"{prefix}: {counterparty_field.value}" + (f" — {combined_note}" if combined_note else "")

        db.add_transaction(
            account_id=int(account_dropdown.value),
            type_=type_,
            amount=amount,
            category=category_dropdown.value,
            note=combined_note,
        )

        amount_field.value = ""
        amount_field.error_text = None
        account_dropdown.value = None
        category_dropdown.value = None
        counterparty_field.value = ""
        note_field.value = ""
        add_feedback.value = "Added!"
        add_feedback.color = ft.Colors.GREEN

        build_home()
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
    loan_amount_field = ft.TextField(label="Amount", prefix=ft.Text("₹"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    loan_account_dropdown = ft.Dropdown(label="Account", border_color=ft.Colors.OUTLINE)
    loan_reason_field = ft.TextField(label="Reason (optional)", border_color=ft.Colors.OUTLINE)
    loan_feedback = ft.Text("", color=ft.Colors.GREEN)

    repay_amount_field = ft.TextField(label="Repayment amount", prefix=ft.Text("₹"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
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
                            ft.Text(f"₹{owed_to_you:,.2f}", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN),
                        ]
                    ),
                    ft.Column(
                        [
                            ft.Text("You owe", size=12, color=ft.Colors.GREY),
                            ft.Text(f"₹{you_owe:,.2f}", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED),
                        ]
                    ),
                ],
                spacing=40,
            )
        )

        loan_account_dropdown.options = [
            ft.dropdown.Option(key=str(a_id), text=name) for (a_id, name, _bal) in db.get_accounts()
        ]
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
                                ft.Text(f"₹{loan['remaining_amount']:,.2f}", color=color, weight=ft.FontWeight.BOLD),
                                ft.Text(f"of ₹{loan['amount']:,.2f}", size=11, color=ft.Colors.GREY),
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

    invest_name_field = ft.TextField(label="Investment name", border_color=ft.Colors.OUTLINE)
    invest_amount_field = ft.TextField(label="Amount invested", prefix=ft.Text("₹"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    invest_feedback = ft.Text("", color=ft.Colors.GREEN)

    update_value_field = ft.TextField(label="Current value", prefix=ft.Text("₹"), keyboard_type=ft.KeyboardType.NUMBER, border_color=ft.Colors.OUTLINE)
    update_value_error = ft.Text("", color=ft.Colors.RED)
    active_investment_id = {"id": None}

    def close_update_dialog(e=None):
        page.pop_dialog()

    def confirm_update_value(e):
        update_value_error.value = ""
        try:
            new_value = float(update_value_field.value)
            if new_value < 0:
                raise ValueError
        except (ValueError, TypeError):
            update_value_error.value = "Enter a valid amount"
            page.update()
            return

        db.update_investment_value(active_investment_id["id"], new_value)
        page.pop_dialog()
        build_invest()
        page.update()

    update_value_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Update Current Value"),
        content=ft.Column([update_value_field, update_value_error], tight=True, spacing=12),
        actions=[
            ft.TextButton("Cancel", on_click=close_update_dialog),
            ft.TextButton("Save", on_click=confirm_update_value),
        ],
    )

    def open_update_dialog(investment_id, current_value):
        active_investment_id["id"] = investment_id
        update_value_field.value = str(current_value)
        update_value_error.value = ""
        page.show_dialog(update_value_dialog)

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
                                    ft.Text(f"₹{total_invested:,.2f}", size=18, weight=ft.FontWeight.BOLD),
                                ]
                            ),
                            ft.Column(
                                [
                                    ft.Text("Current Value", size=12, color=ft.Colors.GREY),
                                    ft.Text(f"₹{total_current:,.2f}", size=18, weight=ft.FontWeight.BOLD),
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
                                f"{'+' if gain_loss >= 0 else ''}₹{gain_loss:,.2f} ({gain_pct:+.1f}%)",
                                color=gain_color,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ]
                    ),
                ],
                spacing=10,
            )
        )

        new_invest_card = card(
            ft.Column(
                [
                    ft.Text("Add Investment", size=14, color=ft.Colors.GREY),
                    invest_name_field,
                    invest_amount_field,
                    ft.ElevatedButton("Add", on_click=submit_investment, width=200),
                    invest_feedback,
                ],
                spacing=12,
            )
        )

        def investment_row(inv):
            gl = inv["current_value"] - inv["amount_invested"]
            gl_color = ft.Colors.GREEN if gl >= 0 else ft.Colors.RED
            gl_pct = (gl / inv["amount_invested"] * 100) if inv["amount_invested"] else 0
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(inv["name"], weight=ft.FontWeight.W_600),
                                ft.Text(f"Invested ₹{inv['amount_invested']:,.2f} · {inv['date_added']}", size=12, color=ft.Colors.GREY),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Column(
                            [
                                ft.Text(f"₹{inv['current_value']:,.2f}", weight=ft.FontWeight.BOLD),
                                ft.Text(f"{'+' if gl >= 0 else ''}{gl_pct:.1f}%", size=12, color=gl_color),
                                ft.TextButton(
                                    "Update",
                                    on_click=lambda e, iid=inv["id"], cv=inv["current_value"]: open_update_dialog(iid, cv),
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            spacing=2,
                        ),
                    ]
                ),
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

        db.add_investment(name=invest_name_field.value, amount_invested=amount)

        invest_name_field.value = ""
        invest_amount_field.value = ""
        invest_amount_field.error_text = None
        invest_feedback.value = "Added!"
        invest_feedback.color = ft.Colors.GREEN

        build_invest()
        page.update()
    stats_content = placeholder("Stats — coming next stage")

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