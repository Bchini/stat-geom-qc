# -*- coding: utf-8 -*-
"""Classe principale du plugin STAT GEOM QC : enregistrement du menu / de la
barre d'outils et gestion du panneau dockable."""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .stat_geom_dockwidget import StatGeomDockWidget

PLUGIN_DIR = os.path.dirname(__file__)
MENU_NAME = "STAT GEOM QC"


class StatGeomQCPlugin:
    """Point d'entrée du plugin (interface iface QGIS)."""

    def __init__(self, iface):
        self.iface = iface
        self.dock = None
        self.action = None

    def initGui(self):  # noqa: N802 (API QGIS)
        icon_path = os.path.join(PLUGIN_DIR, "icon.svg")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.action = QAction(icon, "STAT GEOM QC — Contrôle qualité", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self.toggle_panel)

        self.iface.addPluginToVectorMenu(MENU_NAME, self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action is not None:
            self.iface.removePluginVectorMenu(MENU_NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None
        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

    def toggle_panel(self, checked=None):
        if self.dock is None:
            self.dock = StatGeomDockWidget(self.iface, self.iface.mainWindow())
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
            self.dock.visibilityChanged.connect(self._on_visibility_changed)
        visible = not self.dock.isVisible()
        self.dock.setVisible(visible)
        if self.action is not None:
            self.action.setChecked(visible)

    def _on_visibility_changed(self, visible):
        if self.action is not None:
            self.action.setChecked(visible)
