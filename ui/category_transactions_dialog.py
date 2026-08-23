"""Modal dialog listing every transaction posted to a single category."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTableView, QVBoxLayout

from models import CategoryTransactionTableModel
from table_copy import enable_cell_copy


class CategoryTransactionsDialog(QDialog):
    def __init__(self, category_name, transactions, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Transactions: {category_name}")

        self.count_label = QLabel(f"{len(transactions)} records")

        self.table_model = CategoryTransactionTableModel(transactions)
        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        enable_cell_copy(self.table_view)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.count_label)
        layout.addWidget(self.table_view)
        layout.addWidget(button_box)
        self.resize(700, 400)
