# Vue simulation — décor du site (plan réaliste)

Objectif : remplacer le « plan choropleth » (polygones plats + traits gris) par
un **site de festival crédible** — scènes, entrée, allées, stands, tentes —
100 % vectoriel, hors-ligne, sans aucune ressource externe.

Périmètre : **`dashboard/viewer_template.html` uniquement**. Le moteur
(`simulation/replay_sim.py`), le format de `replay.json` et les KPIs ne sont
**pas** touchés. Tout est dérivé de l'en-tête déjà présent (`zones[*].poly`,
`focal`, `gate`, `bottom_exit`, `paths`). Rebuild : `python3
dashboard/festival_map.py`.

---

## 1. Couche statique hors-écran (`renderStatic`)

Le « bâti » du site est dessiné **une seule fois** dans un canvas hors-écran
(`staticCv`), puis recopié à chaque frame (`ctx.drawImage`). Re-rendu seulement
sur **resize / changement de thème / toggle « Allées »**. Le décor n'est donc
plus redessiné 60×/s → visuels riches quasi gratuits.

- `draw()` : `clearRect` → `drawImage(staticCv)` → couches dynamiques.
- Hooks ajoutés : `resize()`, `theme.onclick`, `matchMedia change`, toggle
  `allees` appellent `renderStatic()` avant `draw()`.

## 2. Éléments dessinés

- **Sol** : pelouse + rayures de tonte, extérieur neutre, **clôture
  périmétrique** (rail + poteaux) avec trou en bas au centre pour l'entrée.
- **Allées** : les 10 `paths` deviennent des **chemins de gravier** (liseré
  large + remplissage clair, deux passes) qui fusionnent en réseau.
- **Scènes** (MainStage/SecondStage) : plateau + toit trapèze + rampe de
  projecteurs + écran LED + 2 piles d'enceintes, au bord avant de la fosse
  (MainStage plus grande). Badge « en concert » (♪ + égaliseur) posé sur le
  toit. Géométrie factorisée dans `stageGeom(z)`.
- **FoodCourt** : deux rangées de **stands à auvent rayé**, plaza au centre.
- **Camping** : grille de **tentes A-frame** légèrement désordonnée (jitter
  déterministe par `hash(i)`).
- **Entrée** : corridor clôturé (murs = côtés du sablier), **portique** au col
  (poteaux + banderole), 2 **guichets** dans le parvis, parvis pavé.

## 3. Densité en recouvrement translucide

Les zones ne sont plus remplies en opaque : la teinte de densité devient un
**overlay translucide** dont l'alpha suit l'affluence
(`0.2 + 0.62·d`). Le décor (tentes, stands, scènes) reste visible à faible
affluence ; la chaleur monte et masque quand la zone se remplit. Anneaux de
prévision, contours d'alerte et libellés `%` inchangés.

## 4. Helpers ajoutés

`paint(l,d)` (couleur selon thème), `U(v)` (map→px), `zbbox(z)`, `hash(i)`
(pseudo-aléa stable), `rrect` / `rrectMap` (rectangles arrondis),
`strokePath`, `fenceLine` / `fencePosts`, `stageGeom`, et les fonctions
`draw*` (`drawGround`, `drawRoads`, `drawPerimeter`, `drawStageBuilt`,
`drawFoodStalls`, `drawCamping`, `drawEntranceBuilt`, `drawTent`, `drawStall`,
`drawBooth`, `drawGatePost`).

## Vérifié

Rendu headless (Chrome) en clair / sombre, site vide (matin) et pic
(tête d'affiche) : décor lisible dans les quatre états.

## Reste possible (non fait)

Les allées se terminent aux **centroïdes** des zones → quelques « rayons »
entrent au milieu des zones (visible à vide). Options : rogner chaque allée au
bord de zone, ou router via une plaza centrale partagée.
