# Vue simulation — choix d'implémentation

Résumé des décisions techniques de la « vue simulation » (plan animé du site) et
du modèle de population qui l'alimente. Objectif : comprendre le *pourquoi*.

## 1. Principe : jumeau numérique, pas un second simulateur
La vue **rejoue** ce que la boucle de contrôle a déjà décidé, à partir des
artefacts existants (`attendance.csv`, `flow.csv`, `events.csv`,
`control_log.json`). Une seule source de vérité → l'écran ne peut pas
contredire les KPIs. Depuis la calibration réelle, c'est désormais la
**géométrie du site qui est autoritative** pour les durées : `mas.TRAVEL` en
dérive (longueur d'allée × échelle 0,5 m/u ÷ vitesse d'intervention), si bien
que la vue et les KPIs partagent la même carte (calibration vérifiée par
`geometry.py` : aires m²/pers·m², durées dans une plage plausible).
cf. `docs/calibration-donnees-reelles.md`.

## 2. Rendu : frames pré-calculées + lecteur HTML autonome
`replay_sim.py` calcule l'état du monde image par image → `replay.json` ;
`festival_map.py` l'injecte dans un gabarit HTML (Canvas 2D, JS vanilla, JSON
en ligne, **aucun CDN/serveur**). Raisons : cohérent avec le principe
« tout est un fichier dans `outputs/` », hors-ligne pour la soutenance,
partageable. Alternatives écartées : Plotly (trop lent >100 frames), pygame/
matplotlib (pas partageable HTML), serveur websocket (fragile en démo).

## 3. Modèle de population (jour complet, `data/generate_data.py`)
Le site part **vide** à 10h, se remplit, sature à la tête d'affiche, se vide ;
seuls les campeurs restent la nuit. Inspiré d'études réelles (voir README) :
- **4 types de visiteurs** (campeur / lève-tôt / planificateur / public
  tête-d'affiche) — mix = principal levier de réglage.
- **Arrivées = Poisson non-homogène** par type (log-normale d'après-midi +
  ruée ~90 min avant la tête d'affiche).
- **Population conservée** : Σ affluence des zones = population sur site.
- **Goulot d'entrée** (capacité d'admission) → une file se forme quand le flux
  la dépasse ; **egress** compressé après le concert, borné par la capacité de
  sortie.
- **Choix de zone = softmax du programme des concerts + forte inertie** (peu de
  gens re-décident par pas → migrations en vagues) + **pénalité d'évitement**
  au-delà de 85 % de capacité (débordement réaliste, empêche la sur-occupation).
- Contrôles de cohérence imprimés/asserts par `generate_data.py`.

Fenêtre rejouée élargie au **dernier jour complet** (56 pas, 840 frames, horloge
10h→minuit) ; l'historique des 2 jours précédents sert à la prévision TimesFM.

## 4. Foule dynamique (points)
- **1 point ≙ K personnes** (K = pic / `MAX_DOTS`) — la foule est un
  échantillon, pas des individus suivis.
- **Points dynamiques** : ils entrent par la porte, migrent, sortent par la
  porte. Chaque point a un **id stable** → le lecteur interpole les positions
  d'une frame à l'autre malgré une liste qui change (sinon scintillement).
- **Dégradé de couleur** pendant un trajet : le point porte sa zone d'ORIGINE et
  sa destination ; la teinte est interpolée le long du trajet (avant : bascule
  instantanée au départ).
- Migrations inter-zones = directes (ne passent pas par la porte) ; arrivées /
  départs = par le col.

## 5. Entrée = sablier à écoulement granulaire (goulot)
L'Entrée est un **sablier** (col étroit entre deux bulbes). Les points en
attente suivent une **physique de balles** (`_settle_funnel`) :
attraction vers le col + répulsion mutuelle (ils s'entassent sans se chevaucher)
+ confinement par les parois de l'entonnoir. Le point le **plus proche du col**
le franchit en premier. Conséquence recherchée :
- faible affluence → flux libre (les points traversent aussitôt) ;
- forte affluence → bouchon qui grossit puis s'écoule, comme un sablier.
La file d'entrée est alimentée au rythme des **arrivées** et vidée au rythme des
**admissions** (⇒ taille ≈ file réelle, se vide garantie). La file de sortie se
forme à l'egress (débit du col < pointe des départs).

## 6. Auto-vérifications (au lieu de tests unitaires)
Chaque module a un `__main__` exécutable : `generate_data.py` (conservation,
pic, file, egress, campeurs), `geometry.py` (calibration ↔ TRAVEL),
`replay_sim.py` (bornes de points, conservation ≈ onsite, progression
remplissage→vidage, incidents tous clôturés). Test d'intégration = `run_demo.py`
de bout en bout.

## 7. Compromis assumés
- `festival_map.html` ≈ **13 Mo** (840 frames × ~800 points × dégradé de
  couleur). Ouvre instantanément en local ; réduire `MAX_DOTS` si besoin.
- Conservation foule ≈ 15 % pendant les pics : les points **retardent**
  volontairement sur l'affluence quand ils bouchonnent au col — c'est l'effet
  goulot, pas un bug.
- File de sortie encore ~60 points à minuit : l'egress déborde la fin de la
  fenêtre (réaliste — le site se vide encore à la fermeture).
- Journée entière rejouée ⇒ le CNN produit plus d'alertes (dont des faux
  positifs à basse densité) ; le CSP les absorbe sans devenir infaisable.

## 8. Principaux réglages (config.py)
`VISITOR_MIX`, `PEAK_POPULATION`, `DAY_TURNOVER`, `GATE_CAP_STEP`,
`NECK_EXIT_CAP_STEP`, `CHOICE_TEMP`, `MOBILITY`, `CROWD_AVERSION`, `SCHEDULE`,
`MAX_DOTS`, `WALK_SPEED` ; physique du col : `FUNNEL_ATTRACT`, `FUNNEL_REPULSE`,
`NECK_HALF` (geometry).

> Note d'intégration : `Camping` a une capacité relevée (grand terrain) et
> `Entrance` une capacité réduite (col étroit qui sature à l'entrée et à
> l'egress) — à signaler si le réglage du CSP suppose les anciennes valeurs.
