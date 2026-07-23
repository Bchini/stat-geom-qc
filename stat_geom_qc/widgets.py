# -*- coding: utf-8 -*-
"""Widgets personnalisés : jauge de score circulaire et carte d'indicateur."""

from qgis.PyQt.QtCore import Qt, QRectF, QSize
from qgis.PyQt.QtGui import QColor, QFont, QPainter, QPen
from qgis.PyQt.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class ScoreGauge(QWidget):
    """Jauge circulaire (anneau) affichant un score 0..100."""

    def __init__(self, parent=None, diameter=132):
        super().__init__(parent)
        self._score = 0.0
        self._color = QColor("#94a3b8")
        self._grade = ""
        self._diameter = diameter
        self.setMinimumSize(QSize(diameter, diameter))
        self.setMaximumSize(QSize(diameter, diameter))

    def set_score(self, score, color_hex, grade=""):
        self._score = max(0.0, min(100.0, float(score)))
        self._color = QColor(color_hex)
        self._grade = grade or ""
        self.update()

    def paintEvent(self, event):  # noqa: N802 (API Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        side = min(self.width(), self.height())
        pen_w = max(10, int(side * 0.11))
        margin = pen_w / 2 + 2
        rect = QRectF(margin, margin, side - 2 * margin, side - 2 * margin)

        # Anneau de fond
        p.setPen(QPen(QColor("#e2e8f0"), pen_w, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 0, 360 * 16)

        # Arc de score (départ en haut, sens horaire)
        span = int(-self._score / 100.0 * 360 * 16)
        p.setPen(QPen(self._color, pen_w, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 90 * 16, span)

        # Valeur au centre
        p.setPen(self._color)
        f = QFont()
        f.setPointSizeF(side * 0.24)
        f.setBold(True)
        p.setFont(f)
        txt = ("%g" % self._score) if self._score == int(self._score) else ("%.1f" % self._score)
        p.drawText(rect, Qt.AlignCenter, txt)

        p.end()


class MetricCard(QFrame):
    """Petite carte : valeur en gros + libellé, colorée selon la gravité."""

    _PALETTE = {
        "ok": ("#0ea5e9", "#e0f2fe", "#bae6fd"),
        "err": ("#dc2626", "#fef2f2", "#fecaca"),
        "warn": ("#d97706", "#fffbeb", "#fde68a"),
        "muted": ("#475569", "#f1f5f9", "#e2e8f0"),
    }

    def __init__(self, value, label, severity="muted", parent=None):
        super().__init__(parent)
        fg, bg, border = self._PALETTE.get(severity, self._PALETTE["muted"])
        self.setObjectName("metricCard")
        self.setStyleSheet(
            "#metricCard{background:%s;border:1px solid %s;border-radius:12px;}" % (bg, border)
        )
        self.setMinimumWidth(104)
        self.setFixedHeight(64)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(0)

        self.v = QLabel(str(value))
        vf = QFont()
        vf.setPointSize(16)
        vf.setBold(True)
        self.v.setFont(vf)
        self.v.setStyleSheet("color:%s;background:transparent;" % fg)

        self.lbl = QLabel(label)
        self.lbl.setStyleSheet("color:#64748b;background:transparent;font-size:11px;")

        lay.addWidget(self.v)
        lay.addWidget(self.lbl)
