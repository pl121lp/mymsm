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


class _CheckableListDialog(QDialog):
    """Common shell for a dialog offering a checkable list of items plus
    Select All / Select None buttons and an OK/Cancel button box. Subclasses
    populate ``self.list_widget`` from their own constructor data and expose
    their own accessor for the checked items.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.list_widget = QListWidget()

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


class CategoryFilterDialog(_CheckableListDialog):
    def __init__(self, category_names, selected_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Categories")

        for name in category_names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in selected_names else Qt.Unchecked)
            self.list_widget.addItem(item)

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


class AccountFilterDialog(_CheckableListDialog):
    def __init__(self, accounts, selected_ids, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Accounts")

        for account_id, name in accounts:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, account_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if account_id in selected_ids else Qt.Unchecked)
            self.list_widget.addItem(item)

    def selected_account_ids(self):
        return {
            self.list_widget.item(i).data(Qt.UserRole)
            for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == Qt.Checked
        }
