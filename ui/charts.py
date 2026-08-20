"""Shared QtCharts line-chart builder for time-series widgets."""

from PySide6.QtCharts import QChart, QDateTimeAxis, QLineSeries, QValueAxis
from PySide6.QtCore import QDateTime, Qt


def build_line_chart(title, series):
    """Build a multi-series date/value line chart.

    series is an iterable of (label, points) pairs, where points is a list
    of (date, value) tuples.
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
        if y_min == y_max:
            y_min, y_max = y_min - 1, y_max + 1
        axis_x.setRange(
            QDateTime.fromMSecsSinceEpoch(x_min), QDateTime.fromMSecsSinceEpoch(x_max)
        )
        axis_y.setRange(y_min, y_max)
    return chart
