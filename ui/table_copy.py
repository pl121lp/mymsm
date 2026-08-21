"""Copy-to-clipboard support for QTableView cells (right-click menu + Ctrl+C)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QMenu


def build_clipboard_text(cells):
    """Turn (row, col, text) cells into an Excel-style tab/newline-joined string."""
    if not cells:
        return ""
    rows = {}
    for row, col, text in cells:
        rows.setdefault(row, {})[col] = text
    col_keys = sorted({col for row_cells in rows.values() for col in row_cells})
    lines = [
        "\t".join(str(rows[row].get(col, "")) for col in col_keys) for row in sorted(rows)
    ]
    return "\n".join(lines)


def _copy_selection(view):
    indexes = view.selectionModel().selectedIndexes()
    if not indexes:
        current = view.currentIndex()
        if current.isValid():
            indexes = [current]
    cells = [(index.row(), index.column(), index.data(Qt.DisplayRole) or "") for index in indexes]
    text = build_clipboard_text(cells)
    if text:
        QGuiApplication.clipboard().setText(text)


def _build_context_menu(view, pos, on_edit=None, extra_actions=None):
    menu = QMenu(view)
    copy_action = menu.addAction("Copy")
    copy_action.triggered.connect(lambda: _copy_selection(view))
    index = view.indexAt(pos)
    if on_edit is not None and index.isValid():
        edit_action = menu.addAction("Edit Record")
        edit_action.triggered.connect(lambda: on_edit(index.row()))
    if extra_actions is not None and index.isValid():
        for label, callback in extra_actions(index.row()):
            action = menu.addAction(label)
            action.triggered.connect(callback)
    return menu


def _show_context_menu(view, pos, on_edit=None, extra_actions=None):
    menu = _build_context_menu(view, pos, on_edit, extra_actions)
    menu.exec(view.viewport().mapToGlobal(pos))


def enable_label_copy(label):
    """Let a QLabel's text be selected with the mouse and copied (Ctrl+C / right-click)."""
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)


def enable_cell_copy(view, on_edit=None, extra_actions=None):
    """Wire up right-click 'Copy' (plus 'Edit Record' when `on_edit` is given)
    and Ctrl+C on a QTableView's cells. `on_edit`, if given, is called with
    the clicked row when "Edit Record" is chosen. `extra_actions`, if given,
    is called with the clicked row and should return a list of
    (label, callback) pairs to append to the menu."""
    view.setContextMenuPolicy(Qt.CustomContextMenu)
    view.customContextMenuRequested.connect(
        lambda pos: _show_context_menu(view, pos, on_edit, extra_actions)
    )

    shortcut = QShortcut(QKeySequence.Copy, view)
    shortcut.setContext(Qt.WidgetWithChildrenShortcut)
    shortcut.activated.connect(lambda: _copy_selection(view))
