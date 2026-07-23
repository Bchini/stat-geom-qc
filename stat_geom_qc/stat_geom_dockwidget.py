# -*- coding: utf-8 -*-
"""Panneau dockable STAT GEOM QC : sélection de couche, options, analyse,
affichage moderne des résultats (score de correctness, indicateurs, rapport)
et actions QGIS (sélection des entités, couche d'erreurs, exports)."""

import os
import tempfile
import webbrowser

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsDockWidget, QgsMapLayerComboBox

try:
    from qgis.core import QgsMapLayerProxyModel
    _VECTOR_FILTER = QgsMapLayerProxyModel.VectorLayer
except Exception:  # pragma: no cover
    _VECTOR_FILTER = None

from . import report
from .analysis_engine import (
    AnalysisCancelled,
    AnalysisOptions,
    GeomAnalyzer,
    RepairOptions,
)
from .flow_layout import FlowLayout
from .widgets import MetricCard, ScoreGauge


PANEL_QSS = """
#sgContent { background:#f8fafc; color:#0f172a; }
#sgContent QLabel { background:transparent; color:#0f172a; }
QGroupBox { border:1px solid #e2e8f0; border-radius:12px; margin-top:12px;
    background:#ffffff; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; color:#334155; }
QPushButton { border:1px solid #cbd5e1; border-radius:8px; padding:7px 12px;
    background:#ffffff; color:#0f172a; }
QPushButton:hover { background:#eef2f7; }
QPushButton:disabled { color:#94a3b8; border-color:#e2e8f0; }
QPushButton#primary { background:#0ea5e9; color:#ffffff; border:none; font-weight:600;
    padding:10px 14px; }
QPushButton#primary:hover { background:#0284c7; }
QPushButton#primary:disabled { background:#94a3b8; }
QPushButton#danger { color:#b91c1c; border-color:#fecaca; background:#fef2f2; }
QPushButton#danger:hover { background:#fee2e2; }
QComboBox, QDoubleSpinBox { border:1px solid #cbd5e1; border-radius:8px; padding:5px 8px;
    background:#ffffff; color:#0f172a; }
QCheckBox { color:#334155; }
QTabWidget::pane { border:1px solid #e2e8f0; border-radius:12px; background:#ffffff; top:-1px; }
QTabBar::tab { padding:7px 14px; margin-right:3px; border-top-left-radius:8px;
    border-top-right-radius:8px; background:#e2e8f0; color:#475569; }
QTabBar::tab:selected { background:#ffffff; color:#0f172a; font-weight:600; }
QTableWidget { border:none; background:#ffffff; gridline-color:#eef2f7; color:#0f172a; }
QHeaderView::section { background:#f1f5f9; color:#475569; padding:6px; border:none;
    border-bottom:1px solid #e2e8f0; font-weight:600; }
QTextBrowser { border:none; background:#ffffff; }
QProgressBar { border:1px solid #e2e8f0; border-radius:8px; background:#eef2f7;
    text-align:center; color:#334155; height:18px; }
QProgressBar::chunk { border-radius:7px; background:#0ea5e9; }
QScrollArea { border:none; background:#f8fafc; }
"""

_SUPPORTED = "GIS (*.shp *.tab *.geojson *.gpkg *.kml *.json);;Tous (*.*)"

_CATEGORY_LABELS = {
    "null_empty": "Nulle/Vide",
    "invalid": "Invalide",
    "self_intersection": "Auto-intersection",
    "overlap": "Chevauchement",
    "small": "Petit polygone",
    "duplicate": "Doublon",
    "agl": "AGL>AMSL",
}

# Catégories d'entités problématiques (union pour sélection)
_ALL_CATEGORIES = ("null_empty", "invalid", "self_intersection",
                   "overlap", "small", "duplicate", "agl")
# Catégories dont les entités possèdent une géométrie (pour la couche d'erreurs)
_GEOM_CATEGORIES = ("invalid", "self_intersection", "overlap", "small", "duplicate", "agl")


class StatGeomDockWidget(QgsDockWidget):
    """Panneau principal du plugin."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self._result = None
        self._analyzing = False
        self._cancel = False
        self.setWindowTitle("STAT GEOM QC")
        self._build_ui()

    # ── Construction de l'UI ──────────────────────────────────────────────

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        content.setObjectName("sgContent")
        content.setStyleSheet(PANEL_QSS)
        root = QVBoxLayout(content)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # -- En-tête --
        header = QHBoxLayout()
        logo = QLabel("◈")
        logo.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0ea5e9,stop:1 #6366f1);"
            "color:white;border-radius:10px;font-size:20px;font-weight:bold;"
        )
        logo.setFixedSize(38, 38)
        logo.setAlignment(Qt.AlignCenter)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        t = QLabel("STAT GEOM QC")
        t.setStyleSheet("font-size:16px;font-weight:700;")
        sub = QLabel("Contrôle qualité géométrique")
        sub.setStyleSheet("color:#64748b;font-size:11px;")
        title_box.addWidget(t)
        title_box.addWidget(sub)
        header.addWidget(logo)
        header.addLayout(title_box)
        header.addStretch()
        root.addLayout(header)

        # -- Source --
        src_group = QGroupBox("Source de données")
        src_lay = QVBoxLayout(src_group)
        self.layer_combo = QgsMapLayerComboBox()
        if _VECTOR_FILTER is not None:
            self.layer_combo.setFilters(_VECTOR_FILTER)
        row = QHBoxLayout()
        btn_file = QPushButton("📂 Charger un fichier…")
        btn_file.clicked.connect(self._on_load_file)
        row.addWidget(self.layer_combo, 1)
        row.addWidget(btn_file)
        src_lay.addLayout(row)
        root.addWidget(src_group)

        # -- Options --
        opt_group = QGroupBox("Options d'analyse")
        opt_lay = QGridLayout(opt_group)
        opt_lay.setVerticalSpacing(8)
        opt_lay.addWidget(QLabel("Seuil petits polygones (m²)"), 0, 0)
        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setRange(0.0, 1_000_000.0)
        self.spin_threshold.setDecimals(2)
        self.spin_threshold.setValue(2.0)
        opt_lay.addWidget(self.spin_threshold, 0, 1)
        self.chk_topology = QCheckBox("Contrôles topologiques (détails d'invalidité)")
        self.chk_topology.setChecked(True)
        self.chk_overlaps = QCheckBox("Détecter les chevauchements/intersections entre polygones")
        self.chk_overlaps.setChecked(True)
        self.chk_dup = QCheckBox("Détecter les doublons")
        self.chk_dup.setChecked(True)
        self.chk_buildings = QCheckBox("Contrôle bâtiments (AGL vs AMSL)")
        self.chk_buildings.setChecked(False)  # désactivé par défaut (à activer au besoin)
        opt_lay.addWidget(self.chk_topology, 1, 0, 1, 2)
        opt_lay.addWidget(self.chk_overlaps, 2, 0, 1, 2)
        opt_lay.addWidget(self.chk_dup, 3, 0, 1, 2)
        opt_lay.addWidget(self.chk_buildings, 4, 0, 1, 2)
        root.addWidget(opt_group)

        # -- Bouton d'analyse + progression --
        self.btn_analyze = QPushButton("▶  Analyser la couche")
        self.btn_analyze.setObjectName("primary")
        self.btn_analyze.clicked.connect(self._run_analysis)
        root.addWidget(self.btn_analyze)

        prog_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.btn_cancel = QPushButton("✖")
        self.btn_cancel.setFixedWidth(38)
        self.btn_cancel.clicked.connect(self._on_cancel)
        prog_row.addWidget(self.progress, 1)
        prog_row.addWidget(self.btn_cancel)
        self.prog_widget = QWidget()
        self.prog_widget.setLayout(prog_row)
        self.prog_widget.setVisible(False)
        root.addWidget(self.prog_widget)

        self.status_label = QLabel("Sélectionnez une couche puis lancez l'analyse.")
        self.status_label.setStyleSheet("color:#64748b;font-size:12px;")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        # -- Bloc résultats (masqué au départ) --
        self.results_widget = QWidget()
        res_lay = QVBoxLayout(self.results_widget)
        res_lay.setContentsMargins(0, 0, 0, 0)
        res_lay.setSpacing(12)

        # Bandeau score
        score_group = QGroupBox("Score de correctness")
        score_row = QHBoxLayout(score_group)
        self.gauge = ScoreGauge()
        score_col = QVBoxLayout()
        self.grade_label = QLabel("—")
        self.grade_label.setStyleSheet("font-size:20px;font-weight:700;")
        self.grade_desc = QLabel("")
        self.grade_desc.setStyleSheet("color:#64748b;font-size:12px;")
        self.grade_desc.setWordWrap(True)
        score_col.addStretch()
        score_col.addWidget(self.grade_label)
        score_col.addWidget(self.grade_desc)
        score_col.addStretch()
        score_row.addWidget(self.gauge)
        score_row.addLayout(score_col, 1)
        res_lay.addWidget(score_group)

        # Onglets
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_summary_tab(), "Synthèse")
        self.tabs.addTab(self._build_quality_tab(), "Qualité")
        self.tabs.addTab(self._build_attributes_tab(), "Attributs")
        self.tabs.addTab(self._build_report_tab(), "Rapport")
        res_lay.addWidget(self.tabs)

        # Barre d'actions
        actions = QGroupBox("Actions")
        act_lay = FlowLayout(actions, margin=8, spacing=8)
        self.btn_select = QPushButton("🎯 Sélectionner les entités")
        self.btn_select.clicked.connect(self._select_features)
        self.btn_errlayer = QPushButton("🧩 Créer couche d'erreurs")
        self.btn_errlayer.clicked.connect(self._create_error_layer)
        self.btn_repair = QPushButton("🛠 Réparer → nouveau fichier")
        self.btn_repair.setObjectName("danger")
        self.btn_repair.setToolTip(
            "Choisir les erreurs à corriger (cases à cocher) et écrire le "
            "résultat dans un nouveau fichier, sans modifier la couche d'origine."
        )
        self.btn_repair.clicked.connect(self._repair_geometries)
        self.btn_browser = QPushButton("🌐 Rapport navigateur")
        self.btn_browser.clicked.connect(self._open_in_browser)
        self.btn_html = QPushButton("⬇ HTML")
        self.btn_html.clicked.connect(lambda: self._export("html"))
        self.btn_csv = QPushButton("⬇ CSV")
        self.btn_csv.clicked.connect(lambda: self._export("csv"))
        self.btn_json = QPushButton("⬇ JSON")
        self.btn_json.clicked.connect(lambda: self._export("json"))
        for b in (self.btn_select, self.btn_errlayer, self.btn_repair,
                  self.btn_browser, self.btn_html, self.btn_csv, self.btn_json):
            act_lay.addWidget(b)
        res_lay.addWidget(actions)

        self.results_widget.setVisible(False)
        root.addWidget(self.results_widget)
        root.addStretch()

        scroll.setWidget(content)
        self.setWidget(scroll)

    def _build_summary_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)

        cards_holder = QWidget()
        self.cards_layout = FlowLayout(cards_holder, margin=0, spacing=8)
        lay.addWidget(cards_holder)

        bars_title = QLabel("Décomposition du score")
        bars_title.setStyleSheet("color:#334155;font-weight:600;")
        lay.addWidget(bars_title)
        self.bars_holder = QWidget()
        self.bars_layout = QVBoxLayout(self.bars_holder)
        self.bars_layout.setContentsMargins(0, 0, 0, 0)
        self.bars_layout.setSpacing(6)
        lay.addWidget(self.bars_holder)
        lay.addStretch()
        return w

    def _build_quality_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        self.quality_table = QTableWidget(0, 2)
        self.quality_table.setHorizontalHeaderLabels(["Indicateur", "Valeur"])
        self.quality_table.verticalHeader().setVisible(False)
        self.quality_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.quality_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.quality_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.quality_table)
        lay.addWidget(QLabel("Détails d'invalidité"))
        self.invalid_browser = QTextBrowser()
        self.invalid_browser.setMaximumHeight(150)
        lay.addWidget(self.invalid_browser)
        return w

    def _build_attributes_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        info = QLabel("Aperçu des premières entités (attributs).")
        info.setStyleSheet("color:#64748b;font-size:11px;")
        lay.addWidget(info)
        self.attr_table = QTableWidget(0, 0)
        self.attr_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.attr_table.setAlternatingRowColors(True)
        lay.addWidget(self.attr_table)
        return w

    def _build_report_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        self.report_browser = QTextBrowser()
        self.report_browser.setOpenExternalLinks(True)
        lay.addWidget(self.report_browser)
        return w

    # ── Actions source ────────────────────────────────────────────────────

    def _on_load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Charger une couche vectorielle", "", _SUPPORTED
        )
        if not path:
            return
        name = os.path.splitext(os.path.basename(path))[0]
        layer = QgsVectorLayer(path, name, "ogr")
        if not layer.isValid():
            QMessageBox.critical(self, "STAT GEOM QC", "Couche invalide :\n%s" % path)
            return
        QgsProject.instance().addMapLayer(layer)
        self.layer_combo.setLayer(layer)
        self.status_label.setText("Couche chargée : %s" % name)

    def _current_layer(self):
        layer = self.layer_combo.currentLayer()
        if layer is None or not isinstance(layer, QgsVectorLayer):
            return None
        return layer

    # ── Analyse ───────────────────────────────────────────────────────────

    def _run_analysis(self):
        if self._analyzing:
            return
        layer = self._current_layer()
        if layer is None:
            QMessageBox.warning(self, "STAT GEOM QC", "Sélectionnez d'abord une couche vectorielle.")
            return

        opts = AnalysisOptions(
            small_polygon_threshold_m2=self.spin_threshold.value(),
            topology_checks=self.chk_topology.isChecked(),
            check_duplicates=self.chk_dup.isChecked(),
            check_buildings=self.chk_buildings.isChecked(),
            check_overlaps=self.chk_overlaps.isChecked(),
        )

        self._analyzing = True
        self._cancel = False
        self.btn_analyze.setEnabled(False)
        self.prog_widget.setVisible(True)
        self.progress.setValue(0)
        self.status_label.setText("Analyse en cours…")
        QApplication.setOverrideCursor(Qt.WaitCursor)

        analyzer = GeomAnalyzer(opts)
        try:
            result = analyzer.analyze(
                layer,
                progress_cb=self._progress,
                is_canceled=lambda: self._cancel,
            )
            self._result = result
            self._display(result)
            self.status_label.setText(
                "Analyse terminée en %.2f s — score %g/100 (%s)."
                % (result.processing_time, result.correctness.score, result.correctness.grade)
            )
        except AnalysisCancelled:
            self.status_label.setText("Analyse annulée.")
        except Exception as exc:  # pragma: no cover
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "STAT GEOM QC", "Échec de l'analyse :\n%s" % exc)
            self.status_label.setText("Échec de l'analyse.")
        finally:
            QApplication.restoreOverrideCursor()
            self._analyzing = False
            self.btn_analyze.setEnabled(True)
            self.prog_widget.setVisible(False)

    def _progress(self, pct, msg=""):
        self.progress.setValue(int(pct))
        if msg:
            self.status_label.setText(msg)
        QApplication.processEvents()

    def _on_cancel(self):
        self._cancel = True

    # ── Affichage des résultats ───────────────────────────────────────────

    def _display(self, result):
        c = result.correctness
        self.results_widget.setVisible(True)
        self.gauge.set_score(c.score, c.color, c.grade)
        self.grade_label.setText(c.grade)
        self.grade_label.setStyleSheet("font-size:20px;font-weight:700;color:%s;" % c.color)
        self.grade_desc.setText(
            "%d alertes sur %s entités analysées."
            % (result.total_issues(), "{:,}".format(result.total_features))
        )

        self._build_metric_cards(result)
        self._build_component_bars(result)
        self._fill_quality_table(result)
        self._fill_attributes_table(result)
        self.report_browser.setHtml(report.build_qt_summary(result))

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            wdg = item.widget()
            if wdg is not None:
                wdg.setParent(None)

    def _build_metric_cards(self, result):
        self._clear_layout(self.cards_layout)
        q = result.quality_report
        cards = [
            ("{:,}".format(result.total_features), "Entités", "ok"),
            ("{:,}".format(q.null_empty_count), "Nulles/Vides", "err" if q.null_empty_count else "muted"),
            ("{:,}".format(q.invalid_count), "Invalides", "err" if q.invalid_count else "muted"),
            ("{:,}".format(q.self_intersection_count), "Auto-inters.", "err" if q.self_intersection_count else "muted"),
            ("{:,}".format(q.overlap_count), "Chevauch.", "err" if q.overlap_count else "muted"),
            ("{:,}".format(q.small_area_count), "≤ %g m²" % result.threshold_m2, "warn" if q.small_area_count else "muted"),
            ("{:,}".format(q.duplicate_count), "Doublons", "warn" if q.duplicate_count else "muted"),
        ]
        if isinstance(result.buildings_agl_over_amsl, int):
            cards.append((
                "{:,}".format(result.buildings_agl_over_amsl),
                "AGL>AMSL",
                "warn" if result.buildings_agl_over_amsl else "muted",
            ))
        for value, label, sev in cards:
            self.cards_layout.addWidget(MetricCard(value, label, sev))

    def _build_component_bars(self, result):
        self._clear_layout(self.bars_layout)
        comps = result.correctness.components
        for key, label in report._COMPONENT_LABELS.items():
            if key not in comps:
                continue
            val = comps[key]
            color = ("#16a34a" if val >= 95 else "#ca8a04" if val >= 80
                     else "#ea580c" if val >= 60 else "#dc2626")
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            name = QLabel(label)
            name.setMinimumWidth(150)
            name.setStyleSheet("font-size:12px;")
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(round(val)))
            bar.setFormat("%g%%" % val)
            bar.setStyleSheet(
                "QProgressBar{border:1px solid #e2e8f0;border-radius:7px;background:#eef2f7;"
                "text-align:center;color:#334155;height:16px;}"
                "QProgressBar::chunk{border-radius:6px;background:%s;}" % color
            )
            rl.addWidget(name)
            rl.addWidget(bar, 1)
            self.bars_layout.addWidget(row)

    def _fill_quality_table(self, result):
        q = result.quality_report
        rows = [
            ("Total entités", "{:,}".format(result.total_features), None),
            ("Géométries valides", "{:,}".format(q.valid_count), "#16a34a"),
            ("Géométries invalides", "{:,}".format(q.invalid_count), "#dc2626" if q.invalid_count else None),
            ("Auto-intersections", "{:,}".format(q.self_intersection_count), "#dc2626" if q.self_intersection_count else None),
            ("Géométries nulles/vides", "{:,}".format(q.null_empty_count), "#dc2626" if q.null_empty_count else None),
            ("Chevauchements (entités)", "{:,}".format(q.overlap_count), "#dc2626" if q.overlap_count else None),
            ("Paires en intersection", "{:,}".format(q.overlap_pairs), "#dc2626" if q.overlap_pairs else None),
            ("Doublons", "{:,}".format(q.duplicate_count), "#d97706" if q.duplicate_count else None),
            ("Polygones ≤ %g m²" % result.threshold_m2, "{:,}".format(q.small_area_count), "#d97706" if q.small_area_count else None),
            ("Bâtiments AGL > AMSL", str(result.buildings_agl_over_amsl), None),
            ("CRS", "%s — %s" % (result.crs_authid, result.crs_description), None),
            ("Durée d'analyse", "%.2f s" % result.processing_time, None),
        ]
        self.quality_table.setRowCount(len(rows))
        for i, (k, v, color) in enumerate(rows):
            self.quality_table.setItem(i, 0, QTableWidgetItem(k))
            item = QTableWidgetItem(v)
            if color:
                from qgis.PyQt.QtGui import QColor
                item.setForeground(QColor(color))
            self.quality_table.setItem(i, 1, item)

        if q.invalid_details:
            html = "<ul style='margin:0'>" + "".join(
                "<li>%s</li>" % d for d in q.invalid_details) + "</ul>"
        else:
            html = "<span style='color:#16a34a'>Aucun détail d'invalidité.</span>"
        self.invalid_browser.setHtml(html)

    def _fill_attributes_table(self, result):
        cols = result.preview_columns
        rows = result.preview_rows
        self.attr_table.setColumnCount(len(cols))
        self.attr_table.setHorizontalHeaderLabels(cols)
        self.attr_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for cval, value in enumerate(row):
                self.attr_table.setItem(r, cval, QTableWidgetItem(value))
        self.attr_table.resizeColumnsToContents()

    # ── Actions QGIS ──────────────────────────────────────────────────────

    def _all_flagged_fids(self):
        fids = set()
        for cat in _ALL_CATEGORIES:
            fids.update(self._result.flagged.get(cat, []))
        return list(fids)

    def _select_features(self):
        if not self._require_result():
            return
        layer = self._matching_layer()
        if layer is None:
            return
        fids = self._all_flagged_fids()
        if not fids:
            QMessageBox.information(self, "STAT GEOM QC", "Aucune entité problématique à sélectionner.")
            return
        layer.selectByIds(fids)
        try:
            self.iface.mapCanvas().zoomToSelected(layer)
        except Exception:  # nosec B110 - zoom best-effort, sans incidence
            pass
        self.status_label.setText("%d entités problématiques sélectionnées." % len(fids))

    def _create_error_layer(self):
        if not self._require_result():
            return
        layer = self._matching_layer()
        if layer is None:
            return

        fid_to_errors = {}
        for cat in _GEOM_CATEGORIES:
            for fid in self._result.flagged.get(cat, []):
                fid_to_errors.setdefault(fid, []).append(_CATEGORY_LABELS[cat])
        if not fid_to_errors:
            QMessageBox.information(
                self, "STAT GEOM QC",
                "Aucune entité à géométrie fautive (les nulles/vides n'ont pas de géométrie)."
            )
            return

        wkb_str = QgsWkbTypes.displayString(layer.wkbType())
        uri = wkb_str
        authid = layer.crs().authid()
        if authid:
            uri += "?crs=%s" % authid
        mem = QgsVectorLayer(uri, "QC erreurs — %s" % layer.name(), "memory")
        pr = mem.dataProvider()
        pr.addAttributes([
            QgsField("src_fid", QVariant.LongLong),
            QgsField("qc_error", QVariant.String),
        ])
        mem.updateFields()

        cap = 50000
        feats = []
        request = QgsFeatureRequest().setFilterFids(list(fid_to_errors.keys()))
        for src_feat in layer.getFeatures(request):
            if len(feats) >= cap:
                break
            if not src_feat.hasGeometry():
                continue
            nf = QgsFeature(mem.fields())
            nf.setGeometry(src_feat.geometry())
            nf.setAttributes([src_feat.id(), ", ".join(fid_to_errors.get(src_feat.id(), []))])
            feats.append(nf)
        pr.addFeatures(feats)
        mem.updateExtents()
        QgsProject.instance().addMapLayer(mem)
        note = " (limité à %d)" % cap if len(feats) >= cap else ""
        self.status_label.setText("Couche d'erreurs créée : %d entités%s." % (len(feats), note))

    def _repair_geometries(self):
        """Réparation sélective (cases à cocher) écrite dans un NOUVEAU fichier.

        La couche d'origine n'est jamais modifiée : l'utilisateur choisit les
        types d'erreurs à corriger, puis un nouveau fichier est créé et chargé.
        """
        if not self._require_result():
            return
        layer = self._matching_layer()
        if layer is None:
            return
        result = self._result

        counts = {
            "invalid": len(result.flagged.get("invalid", [])),
            "self_intersection": len(result.flagged.get("self_intersection", [])),
            "null_empty": len(result.flagged.get("null_empty", [])),
            "duplicate": len(result.flagged.get("duplicate", [])),
            "small": len(result.flagged.get("small", [])),
            "overlap": len(result.flagged.get("overlap", [])),
        }
        if not any(counts.values()):
            QMessageBox.information(
                self, "STAT GEOM QC",
                "Aucune erreur corrigeable détectée (invalides, auto-intersections, "
                "nulles/vides, doublons, petits polygones, chevauchements)."
            )
            return

        ropts = self._ask_repair_options(counts, result.threshold_m2)
        if ropts is None:
            return  # annulé
        if not ropts.any_selected():
            QMessageBox.information(self, "STAT GEOM QC", "Aucune correction sélectionnée.")
            return

        # Fichier de sortie : NOUVEAU fichier, l'original n'est pas touché.
        base = "%s_repare" % (result.layer_name or "couche")
        path, selected = QFileDialog.getSaveFileName(
            self, "Enregistrer la couche réparée (nouveau fichier)",
            base + ".gpkg",
            "GeoPackage (*.gpkg);;Shapefile (*.shp);;GeoJSON (*.geojson)",
        )
        if not path:
            return
        path = self._ensure_extension(path, selected)

        if os.path.abspath(path) == os.path.abspath(layer.source().split("|")[0]):
            QMessageBox.warning(
                self, "STAT GEOM QC",
                "Le fichier de sortie doit être différent du fichier d'origine."
            )
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            mem, stats = GeomAnalyzer.build_repaired_layer(layer, result, ropts)
            self._write_layer_to_file(mem, path)
        except Exception as exc:  # pragma: no cover
            QApplication.restoreOverrideCursor()
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "STAT GEOM QC", "Échec de la réparation :\n%s" % exc)
            self.status_label.setText("Échec de la réparation.")
            return
        QApplication.restoreOverrideCursor()

        # Charger la nouvelle couche dans le projet
        name = os.path.splitext(os.path.basename(path))[0]
        new_layer = QgsVectorLayer(path, name, "ogr")
        if new_layer.isValid():
            QgsProject.instance().addMapLayer(new_layer)

        msg = (
            "Réparation terminée — nouveau fichier créé :\n%s\n\n"
            "• Géométries réparées (valides) : %d\n"
            "• Encore invalides après make valid : %d\n"
            "• Nulles/vides supprimées : %d\n"
            "• Doublons supprimés : %d\n"
            "• Petits polygones supprimés : %d\n"
            "• Chevauchements mineurs rognés : %d\n"
            "• Entités écrites : %d\n"
            % (path, stats.fixed_invalid, stats.still_invalid,
               stats.removed_null_empty, stats.removed_duplicates,
               stats.removed_small, stats.fixed_overlaps, stats.written)
        )

        # Information explicite sur les chevauchements laissés à l'opérateur
        if stats.manual_overlaps:
            fids = stats.manual_overlap_fids
            shown = ", ".join(str(f) for f in fids[:30])
            if len(fids) > 30:
                shown += ", … (+%d)" % (len(fids) - 30)
            msg += (
                "\n⚠ %d chevauchement(s) trop important(s) NON corrigé(s) "
                "(la forme aurait été trop modifiée) — à revoir manuellement.\n"
                "FID source concernés : %s\n"
                "Astuce : « 🎯 Sélectionner les entités » puis filtrez la "
                "catégorie « Chevauchement » sur la couche d'origine."
                % (stats.manual_overlaps, shown)
            )

        msg += (
            "\nLa couche d'origine n'a pas été modifiée. Relancez l'analyse sur "
            "la couche réparée pour actualiser le score."
        )
        QMessageBox.information(self, "STAT GEOM QC", msg)
        self.status_label.setText("Couche réparée créée : %s" % os.path.basename(path))

    def _ask_repair_options(self, counts, threshold):
        """Dialogue de sélection des corrections (cases à cocher).

        Renvoie un RepairOptions, ou None si l'utilisateur annule.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("Réparation géométrique — choix des corrections")
        dlg.setMinimumWidth(440)
        lay = QVBoxLayout(dlg)

        intro = QLabel(
            "Cochez les types d'erreurs à corriger automatiquement.\n"
            "Le résultat sera écrit dans un NOUVEAU fichier ; la couche "
            "d'origine ne sera pas modifiée."
        )
        intro.setWordWrap(True)
        lay.addWidget(intro)

        chk_invalid = QCheckBox(
            "Réparer les géométries invalides — « make valid »  (%d)" % counts["invalid"])
        chk_selfint = QCheckBox(
            "Réparer les auto-intersections — « make valid »  (%d)" % counts["self_intersection"])
        chk_null = QCheckBox(
            "Supprimer les géométries nulles / vides  (%d)" % counts["null_empty"])
        chk_dup = QCheckBox(
            "Supprimer les doublons — conserver la 1ʳᵉ occurrence  (%d)" % counts["duplicate"])
        chk_small = QCheckBox(
            "Supprimer les petits polygones ≤ %g m²  (%d)" % (threshold, counts["small"]))
        chk_overlap = QCheckBox(
            "Corriger les chevauchements MINEURS uniquement  (%d)" % counts["overlap"])

        boxes = (
            (chk_invalid, "invalid"),
            (chk_selfint, "self_intersection"),
            (chk_null, "null_empty"),
            (chk_dup, "duplicate"),
            (chk_small, "small"),
            (chk_overlap, "overlap"),
        )
        for chk, key in boxes:
            enabled = counts[key] > 0
            chk.setEnabled(enabled)
            # Par défaut, seule la réparation des invalides est pré-cochée
            # (elle englobe déjà les auto-intersections).
            chk.setChecked(enabled and key == "invalid")
            lay.addWidget(chk)

        chk_selfint.setToolTip(
            "Les auto-intersections sont un sous-ensemble des géométries "
            "invalides. Cochez cette case pour ne corriger QUE les "
            "auto-intersections sans toucher aux autres invalides."
        )

        # Tolérance de rognage des chevauchements (part de surface max retirée)
        tol_row = QHBoxLayout()
        tol_lbl = QLabel("     ↳ seuil « mineur » — surface rognée max (%)")
        tol_lbl.setStyleSheet("color:#475569;font-size:11px;")
        spin_tol = QDoubleSpinBox()
        spin_tol.setRange(0.1, 50.0)
        spin_tol.setDecimals(1)
        spin_tol.setSingleStep(0.5)
        spin_tol.setValue(5.0)
        spin_tol.setEnabled(counts["overlap"] > 0)
        spin_tol.setToolTip(
            "Un chevauchement n'est corrigé automatiquement que si la surface à "
            "retirer du plus petit polygone est ≤ ce pourcentage de sa surface. "
            "Au-delà, le polygone est laissé intact et signalé pour une "
            "correction manuelle (la forme n'est jamais fortement modifiée)."
        )
        chk_overlap.toggled.connect(
            lambda on: spin_tol.setEnabled(on and counts["overlap"] > 0))
        tol_row.addWidget(tol_lbl)
        tol_row.addWidget(spin_tol)
        tol_row.addStretch()
        lay.addLayout(tol_row)

        note = QLabel(
            "Chevauchements : seul le plus PETIT polygone de chaque paire est "
            "rogné (le plus grand garde sa forme), et uniquement si le rognage "
            "reste mineur. Les cas importants sont laissés à l'opérateur.\n"
            "Les incohérences AGL > AMSL, elles, ne sont pas réparables "
            "automatiquement."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#64748b;font-size:11px;")
        lay.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Réparer…")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)

        if dlg.exec_() != QDialog.Accepted:
            return None
        return RepairOptions(
            fix_invalid=chk_invalid.isChecked(),
            fix_self_intersection=chk_selfint.isChecked(),
            remove_null_empty=chk_null.isChecked(),
            remove_duplicates=chk_dup.isChecked(),
            remove_small=chk_small.isChecked(),
            fix_overlaps=chk_overlap.isChecked(),
            overlap_max_fraction=spin_tol.value() / 100.0,
        )

    @staticmethod
    def _ensure_extension(path, selected_filter):
        """Ajoute l'extension adéquate si l'utilisateur ne l'a pas saisie."""
        ext = os.path.splitext(path)[1].lower()
        if ext in (".gpkg", ".shp", ".geojson", ".json"):
            return path
        if selected_filter and "shp" in selected_filter.lower():
            return path + ".shp"
        if selected_filter and "geojson" in selected_filter.lower():
            return path + ".geojson"
        return path + ".gpkg"

    def _write_layer_to_file(self, mem, path):
        """Écrit la couche mémoire réparée dans `path` (nouveau fichier)."""
        ctx = QgsProject.instance().transformContext()
        ext = os.path.splitext(path)[1].lower()
        driver = {
            ".shp": "ESRI Shapefile",
            ".gpkg": "GPKG",
            ".geojson": "GeoJSON",
            ".json": "GeoJSON",
            ".kml": "KML",
            ".tab": "MapInfo File",
        }.get(ext, "GPKG")

        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = driver
        opts.layerName = os.path.splitext(os.path.basename(path))[0]

        # API récente (QGIS ≥ 3.20) avec repli sur l'ancienne signature.
        try:
            res = QgsVectorFileWriter.writeAsVectorFormatV3(mem, path, ctx, opts)
        except AttributeError:
            res = QgsVectorFileWriter.writeAsVectorFormatV2(mem, path, ctx, opts)

        err_code = res[0]
        err_msg = res[1] if len(res) > 1 else ""
        if err_code != QgsVectorFileWriter.NoError:
            raise RuntimeError(err_msg or ("code d'erreur %s" % err_code))

    # ── Exports ───────────────────────────────────────────────────────────

    def _export(self, kind):
        if not self._require_result():
            return
        base = "STAT_GEOM_QC_%s" % (self._result.layer_name or "rapport")
        filters = {"html": "HTML (*.html)", "csv": "CSV (*.csv)", "json": "JSON (*.json)"}
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter le rapport", base + "." + kind, filters[kind]
        )
        if not path:
            return
        try:
            if kind == "html":
                report.write_html(self._result, path)
            elif kind == "csv":
                report.write_csv(self._result, path)
            else:
                report.write_json(self._result, path)
            self.status_label.setText("Exporté : %s" % path)
        except Exception as exc:
            QMessageBox.critical(self, "STAT GEOM QC", "Échec de l'export :\n%s" % exc)

    def _open_in_browser(self):
        if not self._require_result():
            return
        tmp = os.path.join(tempfile.gettempdir(), "stat_geom_qc_report.html")
        report.write_html(self._result, tmp)
        webbrowser.open("file:///" + tmp.replace("\\", "/"))

    # ── Helpers ───────────────────────────────────────────────────────────

    def _require_result(self):
        if self._result is None:
            QMessageBox.information(self, "STAT GEOM QC", "Lancez d'abord une analyse.")
            return False
        return True

    def _matching_layer(self):
        """La couche sélectionnée doit correspondre au dernier résultat
        (les FID ne sont valables que pour la couche analysée)."""
        layer = self._current_layer()
        if layer is None:
            QMessageBox.warning(self, "STAT GEOM QC", "Aucune couche sélectionnée.")
            return None
        if self._result and layer.source() != self._result.source:
            QMessageBox.warning(
                self, "STAT GEOM QC",
                "La couche sélectionnée ne correspond pas au dernier résultat.\n"
                "Relancez l'analyse sur cette couche."
            )
            return None
        return layer
