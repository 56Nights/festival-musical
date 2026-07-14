# Récapitulatif des améliorations — réalisme, surveillance, bilan

Record concis de **tous** les changements de cette itération, avec le *pourquoi*
de chacun. Détail chronologique dans `changelog.md` ; sources chiffrées dans
`calibration-donnees-reelles.md`.

## 1. Calibration sur données réelles (fondation)
Toutes les constantes chiffrées sont désormais sourcées (académique / guides
officiels / plans de festivals publics). *Pourquoi : rendre la simulation
défendable devant un jury — chaque nombre a une origine, pas une valeur inventée.*

| Changement | Valeur | Pourquoi / source |
|---|---|---|
| Échelle physique du site | `METERS_PER_U = 0.5` (site 500×350 m ≈ 17,5 ha) | calée sur Standon Calling : notre MainStage ≈ 14 700 m² ≈ arène réelle 15 357 m² |
| Vitesse de marche | 1,34 m/s + diagramme de Weidmann | vitesse libre piétonne de référence (Weidmann 1993) |
| Cible premiers gestes | `FIRST_AID_TARGET_MIN = 4` (BLS) | StatPearls / NIH NBK597369 |
| Durée de prise en charge | `TREAT_MIN = (8, 20)` min | temps EMS sur site (revue *Healthcare* 2022) |
| Seuil catastrophe | `MCE_MIN = 40` (était 30) | chronologie officielle Astroworld (21h07 → 21h47) |
| Panier moyen | `MEAL_BASKET_EUR = 14` (était 12) | données POS atVenu (650+ festivals) |
| Débit d'egress | dérivé de 70 pers/m/min | Green Guide/SGSA déclassé (terrain, alcool) |
| 3 citations fausses corrigées | — | « 73 %/5 min » intraçable ; défib pas dans StatPearls ; MCE « ~30 min » erroné |

## 2. Dimensions & déplacements réalistes
*Pourquoi : la carte doit être la source de vérité (vue et KPIs ne peuvent plus
se contredire) et les déplacements doivent coûter du temps, même au sein d'une zone.*

- **Durées de trajet dérivées de la géométrie** (fin de la matrice arbitraire) :
  longueur d'allée réelle × échelle ÷ vitesse. `mas.TRAVEL` en dérive.
- **Temps intra-zone non nul** : rejoindre un incident dans un même stage prend
  du temps (taille de zone ÷ vitesse).
- **Ralentissement en foule dense** (diagramme fondamental) : un intervenant qui
  traverse une zone saturée est ralenti — c'est ce qui rend le pré-positionnement
  payant au pic.
- **Postes de staff ordonnés** (`STAFF_POSTS`, du plus au moins optimal :
  crash-barrier, guichets…) : les équipes stationnent à des points crédibles.
- **File de restauration** : au pic, les points s'**alignent en file devant les
  stands** (file affichée = file mesurée par l'évaluateur) ; **vitesse de la
  foule ∝ densité**.

## 3. Surveillance temps réel des incidents (panneau de droite)
*Pourquoi : l'ancien bandeau mélangeait live et bilan (illisible) ; il fallait un
suivi par incident clair et comparatif.*

- **Une ligne par incident**, chrono qui court de l'apparition jusqu'à l'arrivée
  des forces **sur place**, puis se fige ; « aucun incident en cours » sinon.
- **Dispatch typé** : la **sécurité contient** mouvements de foule / bagarres /
  objets (acte résolutif) ; le médical ne traite que les chutes. *Pourquoi : les
  surges n'apparaissaient pas avant — ils étaient « résolus » par un médic
  fantôme sans données de timer.*
- **Deux timers par incident** : « prédictif » (notre système) vs « sans »
  (jumeau modélisé). *Pourquoi : lire l'écart incident par incident.*
- **Alertes caméra** (lignes 👁 pointillées) et **lignes fantômes** (blessés
  induits « évités par le système »). *Pourquoi : matérialiser qu'un incident
  peut n'exister que sans gestion prédictive, et lever l'incohérence
  bannière/panneau.*

## 4. Prévision TimesFM dynamique
*Pourquoi : montrer que le modèle ANTICIPE, au lieu d'un graphe statique.*

- La courbe **réelle se dessine au fil de la lecture** (jusqu'au playhead).
- La courbe de **prévision est projetée 2 h devant** le playhead : l'orange monte,
  puis le trait plein le rejoint 2 h plus tard → anticipation visible. Curseur
  vertical supprimé.

## 5. Bilan de fin de journée refondu
*Pourquoi : chaque chiffre doit être compréhensible et sourcé ; supprimer les
ambiguïtés de sens de lecture.*

- **Cartes dépliables** : définition → calcul → **source** (concis).
- **Badge « ✓ mieux »** sur la colonne gagnante (résout le piège « plus haut =
  mieux » vs « plus bas = mieux »).
- **Renommages** : « Médecin en < 8 min » (part sous la cible ALS), « État de
  santé des victimes » (100 % = indemne, avec l'explication du sens), « R
  (enchaînement) » explicité comme un R épidémique.
- **Lisibilité Monte-Carlo** : « ≈ 4,9/j » (blessés induits), « 22 % des jours »
  (catastrophe, au lieu de 0,2). Format français (virgule, « min »).

## 6. Modèle « clients perdus » sourcé (balking)
*Pourquoi : l'ancien seuil sec (« tout le monde part au-delà de 8 min ») était
irréaliste ; la formule proposée `1/e(−t)` diverge.*

- **P(renoncer | attente W) = 1 − exp(−(W − 10)/4)** à l'arrivée au stand (le
  client observe la file). Forme bornée du modèle **Erlang-A / patience
  exponentielle** (Palm 1957 ; Garnett-Mandelbaum-Reiman 2002). Une file **réelle**
  se forme au pic (auto-régulation) au lieu d'une coupure brutale.
- Résultat AVEC/SANS : ~218 vs ~2170 clients perdus (~27 000 € sauvés).

## 7. Divers UX
Étiquette « ⚠ surcap. » au-delà de 100 % de capacité · touche Échap (ferme
bilan/accueil) · overlay d'accueil mis à jour (panneau + bouton Σ) · scénario
MAS recalé hors saturation (CSP p95 ~29 vs ~38 min, ~0 vs dizaines de non-couverts).

## Fichiers touchés
`config.py` · `simulation/{geometry,mas,kpis,replay_sim}.py` · `run_demo.py` ·
`dashboard/{viewer_template.html,build_dashboard.py}` · docs
(`calibration-donnees-reelles.md`, `changelog.md`, `README.md`, `ab-demo.md`,
`incident-model.md`, `vue-simulation.md`).

## Vérification
Auto-vérifications par module toutes vertes (`geometry`, `kpis`, `replay`, `mas`,
`dynamic_csp`) + rendu headless du lecteur contrôlé (panneau, timers jumeaux,
fantômes, sparklines dynamiques, bilan dépliable). Artefacts régénérés
(`kpi_comparison.json`, `replay.json`, `festival_map.html`, `dashboard.html`,
`scenarios.json`). `run_demo.py` complet non relancé (télécharge TimesFM/torch),
mais chaque étape passe son contrôle individuellement.
