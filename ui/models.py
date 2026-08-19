"""Qt table models adapting data.py query results for QTableViews."""

from PySide6.QtCore import QAbstractTableModel, Qt


class AccountTableModel(QAbstractTableModel):
    COLUMNS = ["Name", "Type"]

    def __init__(self, accounts=None, parent=None):
        super().__init__(parent)
        self._accounts = accounts or []

    def set_accounts(self, accounts):
        self.beginResetModel()
        self._accounts = accounts
        self.endResetModel()

    def account_id_at(self, row):
        return self._accounts[row][0]

    def rowCount(self, parent=None):
        return len(self._accounts)

    def columnCount(self, parent=None):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        _, name, account_type = self._accounts[index.row()]
        return [name, account_type or ""][index.column()]


class TransactionTableModel(QAbstractTableModel):
    COLUMNS = ["Date", "Payee", "Category", "Memo", "Amount"]

    def __init__(self, transactions=None, parent=None):
        super().__init__(parent)
        self._transactions = transactions or []

    def set_transactions(self, transactions):
        self.beginResetModel()
        self._transactions = transactions
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._transactions)

    def columnCount(self, parent=None):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        _, txn_date, payee, category, memo, amount = self._transactions[index.row()]
        values = [
            txn_date.isoformat(),
            payee or "",
            category or "",
            memo or "",
            f"{amount:.2f}",
        ]
        return values[index.column()]
