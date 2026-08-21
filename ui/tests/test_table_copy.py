from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QTableView

from table_copy import _build_context_menu, build_clipboard_text


def _make_view(rows):
    model = QStandardItemModel(len(rows), 1)
    for row, value in enumerate(rows):
        model.setItem(row, 0, QStandardItem(value))
    view = QTableView()
    view.setModel(model)
    view.resize(200, 200)
    return view


def test_context_menu_has_no_edit_action_when_on_edit_not_given(qapp):
    view = _make_view(["a"])
    pos = view.visualRect(view.model().index(0, 0)).center()
    menu = _build_context_menu(view, pos)
    assert [action.text() for action in menu.actions()] == ["Copy"]


def test_context_menu_edit_action_calls_on_edit_with_clicked_row(qapp):
    view = _make_view(["a", "b", "c"])
    calls = []
    pos = view.visualRect(view.model().index(1, 0)).center()

    menu = _build_context_menu(view, pos, on_edit=lambda row: calls.append(row))

    edit_action = next(a for a in menu.actions() if a.text() == "Edit Record")
    edit_action.trigger()
    assert calls == [1]


def test_context_menu_has_no_edit_action_when_click_is_outside_any_row(qapp):
    view = _make_view(["a"])
    pos = view.viewport().rect().bottomRight()

    menu = _build_context_menu(view, pos, on_edit=lambda row: None)

    assert [action.text() for action in menu.actions()] == ["Copy"]


def test_context_menu_has_no_extra_actions_when_none_returned(qapp):
    view = _make_view(["a"])
    pos = view.visualRect(view.model().index(0, 0)).center()

    menu = _build_context_menu(view, pos, extra_actions=lambda row: [])

    assert [action.text() for action in menu.actions()] == ["Copy"]


def test_context_menu_includes_extra_actions_for_clicked_row(qapp):
    view = _make_view(["a", "b", "c"])
    pos = view.visualRect(view.model().index(1, 0)).center()

    menu = _build_context_menu(view, pos, extra_actions=lambda row: [("Delete Account", lambda: None)])

    assert [action.text() for action in menu.actions()] == ["Copy", "Delete Account"]


def test_context_menu_extra_action_callback_is_triggered(qapp):
    view = _make_view(["a", "b", "c"])
    calls = []
    pos = view.visualRect(view.model().index(2, 0)).center()

    menu = _build_context_menu(
        view, pos, extra_actions=lambda row: [("Delete Account", lambda: calls.append(row))]
    )

    delete_action = next(a for a in menu.actions() if a.text() == "Delete Account")
    delete_action.trigger()
    assert calls == [2]


def test_context_menu_has_no_extra_actions_when_click_is_outside_any_row(qapp):
    view = _make_view(["a"])
    pos = view.viewport().rect().bottomRight()

    menu = _build_context_menu(view, pos, extra_actions=lambda row: [("Delete Account", lambda: None)])

    assert [action.text() for action in menu.actions()] == ["Copy"]


def test_single_cell_returns_its_text():
    assert build_clipboard_text([(0, 0, "52.30")]) == "52.30"


def test_multiple_cells_same_row_are_tab_separated():
    assert build_clipboard_text([(0, 0, "2024-03-15"), (0, 1, "-52.30")]) == "2024-03-15\t-52.30"


def test_multiple_rows_are_newline_separated_and_sorted_by_position():
    cells = [(1, 0, "row1col0"), (0, 0, "row0col0"), (0, 1, "row0col1"), (1, 1, "row1col1")]
    assert build_clipboard_text(cells) == "row0col0\trow0col1\nrow1col0\trow1col1"


def test_no_cells_returns_empty_string():
    assert build_clipboard_text([]) == ""
