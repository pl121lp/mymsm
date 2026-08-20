"""Dictionaries tab: browse categories and investments across all accounts."""

from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QValueAxis
from PySide6.QtCore import QDate, QDateTime, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import data
from models import CategoryTransactionTableModel, DictionaryListModel


class CategoriesPane(QWidget):
    def __init__(self, conn, report_error, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error

        self.list_model = DictionaryListModel()
        self.detail_model = CategoryTransactionTableModel()

        self.list_view = QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selected)

        self.detail_view = QTableView()
        self.detail_view.setModel(self.detail_model)
        self.detail_view.horizontalHeader().setStretchLastSection(True)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.list_view)
        splitter.addWidget(self.detail_view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self._reload()

    def _reload(self):
        try:
            categories = data.list_categories(self._conn)
        except Exception as exc:
            self._report_error(f"Failed to load categories: {exc}")
            return
        self.list_model.set_items(categories)

    def _on_selected(self, selected=None, deselected=None):
        indexes = self.list_view.selectionModel().selectedIndexes()
        if not indexes:
            self.detail_model.set_transactions([])
            return
        category_id = self.list_model.id_at(indexes[0].row())
        try:
            transactions = data.list_category_transactions(self._conn, category_id)
        except Exception as exc:
            self._report_error(f"Failed to load category transactions: {exc}")
            return
        self.detail_model.set_transactions(transactions)
        self.detail_view.resizeColumnsToContents()


class InvestmentsPane(QWidget):
    def __init__(self, conn, report_error, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error

        self.list_model = DictionaryListModel()
        self.list_view = QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selected)

        self.price_chart_view = QChartView()
        self.price_chart_view.setRenderHint(QPainter.Antialiasing)
        self.quantity_chart_view = QChartView()
        self.quantity_chart_view.setRenderHint(QPainter.Antialiasing)

        charts_widget = QWidget()
        charts_layout = QVBoxLayout(charts_widget)
        charts_layout.addWidget(self.price_chart_view)
        charts_layout.addWidget(self.quantity_chart_view)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.list_view)
        splitter.addWidget(charts_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self._reload()

    def _reload(self):
        try:
            securities = data.list_securities(self._conn)
        except Exception as exc:
            self._report_error(f"Failed to load investments: {exc}")
            return
        self.list_model.set_items(securities)

    def _on_selected(self, selected=None, deselected=None):
        indexes = self.list_view.selectionModel().selectedIndexes()
        if not indexes:
            self.price_chart_view.setChart(QChart())
            self.quantity_chart_view.setChart(QChart())
            return
        security_id = self.list_model.id_at(indexes[0].row())
        try:
            history = data.list_security_history(self._conn, security_id)
        except Exception as exc:
            self._report_error(f"Failed to load investment history: {exc}")
            return

        price_by_account = {}
        qty_by_account = {}
        for _account_id, account_name, txn_date, price, cumulative_qty in history:
            if price is not None:
                price_by_account.setdefault(account_name, []).append((txn_date, price))
            qty_by_account.setdefault(account_name, []).append((txn_date, cumulative_qty))

        self.price_chart_view.setChart(self._build_line_chart("Price", price_by_account))
        self.quantity_chart_view.setChart(
            self._build_line_chart("Quantity Held", qty_by_account)
        )

    @staticmethod
    def _build_line_chart(title, series_by_account):
        chart = QChart()
        chart.setTitle(title)
        axis_x = QDateTimeAxis()
        axis_x.setFormat("yyyy-MM-dd")
        axis_y = QValueAxis()
        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        for account_name, points in series_by_account.items():
            series = QLineSeries()
            series.setName(account_name)
            for txn_date, value in points:
                qdt = QDateTime(txn_date.year, txn_date.month, txn_date.day, 0, 0, 0)
                series.append(qdt.toMSecsSinceEpoch(), float(value))
            chart.addSeries(series)
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)
        return chart
