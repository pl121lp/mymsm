from PySide6.QtCore import Qt

from category_filter_dialog import AccountFilterDialog, CategoryFilterDialog, InvestmentFilterDialog


def test_dialog_initializes_checkstate_from_selected_names(qapp):
    dialog = CategoryFilterDialog(["Groceries", "Rent", "Utilities"], {"Groceries", "Utilities"})

    assert dialog.selected_categories() == {"Groceries", "Utilities"}


def test_select_all_checks_every_category(qapp):
    dialog = CategoryFilterDialog(["Groceries", "Rent", "Utilities"], set())

    dialog.select_all_button.click()

    assert dialog.selected_categories() == {"Groceries", "Rent", "Utilities"}


def test_select_none_unchecks_every_category(qapp):
    dialog = CategoryFilterDialog(["Groceries", "Rent", "Utilities"], {"Groceries", "Rent", "Utilities"})

    dialog.select_none_button.click()

    assert dialog.selected_categories() == set()


def test_unchecking_one_item_removes_it_from_selection(qapp):
    dialog = CategoryFilterDialog(["Groceries", "Rent", "Utilities"], {"Groceries", "Rent", "Utilities"})

    dialog.list_widget.item(1).setCheckState(Qt.Unchecked)

    assert dialog.selected_categories() == {"Groceries", "Utilities"}


def test_investment_filter_dialog_has_its_own_window_title(qapp):
    dialog = InvestmentFilterDialog(["Vanguard", "Apple"], {"Vanguard", "Apple"})

    assert dialog.windowTitle() == "Custom Investments"


def test_investment_filter_dialog_selected_investments_reflects_checkstate(qapp):
    dialog = InvestmentFilterDialog(["Vanguard", "Apple"], {"Vanguard"})

    assert dialog.selected_investments() == {"Vanguard"}

    dialog.list_widget.item(1).setCheckState(Qt.Checked)

    assert dialog.selected_investments() == {"Vanguard", "Apple"}


def test_account_dialog_initializes_checkstate_from_selected_ids(qapp):
    dialog = AccountFilterDialog([(1, "Brokerage A"), (2, "Brokerage B")], {1})

    assert dialog.selected_account_ids() == {1}


def test_account_dialog_select_all_checks_every_account(qapp):
    dialog = AccountFilterDialog([(1, "Brokerage A"), (2, "Brokerage B")], set())

    dialog.select_all_button.click()

    assert dialog.selected_account_ids() == {1, 2}


def test_account_dialog_select_none_unchecks_every_account(qapp):
    dialog = AccountFilterDialog([(1, "Brokerage A"), (2, "Brokerage B")], {1, 2})

    dialog.select_none_button.click()

    assert dialog.selected_account_ids() == set()


def test_account_dialog_unchecking_one_account_removes_it_from_selection(qapp):
    dialog = AccountFilterDialog([(1, "Brokerage A"), (2, "Brokerage B")], {1, 2})

    dialog.list_widget.item(1).setCheckState(Qt.Unchecked)

    assert dialog.selected_account_ids() == {1}


def test_account_dialog_selects_by_id_not_name_when_names_collide(qapp):
    dialog = AccountFilterDialog([(1, "Brokerage"), (2, "Brokerage")], {2})

    assert dialog.selected_account_ids() == {2}
