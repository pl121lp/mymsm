"""Light/dark theme palettes and the app-wide toggle.

Forces the Fusion style unconditionally: native styles (particularly on
Linux) often ignore a custom QPalette for parts of their widget chrome, so a
custom dark palette only renders reliably under Fusion.
"""

from PySide6.QtCharts import QChart
from PySide6.QtGui import QColor, QPalette

_dark = False

LIGHT_PALETTE = QPalette()

DARK_PALETTE = QPalette()
DARK_PALETTE.setColor(QPalette.Window, QColor(53, 53, 53))
DARK_PALETTE.setColor(QPalette.WindowText, QColor(222, 222, 222))
DARK_PALETTE.setColor(QPalette.Base, QColor(35, 35, 35))
DARK_PALETTE.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
DARK_PALETTE.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
DARK_PALETTE.setColor(QPalette.ToolTipText, QColor(222, 222, 222))
DARK_PALETTE.setColor(QPalette.Text, QColor(222, 222, 222))
DARK_PALETTE.setColor(QPalette.Button, QColor(53, 53, 53))
DARK_PALETTE.setColor(QPalette.ButtonText, QColor(222, 222, 222))
DARK_PALETTE.setColor(QPalette.BrightText, QColor(255, 60, 60))
DARK_PALETTE.setColor(QPalette.Link, QColor(100, 170, 255))
DARK_PALETTE.setColor(QPalette.Highlight, QColor(60, 120, 200))
DARK_PALETTE.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
DARK_PALETTE.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
DARK_PALETTE.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
DARK_PALETTE.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))


def apply_theme(app, dark):
    """Apply the light or dark palette app-wide and remember the choice."""
    global _dark
    _dark = dark
    app.setStyle("Fusion")
    app.setPalette(DARK_PALETTE if dark else LIGHT_PALETTE)


def is_dark():
    return _dark


def chart_theme():
    return QChart.ChartTheme.ChartThemeDark if _dark else QChart.ChartTheme.ChartThemeLight
