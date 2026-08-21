from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDialog

from search_tab import SearchPane


def test_search_pane_lists_all_accounts_for_filtering(qapp, dict_conn):
    # Same account ordering as the Accounts tab: investment accounts (type '5')
    # sort before dict_conn's unrecognized 'Bank' type, alphabetically within
    # each group (see data.list_accounts).
    pane = SearchPane(dict_conn, report_error=lambda msg: None)
    account_names = [pane.account_list.item(i).text() for i in range(pane.account_list.count())]
    assert account_names == ["Brokerage A", "Brokerage B", "Checking", "Savings"]


def test_search_pane_starts_with_no_results(qapp, dict_conn):
    pane = SearchPane(dict_conn, report_error=lambda msg: None)
    assert pane.result_model.rowCount() == 0


def test_search_pane_search_button_populates_results_from_payee_filter(qapp, dict_conn):
    pane = SearchPane(dict_conn, report_error=lambda msg: None)
    pane.payee_edit.setText("Store A")
    pane.search_button.click()
    assert pane.result_model.rowCount() == 1


def test_search_pane_search_button_filters_by_selected_accounts(qapp, dict_conn):
    pane = SearchPane(dict_conn, report_error=lambda msg: None)
    pane.account_list.item(0).setSelected(True)  # Brokerage A
    pane.search_button.click()
    assert pane.result_model.rowCount() == 3


def test_search_pane_search_button_filters_by_amount_range(qapp, dict_conn):
    pane = SearchPane(dict_conn, report_error=lambda msg: None)
    pane.amount_min_edit.setText("100")
    pane.search_button.click()
    ids = {pane.result_model.transaction_at(r)[0] for r in range(pane.result_model.rowCount())}
    assert ids == {3000, 4000}


def test_search_pane_date_filters_default_to_any(qapp, dict_conn):
    pane = SearchPane(dict_conn, report_error=lambda msg: None)
    assert pane.date_min_edit.text() == "Any"
    assert pane.date_max_edit.text() == "Any"


def test_search_pane_search_button_filters_by_date_range(qapp, dict_conn):
    pane = SearchPane(dict_conn, report_error=lambda msg: None)
    pane.date_min_edit.setDate(QDate(2024, 2, 1))
    pane.date_max_edit.setDate(QDate(2024, 2, 28))
    pane.search_button.click()
    ids = {pane.result_model.transaction_at(r)[0] for r in range(pane.result_model.rowCount())}
    assert ids == {3001, 4001}


def test_search_pane_clear_button_resets_date_filters_to_any(qapp, dict_conn):
    pane = SearchPane(dict_conn, report_error=lambda msg: None)
    pane.date_min_edit.setDate(QDate(2024, 2, 1))
    pane.date_max_edit.setDate(QDate(2024, 2, 28))

    pane.clear_button.click()

    assert pane.date_min_edit.text() == "Any"
    assert pane.date_max_edit.text() == "Any"


def test_search_pane_shows_result_count(qapp, dict_conn):
    pane = SearchPane(dict_conn, report_error=lambda msg: None)
    pane.payee_edit.setText("Store")
    pane.search_button.click()
    assert pane.result_count_label.text() == "2 matching transactions"


def test_search_pane_clear_button_resets_filters_and_results(qapp, dict_conn):
    pane = SearchPane(dict_conn, report_error=lambda msg: None)
    pane.payee_edit.setText("Store A")
    pane.account_list.item(2).setSelected(True)
    pane.search_button.click()
    assert pane.result_model.rowCount() == 1

    pane.clear_button.click()

    assert pane.payee_edit.text() == ""
    assert pane.account_list.selectedItems() == []
    assert pane.result_model.rowCount() == 0
    assert pane.result_count_label.text() == ""


def test_search_pane_double_click_opens_edit_dialog_for_clicked_result(qapp, dict_conn, monkeypatch):
    import add_record_dialog

    seen = []
    original_init = add_record_dialog.AddRecordDialog.__init__

    def spy_init(self, conn, account_id, account_type, transaction=None, parent=None):
        seen.append((account_id, account_type, transaction))
        original_init(self, conn, account_id, account_type, transaction=transaction, parent=parent)

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "__init__", spy_init)
    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Rejected)

    pane = SearchPane(dict_conn, report_error=lambda msg: None)
    pane.payee_edit.setText("Store A")
    pane.search_button.click()

    pane._on_result_double_clicked(pane.result_model.index(0, 0))

    assert len(seen) == 1
    assert seen[0][0] == 1  # Checking account_id
    assert seen[0][1] == "Bank"
    assert seen[0][2] == pane.result_model.transaction_at(0)


def test_search_pane_edit_accept_reruns_search_and_notifies_caller(qapp, dict_conn, monkeypatch):
    import add_record_dialog
    import writes
    from datetime import date
    from decimal import Decimal

    def fake_exec(self):
        writes.update_transaction(
            self._conn, self._editing_transaction_id, date(2024, 3, 15), Decimal("-52.30"),
            memo="edited", payee_name="Store A", category_name="Groceries",
        )
        return QDialog.Accepted

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", fake_exec)

    changed_calls = []
    pane = SearchPane(
        dict_conn, report_error=lambda msg: None,
        on_transaction_changed=lambda: changed_calls.append(True),
    )
    pane.payee_edit.setText("Store A")
    pane.search_button.click()

    pane._on_result_double_clicked(pane.result_model.index(0, 0))

    assert changed_calls == [True]
    assert pane.result_model.transaction_at(0)[4] == "edited"


def test_search_pane_edit_cancel_does_not_rerun_search_or_notify(qapp, dict_conn, monkeypatch):
    import add_record_dialog

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Rejected)

    changed_calls = []
    pane = SearchPane(
        dict_conn, report_error=lambda msg: None,
        on_transaction_changed=lambda: changed_calls.append(True),
    )
    pane.payee_edit.setText("Store A")
    pane.search_button.click()

    pane._on_result_double_clicked(pane.result_model.index(0, 0))

    assert changed_calls == []
