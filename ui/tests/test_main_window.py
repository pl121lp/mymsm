from PySide6.QtCore import Qt

from main_window import MainWindow


def test_summary_labels_are_mouse_selectable_for_copying(qapp, conn):
    window = MainWindow(conn)
    labels = [
        window.total_label,
        window.account_details_label,
        window.details_name_value,
        window.details_type_value,
        window.details_currency_value,
        window.details_opening_balance_value,
        window.details_balance_value,
        window.details_status_value,
    ]
    for label in labels:
        assert label.textInteractionFlags() & Qt.TextSelectableByMouse
