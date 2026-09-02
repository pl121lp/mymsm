from datetime import date
from decimal import Decimal

from PySide6.QtCharts import QBarCategoryAxis
from PySide6.QtCore import Qt, QPointF

import charts
from charts import (
    build_bar_chart,
    build_grouped_stacked_bar_chart,
    build_line_chart,
    build_pie_chart,
    build_stacked_area_chart,
)


def test_build_pie_chart_creates_one_slice_per_category(qapp):
    chart = build_pie_chart(
        "Spending by Category",
        [("Utilities", Decimal("75.00")), ("Groceries", Decimal("72.30"))],
    )

    assert len(chart.series()) == 1
    series = chart.series()[0]
    slices = series.slices()
    assert len(slices) == 2
    assert slices[0].label() == "Utilities"
    assert slices[0].value() == 75.00
    assert slices[1].label() == "Groceries"
    assert slices[1].value() == 72.30


def test_build_bar_chart_hover_shows_date_and_value(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(charts.QToolTip, "showText", lambda pos, text: shown.append(text))

    chart = build_bar_chart("Net Worth Over Time (USD)", ["2024-07-01", "2024-09-01"], [1234.5, 6789.25])
    series = chart.series()[0]
    bar_set = series.barSets()[0]

    series.hovered.emit(True, 0, bar_set)
    assert shown == ["2024-07-01: 1,234.50"]

    series.hovered.emit(True, 1, bar_set)
    assert shown == ["2024-07-01: 1,234.50", "2024-09-01: 6,789.25"]


def test_build_bar_chart_labels_x_axis_with_one_entry_per_year(qapp):
    categories = [
        "2022-01-01",
        "2022-07-01",
        "2023-01-01",
        "2023-07-01",
        "2024-01-01",
        "2024-07-01",
    ]
    chart = build_bar_chart("Net Worth Over Time (USD)", categories, [0, 0, 0, 0, 0, 0])

    axis_x = chart.axes(Qt.Horizontal)[0]
    assert axis_x.labelsVisible()
    assert len(axis_x.categories()) == len(categories)
    assert [label for label in axis_x.categories() if label.isdigit()] == ["2022", "2023", "2024"]


def test_build_bar_chart_labels_every_third_year_when_span_is_wide(qapp):
    categories = [f"{year}-01-01" for year in range(2000, 2030)]
    chart = build_bar_chart("Net Worth Over Time (USD)", categories, [0] * len(categories))

    axis_x = chart.axes(Qt.Horizontal)[0]
    assert len(axis_x.categories()) == len(categories)
    labeled_years = [label for label in axis_x.categories() if label.isdigit()]
    assert labeled_years == [str(year) for year in range(2000, 2030, 3)]


def test_build_bar_chart_labels_every_fourth_year_when_span_is_very_wide(qapp):
    categories = [f"{year}-01-01" for year in range(2000, 2040)]
    chart = build_bar_chart("Net Worth Over Time (USD)", categories, [0] * len(categories))

    axis_x = chart.axes(Qt.Horizontal)[0]
    assert len(axis_x.categories()) == len(categories)
    labeled_years = [label for label in axis_x.categories() if label.isdigit()]
    assert labeled_years == [str(year) for year in range(2000, 2040, 4)]


def test_build_bar_chart_x_axis_labels_are_larger_than_default(qapp):
    categories = ["2022-01-01", "2022-07-01", "2023-01-01"]
    chart = build_bar_chart("Net Worth Over Time (USD)", categories, [0, 0, 0])

    axis_x = chart.axes(Qt.Horizontal)[0]
    default_point_size = QBarCategoryAxis().labelsFont().pointSize()
    assert axis_x.labelsFont().pointSize() > default_point_size


def test_build_bar_chart_x_axis_labels_are_rotated_to_avoid_eliding(qapp):
    categories = [f"{year}-{month:02d}-01" for year in range(2000, 2020) for month in (1, 7)]
    chart = build_bar_chart("Net Worth Over Time (USD)", categories, [0] * len(categories))

    axis_x = chart.axes(Qt.Horizontal)[0]
    assert axis_x.labelsAngle() == -90


def test_build_bar_chart_x_axis_labels_are_not_truncated(qapp):
    # QBarCategoryAxis elides labels against the per-bar slot width, which
    # is tiny once sampling is dense (e.g. a decade of bimonthly net worth
    # samples) -- even rotated, a "2024" label doesn't fit a slot a few
    # pixels wide, so truncation must be disabled or every year label
    # collapses to "...".
    categories = [f"{year}-{month:02d}-01" for year in range(2000, 2020) for month in (1, 7)]
    chart = build_bar_chart("Net Worth Over Time (USD)", categories, [0] * len(categories))

    axis_x = chart.axes(Qt.Horizontal)[0]
    assert axis_x.truncateLabels() is False


def _asset_groups():
    return [
        ("Investments", [("Brokerage A", Decimal("100")), ("Brokerage B", Decimal("50"))]),
        ("Assets", [("House", Decimal("500000"))]),
        ("Loans / Liabilities", []),
    ]


def test_build_grouped_stacked_bar_chart_creates_one_barset_per_account(qapp):
    chart = build_grouped_stacked_bar_chart("Assets and Investments (USD)", _asset_groups())

    series = chart.series()[0]
    bar_sets = series.barSets()
    assert [bar_set.label() for bar_set in bar_sets] == ["Brokerage A", "Brokerage B", "House"]


def test_build_grouped_stacked_bar_chart_pads_accounts_with_zero_outside_their_group(qapp):
    chart = build_grouped_stacked_bar_chart("Assets and Investments (USD)", _asset_groups())

    series = chart.series()[0]
    bar_sets = {bar_set.label(): bar_set for bar_set in series.barSets()}

    def _values(bar_set):
        return [bar_set.at(i) for i in range(bar_set.count())]

    assert _values(bar_sets["Brokerage A"]) == [100.0, 0.0, 0.0]
    assert _values(bar_sets["House"]) == [0.0, 500000.0, 0.0]


def test_build_grouped_stacked_bar_chart_orders_accounts_by_descending_value_within_each_group(qapp):
    groups = [
        ("Investments", [("Brokerage A", Decimal("50")), ("Brokerage B", Decimal("100"))]),
    ]
    chart = build_grouped_stacked_bar_chart("Assets and Investments (USD)", groups)

    series = chart.series()[0]
    assert [bar_set.label() for bar_set in series.barSets()] == ["Brokerage B", "Brokerage A"]


def test_build_grouped_stacked_bar_chart_category_axis_shows_group_labels(qapp):
    chart = build_grouped_stacked_bar_chart("Assets and Investments (USD)", _asset_groups())

    axis = chart.axes(Qt.Horizontal)[0]
    assert list(axis.categories()) == ["Investments", "Assets", "Loans / Liabilities"]
    assert axis.labelsVisible()


def test_build_grouped_stacked_bar_chart_hover_shows_account_and_value(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(charts.QToolTip, "showText", lambda pos, text: shown.append(text))

    chart = build_grouped_stacked_bar_chart("Assets and Investments (USD)", _asset_groups())
    series = chart.series()[0]
    brokerage_a = next(bar_set for bar_set in series.barSets() if bar_set.label() == "Brokerage A")

    series.hovered.emit(True, 0, brokerage_a)
    assert shown == ["Brokerage A: 100.00"]


def _points():
    return [(date(2024, 1, 1), Decimal("100")), (date(2024, 2, 1), Decimal("200"))]


def test_build_line_chart_by_default_does_not_force_zero_into_range(qapp):
    chart = build_line_chart("Title", [("Series", _points())])

    axis_y = chart.axes(Qt.Vertical)[0]
    assert axis_y.min() == 100.0
    assert len(chart.series()) == 1


def test_build_line_chart_mark_zero_extends_range_to_include_zero(qapp):
    chart = build_line_chart("Title", [("Series", _points())], mark_zero=True)

    axis_y = chart.axes(Qt.Vertical)[0]
    assert axis_y.min() == 0.0
    assert axis_y.max() == 200.0


def test_build_line_chart_mark_zero_adds_a_hidden_zero_reference_series(qapp):
    chart = build_line_chart("Title", [("Series", _points())], mark_zero=True)

    assert len(chart.series()) == 2
    zero_series = chart.series()[-1]
    assert all(point.y() == 0.0 for point in zero_series.points())
    markers = chart.legend().markers(zero_series)
    assert markers and markers[0].isVisible() is False


def test_build_line_chart_hover_shows_series_label_date_and_value(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(charts.QToolTip, "showText", lambda pos, text: shown.append(text))

    chart = build_line_chart("Title", [("Series", _points())])
    line_series = chart.series()[0]
    first_point = line_series.points()[0]

    line_series.hovered.emit(QPointF(first_point.x(), first_point.y()), True)
    assert shown == ["Series\n2024-01-01: 100.00"]


def _bands():
    bottom = [(date(2024, 1, 1), Decimal("100")), (date(2024, 2, 1), Decimal("100"))]
    top = [(date(2024, 1, 1), Decimal("50")), (date(2024, 2, 1), Decimal("150"))]
    return [("Bottom", bottom, "#ADD8E6"), ("Top", top, "#FFCC80")]


def test_build_stacked_area_chart_creates_one_area_series_per_band(qapp):
    chart = build_stacked_area_chart("Title", _bands())

    assert [s.name() for s in chart.series()] == ["Bottom", "Top"]


def test_build_stacked_area_chart_stacks_bands_cumulatively(qapp):
    chart = build_stacked_area_chart("Title", _bands())

    bottom_series, top_series = chart.series()

    assert [point.y() for point in bottom_series.lowerSeries().points()] == [0.0, 0.0]
    assert [point.y() for point in bottom_series.upperSeries().points()] == [100.0, 100.0]
    assert [point.y() for point in top_series.lowerSeries().points()] == [100.0, 100.0]
    assert [point.y() for point in top_series.upperSeries().points()] == [150.0, 250.0]


def test_build_stacked_area_chart_mark_zero_extends_range_to_include_zero(qapp):
    negative_bottom = [(date(2024, 1, 1), Decimal("-10")), (date(2024, 2, 1), Decimal("-10"))]
    chart = build_stacked_area_chart("Title", [("Bottom", negative_bottom, "#ADD8E6")], mark_zero=True)

    axis_y = chart.axes(Qt.Vertical)[0]
    assert axis_y.max() == 0.0


def test_build_stacked_area_chart_hover_shows_band_own_value_not_cumulative(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(charts.QToolTip, "showText", lambda pos, text: shown.append(text))

    chart = build_stacked_area_chart("Title", _bands())
    top_series = chart.series()[1]
    first_upper_point = top_series.upperSeries().points()[0]

    # y is the cumulative boundary value (150); the hover handler should look up
    # the band's own contribution (50) by date rather than using this y.
    top_series.hovered.emit(QPointF(first_upper_point.x(), first_upper_point.y()), True)
    assert shown == ["Top\n2024-01-01: 50.00"]
