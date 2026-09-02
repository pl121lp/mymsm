"""Modal dialog summarizing a set of selected transaction records."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from models import format_currency


class SummarizeDialog(QDialog):
    def __init__(self, transactions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Summarize Records")

        dates = [txn_date for _tid, txn_date, *_rest in transactions]
        payees = sorted({payee for _tid, _date, payee, *_rest in transactions if payee})
        amounts = [amount for _tid, _date, _payee, _category, _memo, amount, *_rest in transactions]
        total = sum(amounts)

        self.payees_label = QLabel(f"Payees: {', '.join(payees)}")
        self.payees_label.setWordWrap(True)
        self.date_range_label = QLabel(
            f"Date range: {min(dates).isoformat()} – {max(dates).isoformat()}"
        )
        self.count_label = QLabel(f"{len(transactions)} records")
        self.total_label = QLabel(f"Total: {format_currency(total)}")
        self.average_label = QLabel(f"Average: {format_currency(total / len(amounts))}")

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        self.button_box.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self.payees_label)
        layout.addWidget(self.date_range_label)
        layout.addWidget(self.count_label)
        layout.addWidget(self.total_label)
        layout.addWidget(self.average_label)
        layout.addWidget(self.button_box)
