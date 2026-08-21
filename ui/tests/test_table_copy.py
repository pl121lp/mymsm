from table_copy import build_clipboard_text


def test_single_cell_returns_its_text():
    assert build_clipboard_text([(0, 0, "52.30")]) == "52.30"


def test_multiple_cells_same_row_are_tab_separated():
    assert build_clipboard_text([(0, 0, "2024-03-15"), (0, 1, "-52.30")]) == "2024-03-15\t-52.30"


def test_multiple_rows_are_newline_separated_and_sorted_by_position():
    cells = [(1, 0, "row1col0"), (0, 0, "row0col0"), (0, 1, "row0col1"), (1, 1, "row1col1")]
    assert build_clipboard_text(cells) == "row0col0\trow0col1\nrow1col0\trow1col1"


def test_no_cells_returns_empty_string():
    assert build_clipboard_text([]) == ""
