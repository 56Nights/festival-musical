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
