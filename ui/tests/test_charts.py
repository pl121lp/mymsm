from decimal import Decimal

from charts import build_pie_chart


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
