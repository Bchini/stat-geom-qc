# STAT GEOM QC — Plugin QGIS

Contrôle qualité et statistiques géométriques des couches vectorielles, avec
**score de correctness** et rapport exportable. Portage natif PyQGIS de
l'application desktop *STAT GEOM* (aucune dépendance externe : ni geopandas,
ni matplotlib).

## ✨ Fonctionnalités

- **Analyse de qualité géométrique** directement sur les couches QGIS :
  - géométries **nulles ou vides** (type de problème unifié) ;
  - géométries invalides + auto-intersections (contrôles topologiques) ;
  - **chevauchements / intersections entre polygones** (aire d'intersection > 0, via index spatial ; les simples contacts de frontière et les doublons exacts sont exclus) ;
  - doublons (WKB normalisé) ;
  - petits polygones sous un seuil m² configurable (surface ellipsoïdale, fonctionne aussi en CRS géographique) ;
  - incohérences bâtiments **AGL > AMSL**.
- **Score de correctness (0-100)** pondéré, avec grade (Excellent → Critique),
  jauge circulaire et décomposition par dimension.
- **Interface moderne dockable** : sélection de couche (ou chargement de fichier),
  options, progression annulable, onglets Synthèse / Qualité / Attributs / Rapport.
- **Actions QGIS intégrées** :
  - 🎯 sélectionner les entités problématiques (avec zoom) ;
  - 🧩 créer une couche mémoire des erreurs (avec type d'erreur par entité) ;
  - 🛠 **réparation géométrique sélective** : un dialogue à **cases à cocher**
    laisse choisir quelles erreurs corriger automatiquement (géométries
    invalides → *make valid*, **auto-intersections** → *make valid*, suppression
    des nulles/vides, des doublons, des petits polygones, et **correction
    prudente des chevauchements mineurs**). Le résultat est écrit dans un
    **nouveau fichier** (GeoPackage / Shapefile / GeoJSON) : **la couche
    d'origine n'est jamais modifiée**.
  - 🔗 **chevauchements** : seul le **plus petit** polygone de chaque paire est
    rogné (le plus grand conserve sa forme), et **uniquement si le rognage reste
    mineur** (surface retirée ≤ un seuil % réglable, 5 % par défaut). Les
    chevauchements importants sont **laissés intacts** et leurs **FID** sont
    listés pour une correction manuelle.
- **Exports** : rapport HTML moderne (anneau de score), CSV, JSON.

> ℹ️ **Score de correctness** : un score parfait `100/100` est réservé aux
> couches **sans aucune anomalie**. Dès qu'une erreur subsiste, le score est
> plafonné sous 100.

## 📦 Installation

1. Dans QGIS : **Extensions → Installer/Gérer les extensions → Installer depuis un ZIP**.
2. Sélectionner `stat_geom_qc.zip`.
3. Activer *STAT GEOM QC*.

L'outil apparaît dans le menu **Vecteur → STAT GEOM QC** et dans la barre d'outils.

## 🚀 Utilisation

1. Cliquer sur l'icône pour ouvrir le panneau.
2. Choisir une couche vectorielle (ou *Charger un fichier*).
3. Régler les options (seuil m², topologie, doublons, bâtiments).
4. **Analyser la couche**.
5. Consulter le score, les indicateurs et le rapport ; exporter ou agir sur la couche.

## 🧮 Score de correctness

Le score part de 100 et retranche une pénalité proportionnelle à la part
d'entités concernées, pondérée par gravité :

| Dimension | Poids |
|-----------|-------|
| Nulles/Vides · Invalides | 1.00 |
| Chevauchements | 0.70 |
| Doublons | 0.60 |
| AGL > AMSL | 0.50 |
| Petits polygones | 0.40 |

Grades : Excellent ≥ 95 · Bon ≥ 85 · Correct ≥ 70 · Faible ≥ 50 · Critique < 50.

---
*Adel Bchini — v2.8.1*
