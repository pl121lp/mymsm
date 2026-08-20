"""Dictionaries tab: browse categories and investments across all accounts."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import data
from models import CategoryTransactionTableModel, DictionaryListModel


class CategoriesPane(QWidget):
    def __init__(self, conn, report_error, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error

        self.list_model = DictionaryListModel()
        self.detail_model = CategoryTransactionTableModel()

        self.list_view = QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selected)

        self.detail_view = QTableView()
        self.detail_view.setModel(self.detail_model)
        self.detail_view.horizontalHeader().setStretchLastSection(True)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.list_view)
        splitter.addWidget(self.detail_view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self._reload()

    def _reload(self):
        try:
            categories = data.list_categories(self._conn)
        except Exception as exc:
            self._report_error(f"Failed to load categories: {exc}")
            return
        self.list_model.set_items(categories)

    def _on_selected(self, selected=None, deselected=None):
        indexes = self.list_view.selectionModel().selectedIndexes()
        if not indexes:
            self.detail_model.set_transactions([])
            return
        category_id = self.list_model.id_at(indexes[0].row())
        try:
            transactions = data.list_category_transactions(self._conn, category_id)
        except Exception as exc:
            self._report_error(f"Failed to load category transactions: {exc}")
            return
        self.detail_model.set_transactions(transactions)
        self.detail_view.resizeColumnsToContents()
