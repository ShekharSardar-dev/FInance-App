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

    def build_home():
        home_content.controls.clear()

        accounts = db.get_accounts()
        income, expense, net = db.get_monthly_cash_flow()

        # --- Account balance cards, side by side ---
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

    loans_content = placeholder("Loans — coming next stage")
    invest_content = placeholder("Investments — coming next stage")
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