"""Gráficos leves desenhados com QPainter (sem dependências extras)."""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..theme import get_theme
from ..utils import format_bytes


def _contrast_text(color: QColor, dark: str, light: str) -> QColor:
    """Escolhe texto claro/escuro conforme a luminância do arco."""
    luminance = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
    return QColor(dark if luminance > 150 else light)


class DonutChart(QWidget):
    """Donut de distribuição com total central, percentuais e legenda."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, int, str]] = []
        self.setMinimumHeight(210)
        self.setMinimumWidth(320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        get_theme().changed.connect(self.update)

    def set_data(self, data: list[tuple[str, int, str]]) -> None:
        self._data = [(label, max(0, int(value)), color) for label, value, color in data]
        row_h = max(28.0, get_theme().fs(28))
        self.setMinimumHeight(max(210, int(min(len(self._data), 6) * row_h + 24)))
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(450, 240)

    def paintEvent(self, event) -> None:  # noqa: N802
        theme = get_theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(theme.color("surface")))
        total = sum(v for _, v, _ in self._data)
        legend_w = min(230, max(150, int(w * 0.42)))
        ring_area = min(h - 28, w - legend_w - 40)
        ring_area = max(90, ring_area)
        cx = 20 + ring_area / 2
        cy = h / 2
        outer = QRectF(cx - ring_area / 2, cy - ring_area / 2, ring_area, ring_area)
        pen_w = max(14, ring_area * 0.12)
        arc_rect = outer.adjusted(pen_w / 2, pen_w / 2, -pen_w / 2, -pen_w / 2)

        track = QPen(QColor(theme.color("surface_3")), pen_w)
        track.setCapStyle(Qt.FlatCap)
        p.setPen(track)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(arc_rect)

        if total > 0:
            start = 90 * 16
            f = QFont("Segoe UI")
            f.setPixelSize(theme.fs(10))
            f.setWeight(QFont.Bold)
            for _label, value, color in self._data:
                span = -int(round(value / total * 360 * 16))
                if span == 0:
                    continue
                pen = QPen(QColor(color), pen_w)
                pen.setCapStyle(Qt.FlatCap)
                p.setPen(pen)
                p.drawArc(arc_rect, start, span)

                pct = value / total * 100
                if pct >= 7:
                    mid_angle = math.radians((start + span / 2) / 16.0)
                    if len(self._data) == 1:
                        mid_angle = math.radians(90)
                    radius = ring_area / 2 - pen_w / 2
                    tx = cx + math.cos(mid_angle) * radius
                    ty = cy - math.sin(mid_angle) * radius
                    p.setFont(f)
                    p.setPen(_contrast_text(QColor(color), "#042126", "#ffffff"))
                    label = f"{pct:.0f}%" if pct >= 10 else f"{pct:.1f}%"
                    metrics = p.fontMetrics()
                    tw = metrics.horizontalAdvance(label) + 4
                    th = metrics.height()
                    p.drawText(
                        QRectF(tx - tw / 2, ty - th / 2, tw, th),
                        Qt.AlignCenter,
                        label,
                    )
                start += span

        # Texto central
        p.setPen(QColor(theme.color("muted")))
        f = QFont("Segoe UI")
        f.setPixelSize(theme.fs(11))
        p.setFont(f)
        p.drawText(
            QRectF(cx - 70, cy - 28, 140, 20), Qt.AlignCenter, "ESPAÇO TOTAL"
        )
        p.setPen(QColor(theme.color("text")))
        f.setPixelSize(theme.fs(20) if ring_area > 140 else theme.fs(16))
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.drawText(
            QRectF(cx - 82, cy - 8, 164, 32),
            Qt.AlignCenter,
            format_bytes(total),
        )

        # Legenda com percentual sempre visível, como em um painel de BI.
        row_h = max(28.0, theme.fs(28))
        x = 20 + ring_area + 26
        y = max(16.0, h / 2 - min(len(self._data), 6) * row_h / 2)
        reserve_pct = 62
        for i, (label, value, color) in enumerate(self._data[:6]):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(x, y + i * row_h + 7, 9, 9), 4.5, 4.5)
            p.setPen(QColor(theme.color("text")))
            f.setPixelSize(theme.fs(12))
            f.setWeight(QFont.Normal)
            p.setFont(f)
            pct = (value / total * 100) if total else 0
            text_w = max(40, w - x - reserve_pct - 18)
            text = p.fontMetrics().elidedText(label, Qt.ElideMiddle, text_w)
            p.drawText(
                QRectF(x + 17, y + i * row_h, text_w, 24),
                Qt.AlignVCenter | Qt.AlignLeft,
                text,
            )
            p.setPen(QColor(theme.color("muted")))
            f.setPixelSize(theme.fs(11))
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.drawText(
                QRectF(w - reserve_pct, y + i * row_h, reserve_pct - 4, 24),
                Qt.AlignVCenter | Qt.AlignRight,
                f"{pct:.0f}%" if pct >= 10 else f"{pct:.1f}%",
            )
        if not self._data:
            p.setPen(QColor(theme.color("muted")))
            f.setPixelSize(theme.fs(12))
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.drawText(
                QRectF(x, h / 2 - 12, max(80, w - x - 20), 24),
                Qt.AlignVCenter | Qt.AlignLeft,
                "Nenhuma pasta analisada ainda",
            )
        p.end()


class BarList(QWidget):
    """Ranking de diretórios com barras e participação percentual."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[tuple[str, int]] = []
        self._total = 0
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        get_theme().changed.connect(self.update)

    def set_data(self, rows: list[tuple[str, int]], total: int = 0) -> None:
        self._rows = [(label, max(0, int(value))) for label, value in rows]
        self._total = max(0, int(total))
        row_h = max(42.0, get_theme().fs(42))
        self.setMinimumHeight(max(120, int(len(self._rows) * row_h + 14)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        theme = get_theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        p.fillRect(self.rect(), QColor(theme.color("surface")))
        if not self._rows:
            p.setPen(QColor(theme.color("muted")))
            f = QFont("Segoe UI")
            f.setPixelSize(theme.fs(12))
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, "Nenhum diretório para exibir")
            p.end()
            return
        maximum = max((value for _, value in self._rows), default=1) or 1
        total = self._total or sum(value for _, value in self._rows) or 1
        row_h = max(42, theme.fs(42))
        f = QFont("Segoe UI")
        for i, (label, value) in enumerate(self._rows):
            y = 6 + i * row_h
            f.setPixelSize(theme.fs(12))
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(QColor(theme.color("text")))
            text = p.fontMetrics().elidedText(label, Qt.ElideMiddle, max(60, w - 150))
            p.drawText(QRectF(0, y, w - 148, 20), Qt.AlignVCenter | Qt.AlignLeft, text)
            p.setPen(QColor(theme.color("muted")))
            f.setPixelSize(theme.fs(11))
            f.setWeight(QFont.Normal)
            p.setFont(f)
            pct = value / total * 100 if total else 0
            pct_text = f"{pct:.0f}%" if pct >= 10 else f"{pct:.1f}%"
            p.drawText(
                QRectF(w - 142, y, 142, 20),
                Qt.AlignVCenter | Qt.AlignRight,
                f"{format_bytes(value)}   ·   {pct_text}",
            )

            track = QRectF(0, y + 25, w, 6)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.color("surface_3")))
            p.drawRoundedRect(track, 3, 3)
            ratio = max(0.02, value / maximum)
            fill = QRectF(0, y + 25, max(6.0, w * ratio), 6)
            grad = QLinearGradient(fill.topLeft(), fill.topRight())
            colors = theme.chart_colors()
            grad.setColorAt(0, QColor(colors[i % len(colors)]))
            grad.setColorAt(1, QColor(theme.color("primary")))
            p.setBrush(grad)
            p.drawRoundedRect(fill, 3, 3)
        p.end()
