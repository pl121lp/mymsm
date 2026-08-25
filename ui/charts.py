"""Shared QtCharts chart builders for time-series widgets."""

from PySide6.QtCharts import (
    QAreaSeries,
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QDateTimeAxis,
    QLineSeries,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QBrush, QColor, QCursor
from PySide6.QtWidgets import QToolTip


def build_line_chart(title, series, mark_zero=False):
    """Build a multi-series date/value line chart.

    series is an iterable of (label, points) pairs, where points is a list
    of (date, value) tuples. When mark_zero is True, the y-axis range is
    extended to include 0 and a dashed reference line is drawn at y=0 (kept
    out of the legend) so a chart that can go negative always shows where
    zero is -- used for the net worth projection, which can dip negative.
    """
    chart = QChart()
    chart.setTitle(title)
    axis_x = QDateTimeAxis()
    axis_x.setFormat("yyyy-MM-dd")
    axis_y = QValueAxis()
    chart.addAxis(axis_x, Qt.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignLeft)

    # QtCharts does not auto-union series ranges across pre-added axes, so
    # track the true min/max across ALL series ourselves and set it explicitly
    # below -- otherwise the visible range reflects only one series arbitrarily
    # and other series' data can be silently clipped out of view.
    x_min = x_max = None
    y_min = y_max = None
    for label, points in series:
        line_series = QLineSeries()
        line_series.setName(label)
        for txn_date, value in points:
            qdt = QDateTime(txn_date.year, txn_date.month, txn_date.day, 0, 0, 0)
            x_ms = qdt.toMSecsSinceEpoch()
            y_val = float(value)
            line_series.append(x_ms, y_val)
            x_min = x_ms if x_min is None else min(x_min, x_ms)
            x_max = x_ms if x_max is None else max(x_max, x_ms)
            y_min = y_val if y_min is None else min(y_min, y_val)
            y_max = y_val if y_max is None else max(y_max, y_val)
        chart.addSeries(line_series)
        line_series.attachAxis(axis_x)
        line_series.attachAxis(axis_y)

    if x_min is not None:
        if mark_zero:
            y_min = min(y_min, 0.0)
            y_max = max(y_max, 0.0)
        if y_min == y_max:
            y_min, y_max = y_min - 1, y_max + 1
        axis_x.setRange(
            QDateTime.fromMSecsSinceEpoch(x_min), QDateTime.fromMSecsSinceEpoch(x_max)
        )
        axis_y.setRange(y_min, y_max)
        if mark_zero:
            zero_series = QLineSeries()
            zero_series.append(x_min, 0.0)
            zero_series.append(x_max, 0.0)
            pen = zero_series.pen()
            pen.setStyle(Qt.DashLine)
            pen.setColor(Qt.gray)
            zero_series.setPen(pen)
            chart.addSeries(zero_series)
            zero_series.attachAxis(axis_x)
            zero_series.attachAxis(axis_y)
            markers = chart.legend().markers(zero_series)
            if markers:
                markers[0].setVisible(False)
    return chart


def build_stacked_area_chart(title, bands, mark_zero=False):
    """Build a date/value chart of filled areas stacked bottom to top.

    bands is an ordered list of (label, points, color) triples, bottom
    band first. points is a list of (date, value) tuples holding that
    band's own contribution -- not cumulative; each band is drawn as the
    area between the running total below it and the running total
    including it, so the top edge of the last band traces the combined
    total. color is any string QColor accepts (e.g. a "#rrggbb" hex).
    mark_zero behaves as in build_line_chart.
    """
    chart = QChart()
    chart.setTitle(title)
    axis_x = QDateTimeAxis()
    axis_x.setFormat("yyyy-MM-dd")
    axis_y = QValueAxis()
    chart.addAxis(axis_x, Qt.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignLeft)

    x_min = x_max = None
    y_min = y_max = None
    running_total = None  # y-values of the cumulative total below the current band
    # QAreaSeries doesn't reparent its boundary series in a way that keeps
    # their Python wrappers alive, so without an explicit reference here
    # they get garbage-collected once this function returns, leaving the
    # chart holding dangling pointers.
    boundary_series = []

    for label, points, color in bands:
        lower_series = QLineSeries()
        upper_series = QLineSeries()
        for index, (point_date, value) in enumerate(points):
            qdt = QDateTime(point_date.year, point_date.month, point_date.day, 0, 0, 0)
            x_ms = qdt.toMSecsSinceEpoch()
            lower_y = running_total[index] if running_total else 0.0
            upper_y = lower_y + float(value)
            lower_series.append(x_ms, lower_y)
            upper_series.append(x_ms, upper_y)
            x_min = x_ms if x_min is None else min(x_min, x_ms)
            x_max = x_ms if x_max is None else max(x_max, x_ms)
            y_min = min(lower_y, upper_y) if y_min is None else min(y_min, lower_y, upper_y)
            y_max = max(lower_y, upper_y) if y_max is None else max(y_max, lower_y, upper_y)

        area = QAreaSeries(upper_series, lower_series)
        area.setName(label)
        area.setBrush(QBrush(QColor(color)))
        area.setPen(Qt.NoPen)
        chart.addSeries(area)
        area.attachAxis(axis_x)
        area.attachAxis(axis_y)
        boundary_series.extend([lower_series, upper_series])

        running_total = [upper_series.at(i).y() for i in range(upper_series.count())]

    if x_min is not None:
        if mark_zero:
            y_min = min(y_min, 0.0)
            y_max = max(y_max, 0.0)
        if y_min == y_max:
            y_min, y_max = y_min - 1, y_max + 1
        axis_x.setRange(
            QDateTime.fromMSecsSinceEpoch(x_min), QDateTime.fromMSecsSinceEpoch(x_max)
        )
        axis_y.setRange(y_min, y_max)
        if mark_zero:
            zero_series = QLineSeries()
            zero_series.append(x_min, 0.0)
            zero_series.append(x_max, 0.0)
            pen = zero_series.pen()
            pen.setStyle(Qt.DashLine)
            pen.setColor(Qt.gray)
            zero_series.setPen(pen)
            chart.addSeries(zero_series)
            zero_series.attachAxis(axis_x)
            zero_series.attachAxis(axis_y)
            markers = chart.legend().markers(zero_series)
            if markers:
                markers[0].setVisible(False)
    chart._stacked_area_boundary_series = boundary_series
    return chart


def build_bar_chart(title, categories, values):
    """Build a single-series bar chart.

    categories is a list of x-axis labels; values is a parallel list of
    numeric values. Categories aren't drawn on the axis (too dense to be
    legible when there are many bars) -- instead the category for a bar
    is shown in a tooltip on hover.
    """
    chart = QChart()
    chart.setTitle(title)
    chart.legend().setVisible(False)

    bar_set = QBarSet(title)
    for value in values:
        bar_set.append(float(value))

    series = QBarSeries()
    series.append(bar_set)

    def _on_bar_hovered(status, index, _bar_set=None):
        if status and 0 <= index < len(categories):
            QToolTip.showText(QCursor.pos(), categories[index])
        else:
            QToolTip.hideText()

    series.hovered.connect(_on_bar_hovered)
    chart.addSeries(series)

    axis_x = QBarCategoryAxis()
    axis_x.append(categories)
    axis_x.setLabelsVisible(False)
    chart.addAxis(axis_x, Qt.AlignBottom)
    series.attachAxis(axis_x)

    axis_y = QValueAxis()
    if values:
        y_min = min(0.0, float(min(values)))
        y_max = float(max(values))
        if y_min == y_max:
            y_min, y_max = y_min - 1, y_max + 1
        axis_y.setRange(y_min, y_max)
    chart.addAxis(axis_y, Qt.AlignLeft)
    series.attachAxis(axis_y)

    return chart


def build_pie_chart(title, categories):
    """Build a pie chart with one slice per category.

    categories is a list of (label, value) pairs, e.g. from
    compute_spending_by_category(). Each slice shows its percentage of the
    total; hovering a slice shows its label and value in a tooltip.
    """
    chart = QChart()
    chart.setTitle(title)

    series = QPieSeries()
    for label, value in categories:
        pie_slice = series.append(label, float(value))
        pie_slice.setLabelVisible(True)

    def _on_slice_hovered(pie_slice, state):
        if state:
            QToolTip.showText(QCursor.pos(), f"{pie_slice.label()}: {pie_slice.value():.2f}")
        else:
            QToolTip.hideText()

    series.hovered.connect(_on_slice_hovered)
    chart.addSeries(series)

    return chart
