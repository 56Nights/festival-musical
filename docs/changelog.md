# Journal des changements (session)

Quatre chantiers, du plus ancien au plus récent. Chaque design détaillé a son
doc dédié ; ici c'est le récapitulatif concis.

## 1. Refonte visuelle de la vue simulation
Doc : néant (intégré). Fichiers : `dashboard/viewer_template.html`,
`simulation/replay_sim.py`, `simulation/geometry.py`.
- **Foule qui se tasse** : ancrage focal par zone + rayon contracté avec la
  densité (`r = R·u^γ(d)`), répulsion légère, flânerie ∝ (1−densité), halo
  additif dans les zones denses (points chauds lumineux).
- **Incidents typés** : pictogrammes dédiés (chute / mouvement de foule / objet),
  anneaux de choc au spawn, flash de zone.
- **Interventions visibles** : faisceau de dépêche équipe→incident, arc de
  prise en charge, anneau de compte à rebours d'abandon, éclat de résolution,
  cordon de sécurité (périmètre).
- **Prévision vs réel** : sparklines par zone (réel plein vs prévision décalée
  +2h pointillée), anneau de pré-chauffe sur la carte, libellé `now → T+2h ↗`,
  ticks d'anticipation sur la timeline, bannière + KPI d'avance.
- **Narration** : chapitres + bandes du programme sur la timeline, bandeau de
  légende auto, badge « en concert », compteur de file au sablier, overlay
  d'accueil, mode démo (`?demo=1`), KPIs animés, journal cliquable.

## 2. Démo A/B — prouver la valeur (avec vs sans gestion prédictive)
Doc : `docs/ab-demo.md`. Fichiers : `config.py`, `integration/pipeline.py`,
`allocation/dynamic_csp.py`, **`simulation/kpis.py` (nouveau)**,
`simulation/replay_sim.py`, `dashboard/viewer_template.html`,
`dashboard/build_dashboard.py`, `narration/llm_narrator.py`, `run_demo.py`.
- `run_control_loop(mode)` : `predictive` (pipeline complet) vs `reactive`
  (`run_reactive_loop`, sans modèle, allocation fixe `static_allocation`).
- `kpis.py` : évaluateur d'impact (mêmes incidents rejoués), Monte-Carlo +
  **ablation 2×2** (prévision × vision) → `kpi_comparison.json` +
  `kpi_ablation.json`.
- Bandeau **AVEC / SANS** dans le lecteur (compteurs jumeaux qui divergent) +
  horodatages jumeaux au journal ; chip flottant en mode démo ; section
  comparaison du dashboard (CDF, CA cumulé, barres, ablation) ; section « apport »
  dans la narration.

## 3. Correctif du modèle de service FoodCourt
Doc : `docs/ab-demo.md` (mis à jour). Fichiers : `config.py`,
`simulation/kpis.py`.
- Capacité **permanente** volontairement insuffisante au pic → une file se
  forme TOUJOURS (réaliste, même « avec »).
- **Équipes volantes** (réserve) : pré-déployées grâce à la prévision (avec) vs
  appelées en réaction, une par une, avec 30 min de retard (sans) → re-mobiliser
  à chaque pic. Résultat : ~200 vs ~2 100 clients perdus (~22 700 € sauvés).

## 4. Modèle d'incidents v2 — cycles de vie & réactions en chaîne
Doc : `docs/incident-model.md`. Fichiers : `config.py`,
`data/generate_data.py`, `allocation/dynamic_csp.py`, `simulation/kpis.py`,
`simulation/replay_sim.py`, `dashboard/viewer_template.html`,
`dashboard/build_dashboard.py`, `narration/llm_narrator.py`.
- Simulateur **minute par minute** ; dispatch **typé** (sécurité pour
  surge/fight, médical pour chutes).
- **Nouveau type `fight`** de bout en bout (données → CSP `SEVERITY=2` → KPI →
  lecteur : pictogramme, cordon).
- **Chaînes** : surge → chutes crush ; fight → blessés ; intensité croissante
  tant que non contenu ; **MCE** si surge non contenu 30 min.
- **Chaîne de survie à deux étages** : premiers gestes (gèlent l'issue) puis
  médic (résout) ; **issue ∈[0,1]** par victime.
- Nouveaux KPIs : premiers gestes, arrivée médic, containment, blessés induits,
  **R_eff**, MCE, issue des victimes. Ancien « escalades » retiré.
- Visuel : **liens parent→enfant** des blessés induits, cordon sur surge+fight,
  bandeau « bilan chaîne » (blessés induits / R / issue).

## 5. Calibration sur données réelles (document de référence)
Doc : `docs/calibration-donnees-reelles.md`. Fichiers : aucun changement de
code encore — recherche sourcée (académique / guides officiels / plans de
licensing publics) qui mappe chaque paramètre de `config.py` à sa valeur
réelle, en préparation des étapes « réalisme » (dimensions, temps de
déplacement, postes de staff, files visibles).
- **Confirmés tels quels** : ALS 8 min (StatPearls), SLA 2 min/client,
  abandon ~8 min, binôme sécurité sur bagarre (SIA), −7 %/min sans RCP (AHA),
  PPR 12-13,5/1000 (Glastonbury 2022, festival autrichien).
- **À corriger** : `MCE_MIN` 30 → 40 (timeline officielle HPD d'Astroworld :
  21h07 premier 911 → 21h47 MCE) ; `TREAT_MIN` (5,12) → (8,20) (revue
  systématique des temps sur place EMS) ; `MEAL_BASKET_EUR` 12 → 14 (atVenu,
  POS de 650+ festivals) ; « 73 % abandonnent > 5 min » intraçable → Omnico
  5 min 54 s / Waitwhile 2024 ; « défib < 5 min » n'est pas dans StatPearls →
  Resuscitation Council UK.
- **Nouvelles bases** : Weidmann 1,34 m/s + formule de Kladek (vitesse ∝
  densité) ; Standon Calling CMP (arène 15 357 m², 3-4 p/m² devant scène,
  egress 70 p/m/min) comme festival de référence ; Green Guide 660 pers/h
  par point d'entrée ; échelle recommandée `METERS_PER_U = 0.5`.

## 6. Réalisme (dimensions réelles, trajets, files) + refonte du panneau incidents
Doc : `docs/calibration-donnees-reelles.md`. Fichiers : `config.py`,
`simulation/geometry.py`, `simulation/mas.py`, `simulation/kpis.py`,
`simulation/replay_sim.py`, `dashboard/viewer_template.html`, `run_demo.py`.
- **Échelle physique réelle** : `METERS_PER_U = 0.5` (site 500×350 m ≈ 17,5 ha,
  MainStage ≈ 14 700 m² ≈ arène réelle de Standon Calling). `WALK_SPEED` dérivé
  de la vitesse libre de Weidmann (1,34 m/s).
- **Durées de trajet dérivées de la géométrie** (fin de la matrice arbitraire) :
  `mas.travel_time` = longueur d'allée × échelle ÷ vitesse d'intervention ;
  temps **intra-zone** non nul (même au sein d'un stage) ; un intervenant est
  **ralenti en foule dense** (diagramme fondamental, dans `kpis.py`).
- **Postes de staff ordonnés** par zone (`STAFF_POSTS`, du plus au moins
  optimal) : les équipes stationnent aux crash-barriers / guichets, pas au hasard.
- **Files de restauration** : les points s'alignent devant les stands FoodCourt
  au pic (file affichée = file mesurée) ; **vitesse de la foule ∝ densité**.
- **Valeurs re-sourcées** : `TREAT_MIN` (8-20 min), `MCE_MIN` 40 (Astroworld
  officiel), `MEAL_BASKET_EUR` 14 (atVenu), `FIRST_AID_TARGET_MIN` 4 (BLS),
  `NECK_EXIT_CAP_STEP` dérivé de 70 pers/m/min (Green Guide).
- **Panneau « surveillance temps réel »** (remplace l'ancien bandeau impact
  confus) : une ligne par incident en cours, chrono live jusqu'à l'arrivée des
  forces sur place, état « aucun incident en cours ».
- **Écran de bilan de fin** (bouton Σ / `?summary=1` / fin de lecture) :
  KPIs avec/sans **expliqués un par un**, chiffre-titre « CA sauvé ».
- Scénario MAS re-calé (taux 0,15, hors saturation) : CSP p95 ~29 min / ~0
  non-couvert vs uniforme ~38 min / dizaines de non-couverts.

## 7. Monitoring comparatif, bilan sourcé, prévision dynamique, balking
Fichiers : `simulation/kpis.py`, `simulation/replay_sim.py`, `config.py`,
`dashboard/viewer_template.html`.
- **Dispatch typé dans la vue** : la SÉCURITÉ *contient* les mouvements de foule /
  bagarres / objets (acte résolutif : pending → cordon en route → sur place →
  contenu) ; le MÉDICAL ne traite plus que les chutes. Les surges apparaissent
  enfin dans le panneau incidents.
- **Timers jumeaux par incident** : deux chronos par ligne — « prédictif » (piloté
  par les frames) et « sans » (jumeau modélisé de l'évaluateur) — l'écart se lit
  incident par incident. Ajout de `contain_min` (avec+sans) et d'une
  `rep_timeline` représentative dans `kpis.py`.
- **Alertes caméra** (lignes 👁 pointillées) et **lignes fantômes** (blessés
  induits « évités par le système », depuis la timeline SANS) dans le panneau.
- **Prévision TimesFM dynamique** : les sparklines se dessinent au fil de la
  lecture, la courbe de prévision projetée **2 h devant** le playhead (anticipation
  visible) — plus de barre-curseur.
- **Bilan de fin refondu** : cartes **dépliables** (définition + calcul + source),
  badge « ✓ mieux » sur la colonne gagnante, renommages (« Médecin en < 8 min »,
  « État de santé des victimes 100 % = indemne », « Catastrophe (MCE) — % des
  jours »), lisibilité Monte-Carlo (« ≈ 4,9/j », « 22 % des jours ») et format
  français (virgule, « min »).
- **Clients perdus = balking sourcé** : à l'arrivée, le client observe la file et
  renonce avec P(W) = 1 − exp(−(W−10)/4) (Erlang-A, Palm 1957 ; GMR 2002) —
  remplace le seuil sec à 8 min ; une file réelle se forme au pic. Résultat
  AVEC/SANS : ~218 vs ~2170 clients perdus (~27 000 € sauvés).
- UX : étiquette « ⚠ surcap. » au-delà de 100 %, touche Échap, accueil mis à jour.

## Résultats de démo (40 tirages, mêmes incidents) — avec / sans
| KPI | avec | sans |
|---|---|---|
| Détection | 3,8 min | 5,5 min |
| Premiers gestes | 2,6 min | 5,1 min |
| Arrivée médecin | 3,1 min (99 % < 8) | 7,8 min (77 %) |
| Blessés induits | 5,0 | 7,6 |
| R_eff (enchaînement) | 0,46 | 0,69 |
| Mass Casualty Events | 0,03 | 0,47 |
| Issue des victimes | 65 % | 35 % |
| Clients perdus FoodCourt | ~200 | ~2 100 (~22 700 € sauvés) |

## Nouveaux artefacts `outputs/`
`control_log_reactive.json`, `kpi_comparison.json`, `kpi_ablation.json`
(en plus de `control_log.json`, `replay.json`, `festival_map.html`,
`dashboard.html`, `situation_report.md`).

## Vérification
Self-checks par module (`kpis.py`, `replay_sim.py`, `geometry.py`,
`generate_data.py`, `dynamic_csp.py`) + rendu headless du lecteur + captures.
**Non relancé** : `run_demo.py` complet (télécharge TimesFM + torch) — le
`control_log.json` prédictif a été patché avec les bagarres pour les tests hors
ligne ; `run_demo.py` le régénère proprement via le vrai pipeline.

## Réglages à connaître (tous dans `config.py`, commentés + sourcés)
`MEAL_JOIN_PEAK`, `FC_PERMANENT_STAFF`, `RESERVE_LOGISTICS`, `RESERVE_*` (service) ;
`SURGE_*`, `FIGHT_*`, `MCE_*`, `FALL_DECAY`, `FALL_CRUSH_DENSITY` (incidents) ;
`CNN_LATENCY_MIN`, `HUMAN_DISCOVERY_MIN`, `RESPONSE_TARGET_MIN`, `MC_RUNS` (A/B).
Paramètres non sourcés marqués « illustratifs » (sensibilité ±50 % ne renverse
pas le classement avec/sans).
