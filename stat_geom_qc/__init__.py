# -*- coding: utf-8 -*-
"""STAT GEOM QC — plugin QGIS de contrôle qualité géométrique.

Point d'entrée QGIS : classFactory() instancie la classe du plugin.
"""


def classFactory(iface):  # noqa: N802 (API QGIS)
    from .stat_geom_qc import StatGeomQCPlugin

    return StatGeomQCPlugin(iface)
