"""A small, reusable "the computer is working" spinner widget, plus a helper
to run slow work off the main thread so the spinner's own animation (and the
rest of the UI) keeps running while it waits.

Self-animating via its own QTimer: call start() to show it and begin
spinning, stop() to hide it again. A blocking synchronous call on the main
thread freezes the event loop -- including the spinner's own repaints -- for
however long it runs, so anything more than a blink should go through
run_in_background() below rather than being called directly between
start()/stop().
"""

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QWidget

_TICK_INTERVAL_MS = 80
_STEP_DEGREES = 30
_ARC_SPAN_DEGREES = 270


class BusyIndicator(QWidget):
    """A small rotating-arc spinner, hidden until start() is called."""

    def __init__(self, parent=None, diameter=18):
        super().__init__(parent)
        self._diameter = diameter
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._advance)
        self.setFixedSize(diameter, diameter)
        self.hide()

    def start(self):
        self._angle = 0
        self.show()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()

    def is_spinning(self):
        return self._timer.isActive()

    def _advance(self):
        self._angle = (self._angle + _STEP_DEGREES) % 360
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen_width = max(2, self._diameter // 9)
        pen = QPen(self.palette().highlight().color())
        pen.setWidth(pen_width)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        margin = pen_width
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        # Qt angles are in 1/16ths of a degree, measured counterclockwise from 3 o'clock.
        painter.drawArc(rect, -self._angle * 16, _ARC_SPAN_DEGREES * 16)
        painter.end()


class _Worker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001 -- reported to on_error, not swallowed
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(result)


def run_in_background(fn, indicator, on_success, on_error=None, parent=None):
    """Run `fn` (a slow, argument-less callable) on a background thread while
    `indicator` spins, delivering the result back on the calling (Qt main)
    thread via `on_success` (or `on_error`, default: re-raise) when done.

    `fn` must not touch Qt widgets or a shared, non-thread-safe resource
    (e.g. a database connection also used from the main thread) -- it runs
    on a different thread. Returns the QThread; the caller must keep a
    reference to it (e.g. as an attribute on self) until it finishes, since
    PySide destroys a QThread whose last Python reference disappears while
    it's still running.
    """
    indicator.start()
    thread = _Worker(fn, parent=parent)

    def _handle_success(result):
        indicator.stop()
        on_success(result)

    def _handle_error(message):
        indicator.stop()
        if on_error is not None:
            on_error(message)
        else:
            raise RuntimeError(message)

    thread.succeeded.connect(_handle_success)
    thread.failed.connect(_handle_error)
    thread.start()
    return thread
