# -*- coding: utf-8 -*-
"""
Génération de rapports STAT GEOM QC : HTML moderne (avec anneau de score de
correctness), CSV et JSON. Aucune dépendance externe.
"""

import csv
import html
import json
import math
from typing import List, Tuple

from .analysis_engine import AnalysisResult


# ═══════════════════════════════════════════════════════════════════════════════
# HTML
# ═══════════════════════════════════════════════════════════════════════════════


def _score_ring_svg(score: float, color: str, size: int = 160) -> str:
    """Anneau de progression SVG représentant le score de correctness."""
    r = size / 2 - 14
    cx = cy = size / 2
    circ = 2 * math.pi * r
    frac = max(0.0, min(1.0, score / 100.0))
    dash = circ * frac
    gap = circ - dash
    return f"""
    <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" aria-label="Score {score}">
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#e5e7eb" stroke-width="14"/>
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="14"
              stroke-linecap="round" stroke-dasharray="{dash:.2f} {gap:.2f}"
              transform="rotate(-90 {cx} {cy})"/>
      <text x="50%" y="47%" text-anchor="middle" font-size="34" font-weight="700"
            fill="{color}" font-family="Segoe UI, sans-serif">{score:g}</text>
      <text x="50%" y="63%" text-anchor="middle" font-size="13" fill="#6b7280"
            font-family="Segoe UI, sans-serif">/ 100</text>
    </svg>
    """


def _badge(value, danger: bool, warn: bool = False) -> str:
    cls = "ok"
    if danger and value:
        cls = "err"
    elif warn and value:
        cls = "warn"
    return '<span class="badge %s">%s</span>' % (cls, html.escape(str(value)))


_COMPONENT_LABELS = {
    "null_empty": "Géométries non nulles/vides",
    "invalid": "Géométries valides",
    "overlap": "Absence de chevauchement",
    "duplicate": "Unicité (doublons)",
    "small": "Surfaces > seuil",
    "agl": "Cohérence AGL/AMSL",
}


def build_html(result: AnalysisResult) -> str:
    """Construit un rapport HTML complet et autonome."""
    c = result.correctness
    q = result.quality_report
    esc = html.escape

    geom_types = ", ".join("%s : %s" % (k, v) for k, v in result.geometry_types.items()) or "—"
    cols = result.attribute_info.get("columns", [])
    cols_preview = ", ".join(cols[:12]) + ("…" if len(cols) > 12 else "")

    # Barres de sous-scores
    comp_rows = []
    for key, label in _COMPONENT_LABELS.items():
        if key not in c.components:
            continue
        val = c.components[key]
        bar_color = "#22c55e" if val >= 95 else "#eab308" if val >= 80 else "#f97316" if val >= 60 else "#ef4444"
        comp_rows.append(f"""
          <div class="comp">
            <div class="comp-head"><span>{esc(label)}</span><span class="comp-val">{val:g}%</span></div>
            <div class="bar"><div class="bar-fill" style="width:{val:g}%;background:{bar_color}"></div></div>
          </div>""")
    comp_html = "\n".join(comp_rows)

    warnings_html = ""
    if result.warnings:
        items = "".join("<li>%s</li>" % esc(w) for w in result.warnings)
        warnings_html = f'<div class="card"><h2>⚠️ Avertissements</h2><ul class="msg warn-list">{items}</ul></div>'

    errors_html = ""
    if result.errors:
        items = "".join("<li>%s</li>" % esc(e) for e in result.errors)
        errors_html = f'<div class="card"><h2>⛔ Erreurs</h2><ul class="msg err-list">{items}</ul></div>'

    invalid_html = ""
    if q.invalid_details:
        items = "".join("<li>%s</li>" % esc(d) for d in q.invalid_details)
        invalid_html = f'<div class="card"><h2>🔎 Détails d\'invalidité</h2><ul class="msg">{items}</ul></div>'

    agl = result.buildings_agl_over_amsl
    agl_display = _badge(agl, danger=True, warn=True) if isinstance(agl, int) else esc(str(agl))

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>STAT GEOM QC — Rapport : {esc(result.layer_name)}</title>
<style>
  :root {{
    --bg:#f1f5f9; --card:#ffffff; --ink:#0f172a; --muted:#64748b; --line:#e2e8f0;
    --accent:#0ea5e9;
  }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif; background:var(--bg);
         color:var(--ink); margin:0; padding:28px; line-height:1.5; }}
  .wrap {{ max-width:960px; margin:0 auto; }}
  header {{ display:flex; align-items:center; gap:14px; margin-bottom:22px; }}
  header .logo {{ width:44px; height:44px; border-radius:12px;
    background:linear-gradient(135deg,#0ea5e9,#6366f1); display:flex; align-items:center;
    justify-content:center; color:#fff; font-size:22px; font-weight:700; }}
  header h1 {{ font-size:20px; margin:0; }}
  header .sub {{ color:var(--muted); font-size:13px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:16px;
    padding:22px; margin-bottom:18px; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
  h2 {{ font-size:15px; margin:0 0 14px; letter-spacing:.02em; text-transform:uppercase;
    color:var(--muted); }}
  .hero {{ display:flex; gap:26px; align-items:center; flex-wrap:wrap; }}
  .hero .ring {{ flex:0 0 auto; }}
  .hero .grade {{ flex:1 1 240px; }}
  .grade .g-label {{ font-size:26px; font-weight:700; color:{c.color}; }}
  .grade .g-desc {{ color:var(--muted); font-size:14px; margin-top:4px; }}
  .comps {{ flex:1 1 340px; min-width:280px; }}
  .comp {{ margin-bottom:11px; }}
  .comp-head {{ display:flex; justify-content:space-between; font-size:13px; margin-bottom:4px; }}
  .comp-val {{ color:var(--muted); font-variant-numeric:tabular-nums; }}
  .bar {{ height:8px; background:#eef2f7; border-radius:99px; overflow:hidden; }}
  .bar-fill {{ height:100%; border-radius:99px; }}
  .metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:12px; }}
  .metric {{ border:1px solid var(--line); border-radius:12px; padding:14px; }}
  .metric .v {{ font-size:22px; font-weight:700; font-variant-numeric:tabular-nums; }}
  .metric .l {{ font-size:12px; color:var(--muted); margin-top:2px; }}
  .metric.err {{ border-color:#fecaca; background:#fef2f2; }} .metric.err .v {{ color:#dc2626; }}
  .metric.warn {{ border-color:#fde68a; background:#fffbeb; }} .metric.warn .v {{ color:#d97706; }}
  .metric.ok .v {{ color:#0ea5e9; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th,td {{ text-align:left; padding:9px 6px; border-bottom:1px solid var(--line); }}
  th {{ color:var(--muted); font-weight:600; width:42%; }}
  .badge {{ display:inline-block; padding:2px 10px; border-radius:99px; font-size:12px;
    font-weight:600; }}
  .badge.ok {{ background:#dcfce7; color:#166534; }}
  .badge.warn {{ background:#fef9c3; color:#854d0e; }}
  .badge.err {{ background:#fee2e2; color:#991b1b; }}
  .msg {{ margin:0; padding-left:20px; font-size:14px; }}
  .msg li {{ margin:3px 0; }}
  .warn-list li {{ color:#854d0e; }} .err-list li {{ color:#991b1b; }}
  footer {{ text-align:center; color:var(--muted); font-size:12px; margin-top:8px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="logo">◈</div>
    <div>
      <h1>STAT GEOM QC — Rapport de contrôle qualité</h1>
      <div class="sub">{esc(result.layer_name)} · {esc(result.timestamp)} · {result.processing_time:.2f}s</div>
    </div>
  </header>

  <div class="card">
    <h2>Score de correctness</h2>
    <div class="hero">
      <div class="ring">{_score_ring_svg(c.score, c.color)}</div>
      <div class="grade">
        <div class="g-label">{esc(c.grade)}</div>
        <div class="g-desc">Qualité globale des données évaluée sur {result.total_features:,} entités.</div>
      </div>
      <div class="comps">{comp_html}</div>
    </div>
  </div>

  <div class="card">
    <h2>Indicateurs</h2>
    <div class="metrics">
      <div class="metric ok"><div class="v">{result.total_features:,}</div><div class="l">Entités</div></div>
      <div class="metric {'err' if q.null_empty_count else 'ok'}"><div class="v">{q.null_empty_count:,}</div><div class="l">Nulles/Vides</div></div>
      <div class="metric {'err' if q.invalid_count else 'ok'}"><div class="v">{q.invalid_count:,}</div><div class="l">Invalides</div></div>
      <div class="metric {'err' if q.overlap_count else 'ok'}"><div class="v">{q.overlap_count:,}</div><div class="l">Chevauchements</div></div>
      <div class="metric {'warn' if q.duplicate_count else 'ok'}"><div class="v">{q.duplicate_count:,}</div><div class="l">Doublons</div></div>
      <div class="metric {'warn' if q.small_area_count else 'ok'}"><div class="v">{q.small_area_count:,}</div><div class="l">≤ {result.threshold_m2:g} m²</div></div>
    </div>
  </div>

  <div class="card">
    <h2>Informations couche</h2>
    <table>
      <tr><th>Couche</th><td>{esc(result.layer_name)}</td></tr>
      <tr><th>Source</th><td>{esc(result.source)}</td></tr>
      <tr><th>Fournisseur</th><td>{esc(result.provider)}</td></tr>
      <tr><th>CRS</th><td>{esc(result.crs_authid)} — {esc(result.crs_description)}</td></tr>
      <tr><th>Types de géométrie</th><td>{esc(geom_types)}</td></tr>
      <tr><th>Colonnes ({len(cols)})</th><td>{esc(cols_preview)}</td></tr>
      <tr><th>Étendue</th><td>X [{result.bounds.get('minx', 0):.4f}, {result.bounds.get('maxx', 0):.4f}] · Y [{result.bounds.get('miny', 0):.4f}, {result.bounds.get('maxy', 0):.4f}]</td></tr>
    </table>
  </div>

  <div class="card">
    <h2>Détail qualité</h2>
    <table>
      <tr><th>Géométries valides</th><td>{_badge(q.valid_count, danger=False)}</td></tr>
      <tr><th>Géométries invalides</th><td>{_badge(q.invalid_count, danger=True)}</td></tr>
      <tr><th>Auto-intersections</th><td>{_badge(q.self_intersection_count, danger=True)}</td></tr>
      <tr><th>Géométries nulles/vides</th><td>{_badge(q.null_empty_count, danger=True)}</td></tr>
      <tr><th>Chevauchements (entités)</th><td>{_badge(q.overlap_count, danger=True)}</td></tr>
      <tr><th>Paires en intersection</th><td>{_badge(q.overlap_pairs, danger=True)}</td></tr>
      <tr><th>Doublons</th><td>{_badge(q.duplicate_count, danger=False, warn=True)}</td></tr>
      <tr><th>Polygones ≤ {result.threshold_m2:g} m²</th><td>{_badge(q.small_area_count, danger=False, warn=True)}</td></tr>
      <tr><th>Bâtiments AGL &gt; AMSL</th><td>{agl_display}</td></tr>
    </table>
  </div>

  {invalid_html}
  {warnings_html}
  {errors_html}

  <footer>Généré par STAT GEOM QC · Adel Bchini</footer>
</div>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# CSV / JSON
# ═══════════════════════════════════════════════════════════════════════════════


def _flat_rows(result: AnalysisResult) -> List[Tuple[str, str]]:
    d = result.to_dict()
    rows: List[Tuple[str, str]] = []
    for k, v in d.items():
        if k in ("attribute_info",):
            continue
        if isinstance(v, (dict, list)):
            rows.append((k, json.dumps(v, ensure_ascii=False)))
        else:
            rows.append((k, str(v)))
    return rows


def build_qt_summary(result: AnalysisResult) -> str:
    """Rapport simplifié rendu par QTextBrowser (HTML4/CSS2 limité de Qt)."""
    c = result.correctness
    q = result.quality_report
    esc = html.escape

    def row(label, value, color=None):
        style = ' style="color:%s;font-weight:bold"' % color if color else ""
        return "<tr><td style='padding:4px 8px;color:#64748b'>%s</td><td%s style='padding:4px 8px'>%s</td></tr>" % (
            esc(label), style, esc(str(value)))

    danger = "#dc2626"
    warn = "#d97706"
    geom_types = ", ".join("%s: %s" % (k, v) for k, v in result.geometry_types.items()) or "—"

    comp_rows = ""
    for key, label in _COMPONENT_LABELS.items():
        if key in c.components:
            v = c.components[key]
            col = "#16a34a" if v >= 95 else "#ca8a04" if v >= 80 else "#ea580c" if v >= 60 else "#dc2626"
            comp_rows += row(label, "%g%%" % v, col)

    warn_html = ""
    if result.warnings:
        warn_html = "<h3 style='color:#854d0e'>Avertissements</h3><ul>" + "".join(
            "<li>%s</li>" % esc(w) for w in result.warnings) + "</ul>"
    err_html = ""
    if result.errors:
        err_html = "<h3 style='color:#991b1b'>Erreurs</h3><ul>" + "".join(
            "<li>%s</li>" % esc(e) for e in result.errors) + "</ul>"

    return f"""
    <div style="font-family:'Segoe UI',sans-serif">
      <h2 style="color:{c.color};margin-bottom:2px">Score : {c.score:g}/100 — {esc(c.grade)}</h2>
      <p style="color:#64748b;margin-top:0">{esc(result.layer_name)} · {result.total_features:,} entités · {esc(result.timestamp)}</p>

      <h3>Sous-scores</h3>
      <table>{comp_rows}</table>

      <h3>Qualité géométrique</h3>
      <table>
        {row("Total entités", "%s" % result.total_features)}
        {row("Valides", q.valid_count, "#16a34a")}
        {row("Invalides", q.invalid_count, danger if q.invalid_count else None)}
        {row("Auto-intersections", q.self_intersection_count, danger if q.self_intersection_count else None)}
        {row("Nulles/Vides", q.null_empty_count, danger if q.null_empty_count else None)}
        {row("Chevauchements (entités)", q.overlap_count, danger if q.overlap_count else None)}
        {row("Paires en intersection", q.overlap_pairs, danger if q.overlap_pairs else None)}
        {row("Doublons", q.duplicate_count, warn if q.duplicate_count else None)}
        {row("Polygones ≤ %g m²" % result.threshold_m2, q.small_area_count, warn if q.small_area_count else None)}
        {row("Bâtiments AGL > AMSL", result.buildings_agl_over_amsl,
             warn if isinstance(result.buildings_agl_over_amsl, int) and result.buildings_agl_over_amsl else None)}
      </table>

      <h3>Couche</h3>
      <table>
        {row("CRS", "%s — %s" % (result.crs_authid, result.crs_description))}
        {row("Types", geom_types)}
        {row("Colonnes", len(result.attribute_info.get("columns", [])))}
        {row("Durée", "%.2f s" % result.processing_time)}
      </table>
      {warn_html}
      {err_html}
    </div>
    """


def write_csv(result: AnalysisResult, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Propriété", "Valeur"])
        for k, v in _flat_rows(result):
            writer.writerow([k, v])


def write_json(result: AnalysisResult, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False, default=str)


def write_html(result: AnalysisResult, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_html(result))
