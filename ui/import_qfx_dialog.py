"""Modal dialog for importing parsed QFX records into an account."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

import data
import writes
from models import format_currency

COLUMNS = ["Date", "Type", "Amount", "Name", "Memo", "Check #", "FITID"]


def _row_items(record):
    return [
        record.txn_date.isoformat(),
        record.trn_type,
        format_currency(record.amount),
        record.name,
        record.memo,
        record.checknum,
        record.fitid,
    ]


def _fill_table(table, records):
    table.setRowCount(len(records))
    for row, record in enumerate(records):
        for col, value in enumerate(_row_items(record)):
            table.setItem(row, col, QTableWidgetItem(value))
    table.resizeColumnsToContents()


def _make_table():
    table = QTableWidget(0, len(COLUMNS))
    table.setHorizontalHeaderLabels(COLUMNS)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    return table


class ImportQfxDialog(QDialog):
    """Shows parsed QFX records, split into ones to import and ones that
    look like duplicates of transactions already in the selected account,
    and applies the non-duplicate rows to the database on Apply."""

    def __init__(self, conn, records, default_account_id=None, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._records = records
        self.imported_count = 0
        self.imported_transaction_ids = []

        self.setWindowTitle("Import QFX")

        self.account_combo = QComboBox()
        for account_id, name, *_rest in data.list_accounts(conn):
            self.account_combo.addItem(name, account_id)
        if default_account_id is not None:
            index = self.account_combo.findData(default_account_id)
            if index >= 0:
                self.account_combo.setCurrentIndex(index)
        self.account_combo.currentIndexChanged.connect(self._refresh_tables)

        self.import_table = _make_table()
        self.duplicates_table = _make_table()

        self.import_table.cellDoubleClicked.connect(
            lambda row, _col: self._move_row(row, self._to_import, self._duplicates)
        )
        self.duplicates_table.cellDoubleClicked.connect(
            lambda row, _col: self._move_row(row, self._duplicates, self._to_import)
        )

        self.import_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.import_table.customContextMenuRequested.connect(
            lambda pos: self._show_move_menu(pos, self.import_table, self._to_import, self._duplicates)
        )
        self.duplicates_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.duplicates_table.customContextMenuRequested.connect(
            lambda pos: self._show_move_menu(pos, self.duplicates_table, self._duplicates, self._to_import)
        )

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setWordWrap(True)

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._on_apply)
        self.discard_button = QPushButton("Discard")
        self.discard_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.apply_button)
        button_row.addWidget(self.discard_button)

        account_form = QFormLayout()
        account_form.addRow("Apply to account:", self.account_combo)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{len(records)} record(s) found in file."))
        layout.addWidget(QLabel("Records to import:"))
        layout.addWidget(self.import_table)
        layout.addWidget(QLabel("Likely duplicates (will be skipped):"))
        layout.addWidget(self.duplicates_table)
        layout.addLayout(account_form)
        layout.addWidget(self.error_label)
        layout.addLayout(button_row)
        self.resize(800, 600)

        self._refresh_tables()

    def _existing_keys(self, account_id):
        # Row shape from data.list_transactions: (transaction_id, txn_date,
        # payee_name, category_name, memo, amount, security_name, activity,
        # quantity, price).
        return {
            (row[1], row[5], (row[2] or "").strip().lower())
            for row in data.list_transactions(self._conn, account_id)
        }

    def _refresh_tables(self):
        account_id = self.account_combo.currentData()
        existing = self._existing_keys(account_id) if account_id is not None else set()

        self._to_import = []
        self._duplicates = []
        for record in self._records:
            key = (record.txn_date, record.amount, record.name.strip().lower())
            (self._duplicates if key in existing else self._to_import).append(record)

        self._sync_tables()

    def _sync_tables(self):
        self._to_import.sort(key=lambda record: record.txn_date, reverse=True)
        self._duplicates.sort(key=lambda record: record.txn_date, reverse=True)
        _fill_table(self.import_table, self._to_import)
        _fill_table(self.duplicates_table, self._duplicates)
        self.apply_button.setEnabled(bool(self._to_import))

    def _move_row(self, row, source_list, dest_list):
        self._move_rows([row], source_list, dest_list)

    def _move_rows(self, rows, source_list, dest_list):
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(source_list):
                dest_list.append(source_list.pop(row))
        self._sync_tables()

    def _show_move_menu(self, pos, table, source_list, dest_list):
        selected_rows = {index.row() for index in table.selectionModel().selectedRows()}
        if not selected_rows:
            clicked_row = table.rowAt(pos.y())
            selected_rows = {clicked_row} if clicked_row >= 0 else set()
        if not selected_rows:
            return
        menu = QMenu(table)
        move_action = menu.addAction("Move")
        chosen = menu.exec(table.viewport().mapToGlobal(pos))
        if chosen == move_action:
            self._move_rows(selected_rows, source_list, dest_list)

    def _on_apply(self):
        account_id = self.account_combo.currentData()
        try:
            self.imported_transaction_ids = writes.import_transactions(
                self._conn, account_id, self._to_import
            )
        except Exception as exc:
            self.error_label.setText(f"Failed to import records: {exc}")
            return
        self.imported_count = len(self.imported_transaction_ids)
        self.accept()
