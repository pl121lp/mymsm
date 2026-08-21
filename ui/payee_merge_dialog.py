"""Review dialog for accepting/editing/rejecting suggested payee merges."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

NAME_COLUMN = 0
TXNS_COLUMN = 1
CANONICAL_NAME_COLUMN = 2


class PayeeMergeDialog(QDialog):
    """Shows each suggested merge group as a checkable tree: uncheck a group
    to skip it entirely, uncheck an individual variant to leave it out."""

    def __init__(self, groups, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Merge Duplicate Payees")
        self.resize(640, 480)
        self._groups = groups
        self._name_edits = {}  # group index -> QLineEdit

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Group / Variant", "Txns", "Canonical name"])
        self.tree.setColumnWidth(NAME_COLUMN, 380)
        self.tree.setColumnWidth(CANONICAL_NAME_COLUMN, 220)

        for group_index, group in enumerate(groups):
            total_txns = sum(txns for _pid, _name, txns in group.members)
            group_item = QTreeWidgetItem(self.tree)
            group_item.setFlags(group_item.flags() | Qt.ItemIsUserCheckable)
            group_item.setCheckState(NAME_COLUMN, Qt.Checked)
            group_item.setText(TXNS_COLUMN, str(total_txns))
            group_item.setData(NAME_COLUMN, Qt.UserRole, group_index)

            for payee_id, name, txns in group.members:
                child = QTreeWidgetItem(group_item)
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(NAME_COLUMN, Qt.Checked)
                child.setText(NAME_COLUMN, name)
                child.setText(TXNS_COLUMN, str(txns))
                child.setData(NAME_COLUMN, Qt.UserRole, payee_id)

            name_edit = QLineEdit(group.canonical_name)
            self.tree.setItemWidget(group_item, CANONICAL_NAME_COLUMN, name_edit)
            self._name_edits[group_index] = name_edit

        self.tree.expandAll()

        select_all = QPushButton("Select All")
        select_all.clicked.connect(lambda: self._set_all_checked(Qt.Checked))
        select_none = QPushButton("Select None")
        select_none.clicked.connect(lambda: self._set_all_checked(Qt.Unchecked))

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(select_all)
        buttons_row.addWidget(select_none)
        buttons_row.addStretch()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{len(groups)} suggested groups. Review and uncheck anything you don't want merged."))
        layout.addLayout(buttons_row)
        layout.addWidget(self.tree)
        layout.addWidget(button_box)

    def _set_all_checked(self, state):
        for i in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(i)
            group_item.setCheckState(NAME_COLUMN, state)
            for j in range(group_item.childCount()):
                group_item.child(j).setCheckState(NAME_COLUMN, state)

    def accepted_groups_and_names(self):
        """Returns (groups, names) ready for payee_aliases.save_aliases():
        groups: {canonical_payee_id: [absorbed_payee_id, ...]}
        names: {canonical_payee_id: display name}, only when edited/non-default.
        """
        groups = {}
        names = {}
        for group_index, group in enumerate(self._groups):
            group_item = self.tree.topLevelItem(group_index)
            if group_item.checkState(NAME_COLUMN) != Qt.Checked:
                continue
            checked_ids = [
                group_item.child(j).data(NAME_COLUMN, Qt.UserRole)
                for j in range(group_item.childCount())
                if group_item.child(j).checkState(NAME_COLUMN) == Qt.Checked
            ]
            canonical_id = group.canonical_payee_id
            if canonical_id not in checked_ids or len(checked_ids) < 2:
                continue
            absorbed = [pid for pid in checked_ids if pid != canonical_id]
            groups[canonical_id] = absorbed

            edited_name = self._name_edits[group_index].text().strip()
            if edited_name and edited_name != group.canonical_name:
                names[canonical_id] = edited_name
        return groups, names
