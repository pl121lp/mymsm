"""Dialog for choosing which categories a report should include."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class CategoryFilterDialog(QDialog):
    def __init__(self, category_names, selected_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Categories")

        self.list_widget = QListWidget()
        for name in category_names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in selected_names else Qt.Unchecked)
            self.list_widget.addItem(item)

        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(lambda: self._set_all_checked(Qt.Checked))
        self.select_none_button = QPushButton("Select None")
        self.select_none_button.clicked.connect(lambda: self._set_all_checked(Qt.Unchecked))

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.select_all_button)
        buttons_row.addWidget(self.select_none_button)
        buttons_row.addStretch()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons_row)
        layout.addWidget(self.list_widget)
        layout.addWidget(button_box)

    def _set_all_checked(self, state):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)

    def selected_categories(self):
        return {
            self.list_widget.item(i).text()
            for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == Qt.Checked
        }


class InvestmentFilterDialog(CategoryFilterDialog):
    def __init__(self, investment_names, selected_names, parent=None):
        super().__init__(investment_names, selected_names, parent)
        self.setWindowTitle("Custom Investments")

    def selected_investments(self):
        return self.selected_categories()
