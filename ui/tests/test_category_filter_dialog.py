from PySide6.QtCore import Qt

from category_filter_dialog import CategoryFilterDialog


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
