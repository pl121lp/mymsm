"""Dictionaries tab: browse categories and investments across all accounts."""

from PySide6.QtCharts import QChart, QChartView
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLabel,
    QListView,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import data
import payee_aliases
import theme
from charts import build_line_chart
from models import (
    CategoryTransactionTableModel,
    DictionaryListModel,
    PayeeTransactionTableModel,
)
from payee_merge import find_merge_groups
from payee_merge_dialog import PayeeMergeDialog
from table_copy import enable_cell_copy


def _empty_chart():
    chart = QChart()
    chart.setTheme(theme.chart_theme())
    return chart


class CategoriesPane(QWidget):
    def __init__(self, conn, report_error, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error

        self.list_model = DictionaryListModel()
        self.detail_model = CategoryTransactionTableModel()

        self.count_label = QLabel()

        self.list_view = QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selected)
        enable_cell_copy(self.list_view)

        self.detail_count_label = QLabel()

        self.detail_view = QTableView()
        self.detail_view.setModel(self.detail_model)
        self.detail_view.horizontalHeader().setStretchLastSection(True)
        enable_cell_copy(self.detail_view)

        list_pane = QWidget()
        list_layout = QVBoxLayout(list_pane)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(self.count_label)
        list_layout.addWidget(self.list_view)

        detail_pane = QWidget()
        detail_layout = QVBoxLayout(detail_pane)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(self.detail_count_label)
        detail_layout.addWidget(self.detail_view)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(list_pane)
        splitter.addWidget(detail_pane)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self._reload()

    def _reload(self):
        try:
            categories = data.list_categories(self._conn)
            txn_counts = data.count_transactions_by_category(self._conn)
        except Exception as exc:
            self._report_error(f"Failed to load categories: {exc}")
            return
        categories = [c for c in categories if txn_counts.get(c[0], 0) > 0]
        self.list_model.set_items(categories)
        self.count_label.setText(f"{len(categories)} categories")
        self.detail_model.set_transactions([])
        self.detail_count_label.setText("0 records")

    def _on_selected(self, selected=None, deselected=None):
        indexes = self.list_view.selectionModel().selectedIndexes()
        if not indexes:
            self.detail_model.set_transactions([])
            self.detail_count_label.setText("0 records")
            return
        category_id = self.list_model.id_at(indexes[0].row())
        try:
            transactions = data.list_category_transactions(self._conn, category_id)
        except Exception as exc:
            self._report_error(f"Failed to load category transactions: {exc}")
            return
        self.detail_model.set_transactions(transactions)
        self.detail_count_label.setText(f"{len(transactions)} records")
        self.detail_view.resizeColumnsToContents()


class PayeesPane(QWidget):
    def __init__(self, conn, report_error, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error
        self._alias_groups = payee_aliases.load_aliases()
        self._alias_names = payee_aliases.load_canonical_names()

        self.list_model = DictionaryListModel()
        self.detail_model = PayeeTransactionTableModel()

        self.merge_button = QPushButton("Merge Duplicates…")
        self.merge_button.clicked.connect(self._on_merge_clicked)

        self.count_label = QLabel()

        self.list_view = QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selected)
        enable_cell_copy(self.list_view)

        self.detail_count_label = QLabel()

        self.detail_view = QTableView()
        self.detail_view.setModel(self.detail_model)
        self.detail_view.horizontalHeader().setStretchLastSection(True)
        enable_cell_copy(self.detail_view)

        list_pane = QWidget()
        list_layout = QVBoxLayout(list_pane)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(self.merge_button)
        list_layout.addWidget(self.count_label)
        list_layout.addWidget(self.list_view)

        detail_pane = QWidget()
        detail_layout = QVBoxLayout(detail_pane)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(self.detail_count_label)
        detail_layout.addWidget(self.detail_view)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(list_pane)
        splitter.addWidget(detail_pane)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self._reload()

    def _reload(self):
        try:
            payees = data.list_payees(self._conn)
        except Exception as exc:
            self._report_error(f"Failed to load payees: {exc}")
            return
        merged = payee_aliases.apply_aliases(payees, self._alias_groups, self._alias_names)
        self.list_model.set_items(merged)
        self.count_label.setText(f"{len(merged)} payees")
        self.detail_model.set_transactions([])
        self.detail_count_label.setText("0 records")

    def _on_selected(self, selected=None, deselected=None):
        indexes = self.list_view.selectionModel().selectedIndexes()
        if not indexes:
            self.detail_model.set_transactions([])
            self.detail_count_label.setText("0 records")
            return
        payee_id = self.list_model.id_at(indexes[0].row())
        payee_ids = payee_aliases.resolve_payee_ids(payee_id, self._alias_groups)
        try:
            transactions = data.list_payee_transactions(self._conn, payee_ids)
        except Exception as exc:
            self._report_error(f"Failed to load payee transactions: {exc}")
            return
        self.detail_model.set_transactions(transactions)
        self.detail_count_label.setText(f"{len(transactions)} records")
        self.detail_view.resizeColumnsToContents()

    def _on_merge_clicked(self):
        try:
            payees = data.list_payees(self._conn)
            txn_counts = data.count_transactions_by_payee(self._conn)
        except Exception as exc:
            self._report_error(f"Failed to load payees: {exc}")
            return

        already_merged = {
            payee_id for members in self._alias_groups.values() for payee_id in members
        }
        candidates = [row for row in payees if row[0] not in already_merged]

        self._report_error("Scanning payee names for duplicates…")
        QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            groups = find_merge_groups(candidates, txn_counts)
        finally:
            QApplication.restoreOverrideCursor()
        # Drop groups whose canonical payee already stands for a prior merge --
        # they'd need to compose two overlays, which isn't supported yet.
        groups = [g for g in groups if g.canonical_payee_id not in self._alias_groups]

        if not groups:
            QMessageBox.information(self, "Merge Duplicate Payees", "No duplicate payees found.")
            self._report_error("")
            return

        dialog = PayeeMergeDialog(groups, parent=self)
        if dialog.exec() != PayeeMergeDialog.Accepted:
            self._report_error("")
            return

        new_groups, new_names = dialog.accepted_groups_and_names()
        if not new_groups:
            self._report_error("")
            return

        self._alias_groups = payee_aliases.merge_groups(self._alias_groups, new_groups)
        self._alias_names.update(new_names)
        payee_aliases.save_aliases(self._alias_groups, self._alias_names)

        self._report_error(f"Merged {len(new_groups)} payee group(s).")
        self._reload()


class InvestmentsPane(QWidget):
    def __init__(self, conn, report_error, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error

        self.list_model = DictionaryListModel()
        self.count_label = QLabel()
        self.list_view = QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selected)
        enable_cell_copy(self.list_view)

        list_pane = QWidget()
        list_layout = QVBoxLayout(list_pane)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(self.count_label)
        list_layout.addWidget(self.list_view)

        self.price_chart_view = QChartView()
        self.price_chart_view.setRenderHint(QPainter.Antialiasing)
        self.price_chart_view.setChart(_empty_chart())
        self.quantity_chart_view = QChartView()
        self.quantity_chart_view.setRenderHint(QPainter.Antialiasing)
        self.quantity_chart_view.setChart(_empty_chart())

        charts_widget = QWidget()
        charts_layout = QVBoxLayout(charts_widget)
        charts_layout.addWidget(self.price_chart_view)
        charts_layout.addWidget(self.quantity_chart_view)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(list_pane)
        splitter.addWidget(charts_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self._reload()

    def _reload(self):
        try:
            securities = data.list_securities(self._conn)
        except Exception as exc:
            self._report_error(f"Failed to load investments: {exc}")
            return
        self.list_model.set_items(securities)
        self.count_label.setText(f"{len(securities)} investments")

    def _on_selected(self, selected=None, deselected=None):
        indexes = self.list_view.selectionModel().selectedIndexes()
        if not indexes:
            self.price_chart_view.setChart(_empty_chart())
            self.quantity_chart_view.setChart(_empty_chart())
            return
        security_id = self.list_model.id_at(indexes[0].row())
        try:
            history = data.list_security_history(self._conn, security_id)
        except Exception as exc:
            self._report_error(f"Failed to load investment history: {exc}")
            return

        price_by_account = {}
        qty_by_account = {}
        for account_id, account_name, txn_date, price, cumulative_qty in history:
            if price is not None:
                price_by_account.setdefault(account_id, (account_name, []))[1].append(
                    (txn_date, price)
                )
            qty_by_account.setdefault(account_id, (account_name, []))[1].append(
                (txn_date, cumulative_qty)
            )

        self.price_chart_view.setChart(build_line_chart("Price", price_by_account.values()))
        self.quantity_chart_view.setChart(
            build_line_chart("Quantity Held", qty_by_account.values())
        )
