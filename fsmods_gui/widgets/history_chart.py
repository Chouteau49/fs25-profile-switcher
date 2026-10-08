"""Minimal line chart (QPainter) for a statistic's history."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ..career.formatting import format_value


class HistoryChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._points: list[tuple[datetime, float]] = []
        self._unit = ""
        self.setMinimumHeight(180)

    def set_points(self, points: list[tuple[datetime, float]], unit: str = "") -> None:
        self._points = points
        self._unit = unit
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        p.fillRect(rect, self.palette().base())
        p.setPen(QPen(QColor("#bbb")))
        p.drawRect(rect.adjusted(0, 0, -1, -1))
        if not self._points:
            p.setPen(self.palette().text().color())
            p.drawText(
                rect, Qt.AlignmentFlag.AlignCenter,
                "Pas encore d'historique : il se construit à chaque synchronisation.",
            )
            return

        left, right, top, bottom = 90, 20, 16, 28
        plot = QRectF(left, top, max(1, rect.width() - left - right),
                      max(1, rect.height() - top - bottom))
        values = [v for _, v in self._points]
        lo, hi = min(values), max(values)
        if hi == lo:
            lo, hi = lo - 1, hi + 1
        t0 = self._points[0][0].timestamp()
        t1 = self._points[-1][0].timestamp()
        span = (t1 - t0) or 1.0

        def to_xy(when: datetime, value: float) -> QPointF:
            x = plot.left() + ((when.timestamp() - t0) / span if t1 > t0 else 0.5) * plot.width()
            y = plot.bottom() - (value - lo) / (hi - lo) * plot.height()
            return QPointF(x, y)

        text_color = self.palette().text().color()
        p.setPen(QPen(QColor("#ddd")))
        for i in range(5):
            y = plot.top() + plot.height() * i / 4
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        p.setPen(text_color)
        for i in range(5):
            y = plot.top() + plot.height() * i / 4
            val = hi - (hi - lo) * i / 4
            p.drawText(
                QRectF(0, y - 8, left - 6, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                format_value(val, self._unit),
            )
        p.drawText(QPointF(plot.left(), rect.height() - 8),
                   self._points[0][0].strftime("%d/%m/%Y"))
        end_label = self._points[-1][0].strftime("%d/%m/%Y")
        p.drawText(QPointF(plot.right() - p.fontMetrics().horizontalAdvance(end_label),
                           rect.height() - 8), end_label)

        coords = [to_xy(w, v) for w, v in self._points]
        accent = QColor("#2b6cb0")
        if len(coords) > 1:
            p.setPen(QPen(accent, 2))
            p.drawPolyline(QPolygonF(coords))
        p.setPen(QPen(accent, 1))
        p.setBrush(accent)
        for pt in coords:
            p.drawEllipse(pt, 3, 3)
