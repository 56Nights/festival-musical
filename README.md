# 🎶 Festival Musical Intelligent — SAE S8 (SCIA 2027)

Système intelligent de gestion de festival : prévision d'affluence, détection
d'anomalies, allocation dynamique de ressources et évaluation de scénarios,
intégrés dans une boucle de contrôle unique.

## Démarrage rapide

```bash
uv sync                          # installe les dépendances (torch, ortools, opencv-python-headless…)
uv run python run_demo.py        # ~20 s : données -> boucle -> MAS -> vue simulation -> dashboard -> narration
open outputs/festival_map.html   # ▶ vue simulation animée (plan du site, foule, équipes, incidents)
open outputs/dashboard.html      # dashboard système (courbes, heatmap, KPIs)
```

> Sans `uv` : `pip install -e .` (ou `pip install -r requirements.txt`) puis
> `python run_demo.py`. La vue simulation nécessite `opencv-python-headless`
> (flux optique) — installé automatiquement par `uv sync`.

## Tester / vérifier

Le projet n'a pas de framework de tests : **chaque module embarque son propre
contrôle exécutable** (`python -m` ou exécution directe). Le test d'intégration
de référence reste `run_demo.py` (bout en bout, doit se terminer sans erreur).

```bash
# --- test d'intégration bout en bout (le plus important) ---
uv run python run_demo.py                 # doit afficher les 8 étapes puis « Terminé »

# --- auto-vérifications par module (rapides, ciblées) ---
uv run python simulation/replay_sim.py    # vue simulation : assertions (600 points conservés,
                                          #   incidents tous clôturés, 24 équipes) + génère replay.json
uv run python simulation/geometry.py      # plan du site : calibration géométrie ↔ matrice TRAVEL
uv run python simulation/mas.py           # MAS : compare allocation CSP vs uniforme (Monte-Carlo)
uv run python allocation/dynamic_csp.py   # CSP : situation calme + stress-test masse d'urgences
uv run python vision/optical_flow.py      # flux optique : calme vs bousculade + fusion 3 signaux
uv run python data/generate_data.py       # données : régénère et résume attendance.csv / events.csv

# --- ne régénérer QUE la vue simulation (sans relancer toute la boucle) ---
uv run python dashboard/festival_map.py   # relit replay.json -> outputs/festival_map.html
```

Ce que confirme chaque contrôle de la **vue simulation** :

| Contrôle | Ce qu'il vérifie |
|---|---|
| `replay_sim.py` (auto-vérif) | conservation de la foule (600 points sur 360 images), tout incident réel finit *résolu* ou *non couvert*, effectif = 24 unités (médical 4 · sécurité 12 · logistique 8) |
| `geometry.py` | l'échelle (1 u = 0,5 m, calée sur un festival réel), les aires par zone en m²/pers·m² et les durées de trajet **dérivées de la géométrie** (source de vérité des KPIs) restent dans une plage plausible — la vue et les KPIs partagent la même géométrie |
| `run_demo.py` | la boucle écrit `control_log.json` **avec** `truth_incidents`, puis `replay.json` et `festival_map.html` se génèrent sans erreur |

Inspection manuelle de la vue (aucun serveur requis) : ouvrir
`outputs/festival_map.html` dans un navigateur, cliquer **▶ Lire**. Pour cadrer
un instant précis (utile en soutenance) :
`outputs/festival_map.html?f=255&theme=light&play=1` (pic tête d'affiche).

## Architecture

```
                       ┌─────────────────────────────┐
                       │   Données simulées (CSV)     │
                       │ affluence · zones · météo    │
                       └──────┬──────────────┬───────┘
                              │              │
              ┌───────────────▼──┐    ┌──────▼───────────────┐
              │  TimesFM         │    │  CNN ResNet18        │
              │  zéro-shot,      │    │  (ImageNet gelé)     │
              │  prévision 2h    │    │  densité · chute ·   │
              │  par zone        │    │  objet suspect (POC) │
              └───────┬──────────┘    └──────┬───────────────┘
                      │ pic prévu            │ alertes
                      └──────┬───────────────┘
                             ▼
              ┌──────────────────────────────┐
              │  CSP DYNAMIQUE (CP-SAT)      │   déclencheurs :
              │  ré-allocation périodique    │   · périodique (30 min)
              │  + événementielle            │   · alerte CNN
              │  contraintes dures + souples │   · pic prévu Transformer
              └──────┬───────────────────────┘
                     │ plan d'allocation
                     ▼
              ┌──────────────────────────────┐
              │  SIMULATION MULTI-AGENTS     │
              │  (SimPy, Monte-Carlo)        │
              │  évalue les scénarios :      │
              │  temps de réponse, couverture│
              └──────┬───────────────────────┘
                     ▼
              ┌──────────────────────────────┐
              │  NARRATION LLM               │   Gemini / Groq / Ollama
              │  rapport de situation FR     │   ou gabarit hors-ligne
              └──────┬───────────────────────┘
                     ▼
              ┌──────────────────────────────┐
              │  DASHBOARD (Plotly HTML)     │
              └──────┬───────────────────────┘
                     ▼
              ┌──────────────────────────────┐
              │  VUE SIMULATION (Canvas HTML)│   jumeau numérique animé :
              │  plan du site · foule · équipes│  rejoue spatialement la boucle
              │  · incidents · scrub temporel │  (attendance + events + log)
              └──────────────────────────────┘
```

## Couche LLM (narration)

Le LLM intervient **uniquement en sortie du pipeline** : il convertit les
alertes CNN, les décisions du CSP et les KPIs du MAS en rapport de situation
en français pour un opérateur non technique (`narration/llm_narrator.py`).

- Fournisseur auto-détecté par variable d'environnement :
  `GEMINI_API_KEY` (tier gratuit), `GROQ_API_KEY` (tier gratuit) ou
  `OLLAMA=1` (modèle local).
- **Sans clé API, un gabarit déterministe prend le relais** : la démo ne
  dépend jamais du réseau ; le LLM améliore la rédaction mais n'est pas un
  point de défaillance.
- Justification pour le jury : le LLM n'est PAS utilisé pour la prévision,
  la vision ou l'optimisation (mauvais outil pour ces tâches) ; il est
  utilisé là où il excelle — la génération de texte contraint par des
  faits structurés, sans invention (température basse, prompt strict).

```bash
export GEMINI_API_KEY=...        # optionnel — repli gabarit sinon
python narration/llm_narrator.py # sortie : outputs/situation_report.md
```

## Structure du projet

| Dossier | Contenu | Problématique du sujet |
|---|---|---|
| `data/` | Modèle de population jour complet (arrivées, file, egress, campeurs) → `attendance.csv` · `flow.csv` · `events.csv` | Environnement simulé |
| `forecasting/` | TimesFM zéro-shot (repli saisonnier-naïf) | 📈 Prévision de l'affluence |
| `vision/` | ResNet18 pré-entraîné gelé + 3 têtes | ⚠️ Détection de situations anormales |
| `allocation/` | CSP dynamique OR-Tools CP-SAT | 🔧 Allocation des ressources |
| `simulation/` | Simulation multi-agents SimPy + Monte-Carlo | 🧪 Évaluation de scénarios |
| `integration/` | Boucle de contrôle reliant les 4 modules | Cohérence du système |
| `narration/` | Rapport de situation en langage naturel (LLM) | Sortie actionnable pour un opérateur |
| `dashboard/` | Dashboard HTML Plotly + **vue simulation Canvas** | Démo soutenance |

## Modèle de population (Compétences 2 & 3)

Les données d'affluence ne sont plus des courbes en cloche indépendantes par
zone : `data/generate_data.py` simule une **journée complète** (10h → minuit,
56 pas) avec une population **conservée** (Σ affluence des zones = population
sur site), d'après des observations réelles de festivals (cf. sources) :

| Ingrédient réel | Modélisation |
|---|---|
| Types de public (étude Bluetooth ~130 000 festivaliers) | 4 types : campeurs (présents jour+nuit), lève-tôt, gros pic d'après-midi, public tête-d'affiche |
| ~50 % des visiteurs arrivent 16h-18h ; ruée pré-headliner | **demande** d'arrivée = processus de Poisson non-homogène par type (log-normale planner mode ~15h20 + normale ~90 min avant la tête d'affiche). Le **goulot d'admission** étale les admissions effectives (la file absorbe le pic 16h-18h) : ~63 % du public arrive l'après-midi, pic de population ~18h |
| File d'attente aux portes en fin d'après-midi | **goulot d'admission** (capacité/pas) → une file se forme quand le flux la dépasse |
| Egress compressé après le concert (choix de départ individuel) | départs quasi nuls avant 20h, puis egress **borné par la capacité de sortie** (~45 min pour vider l'essentiel) |
| « Les gens campent autour d'une scène » (faible mobilité) | choix de zone par **softmax du programme des concerts** avec forte **inertie** (seule une fraction re-décide par pas) → migrations en vagues, pas de téléportation |
| Évitement des zones saturées | pénalité d'attractivité au-delà de 85 % de capacité → débordement réaliste |

Résultat : le site **démarre avec les campeurs déjà présents** (~3 600 personnes
à l'ouverture, qui dorment sur place), se remplit progressivement, sature à la
tête d'affiche, puis se vide ; **seuls les campeurs restent la nuit**. Le contrôle
`python data/generate_data.py` imprime et vérifie ces propriétés (conservation,
pic, file, T90 d'egress, population résiduelle).

## Vue simulation (jumeau numérique animé)

`outputs/festival_map.html` — un plan du site vu de dessus qui **rejoue
spatialement** la journée complète du dernier jour (56 pas → 840 images d'une
minute, horloge 10h → minuit) :

- population **dynamique** : les points **entrent par la porte** le matin,
  saturent à la tête d'affiche, puis **sortent par la porte** le soir (colonne
  d'egress) — 1 point ≙ K personnes ; compteur « sur site » avec flux ▲/▼ ;
- **Entrée en sablier** : le col (la porte) est un goulot d'étranglement — la
  foule s'entasse visiblement dans le bulbe *extérieur* à l'ouverture / la ruée
  pré-headliner (tout le monde entre) et dans le bulbe *intérieur* à la
  fermeture (tout le monde sort en même temps → Entrée saturée, rouge) ;
- zones colorées par densité (alerte pulsée au-delà du seuil), migrations en
  vagues au fil du programme (bascule vers MainStage pour la tête d'affiche,
  retour des campeurs au Camping la nuit) ;
- équipes (✚ médical, ▲ sécurité, ■ logistique) postées à des **emplacements
  par défaut ordonnés du plus au moins optimal** par zone (crash-barrier devant
  scène, guichets à l'entrée…) et qui **se déplacent physiquement** à chaque
  ré-allocation du CSP ;
- **files de restauration** : au pic déjeuner/dîner, les festivaliers
  s'**alignent en file devant les stands** du FoodCourt (la file affichée = la
  file mesurée par l'évaluateur) ; la foule **ralentit dans les zones denses**
  (diagramme fondamental piéton) ;
- incidents réels répartis sur la journée → mobilisent une équipe (trajet →
  prise en charge → ✓ résolu, ou ✗ non couvert après 30 min), distinction
  **détecté / manqué** par le CNN ;
- **panneau de surveillance temps réel** : une ligne par incident en cours, un
  chrono qui court de l'apparition jusqu'à l'arrivée des forces sur place puis se
  fige, état « aucun incident en cours » sinon ;
- **écran de bilan en fin de journée** (bouton Σ ou `?summary=1`) : chaque KPI
  avec / sans gestion prédictive, **expliqué en une phrase** (clients perdus,
  blessés induits, R, issue des victimes…) ;
- lecture / pause / vitesse (×1–×8) / défilement, marqueurs de ré-allocation
  sur la timeline, journal d'événements et compteurs de KPI synchronisés.

**Choix de conception (Compétence 3).** Ce n'est **pas** un second simulateur :
c'est un jumeau numérique piloté par les artefacts déjà produits
(`attendance.csv`, `flow.csv`, `events.csv`, `control_log.json`). Une seule
source de vérité → ce qui est affiché **est** ce que le système a décidé. La
logique de réponse aux incidents et les durées de trajet reprennent fidèlement
le MAS (`simulation/mas.py`), donc la vue ne peut pas contredire les KPIs.

```bash
python data/generate_data.py      # modèle de population + contrôles de cohérence
python simulation/geometry.py     # calibration géométrie ↔ matrice TRAVEL
python simulation/replay_sim.py   # auto-vérification + génère outputs/replay.json
python dashboard/festival_map.py  # génère outputs/festival_map.html (autonome)
```

Astuce démo : `festival_map.html?f=665&theme=light&play=1` ouvre à un instant
précis (ici le pic tête d'affiche ~21h), dans un thème donné, en lecture auto.
Repères : `f=30` (matin, site vide), `f=610` (ruée + file), `f=785` (egress).

**Sources (comportement réel) :** [étude Bluetooth ~130 000 festivaliers
(arXiv:1306.3133)](https://arxiv.org/abs/1306.3133) ·
[FHWA — Managing Travel for Planned Special Events](https://ops.fhwa.dot.gov/publications/fhwaop04010/handbook.pdf)
· pratiques ingress/egress (Ticket Fairy).

## Résultats de la démo

- **Prévision** : TimesFM zéro-shot (télécharge ~200 Mo au premier lancement) ;
  hors-ligne, repli saisonnier-naïf documenté
- **CNN** : chute ≈ 99 % · objet ≈ 88–99 % · densité MAE ≈ 0,10 — ce sont des
  **exactitudes sur un split synthétique in-distribution** (prévalence ~30 %),
  PAS la précision en exploitation. En rejouant la journée entière, la prévalence
  réelle des chutes est quasi nulle, donc même une bonne spécificité produit
  beaucoup de faux positifs : ~112 alertes caméra pour 15 incidents réels (7:1).
  Le pipeline **filtre** désormais ces faux positifs (gate de plausibilité par
  densité) et **rapporte précision/rappel**, pas seulement l'exactitude (cf.
  `run_demo.py` et §Limites)
- **Flux optique** : la métrique de cohérence (calculée sur les seuls pixels au
  mouvement significatif) **passe désormais son auto-démo** — situation calme non
  signalée, bousculade détectée (`python vision/optical_flow.py`). Le flux ajoute
  un signal temporel corroborant aux alertes de bousculade (fusion 2/3)
- **Boucle intégrée** : alertes CNN filtrées (gate de plausibilité + veilles
  densité séparées) → précision/rappel rapportés honnêtement, ratio alertes:
  incidents ramené de ~7:1 à ~2,5:1 ; ré-allocations CSP stables (hystérésis)
- **MAS** : au pic (incidents concentrés sur MainStage), l'allocation CSP tient
  un p95 de ~29 min et ~0 incident non couvert, contre ~38 min et des dizaines
  de non-couverts pour une allocation uniforme naïve (20 runs Monte-Carlo)
- **Impact avec / sans gestion prédictive** (évaluateur `kpis.py`, mêmes
  incidents) : détection ~3,5 vs ~5,8 min, arrivée médic ~3,3 vs ~7,0 min
  (**93 % vs 62 %** sous la cible ALS de 8 min), issue des victimes 68 % vs 43 %,
  ~26 000 € de ventes FoodCourt sauvées — bilan détaillé et expliqué à la fin de
  la vue simulation

## Justification des choix (Compétence 3 — Concevoir)

| Problème | Méthode | Pourquoi |
|---|---|---|
| Prévision d'affluence | TimesFM (zéro-shot) | Modèle de fondation pré-entraîné sur ~100 Mds de points : plus robuste qu'un entraînement from scratch sur données simulées limitées ; aucun entraînement local, simple forward CPU |
| Détection d'anomalies | ResNet18 pré-entraîné + 3 têtes | Transfert d'apprentissage : features ImageNet réutilisées, backbone gelé, seules les têtes sont entraînées (features pré-calculées → quelques secondes sur CPU) |
| Allocation | CSP (CP-SAT) | Ressources discrètes + contraintes dures (minimums de sécurité) ; contraintes souples avec pénalité de réaffectation pour la stabilité opérationnelle |
| Évaluation de scénarios | Multi-agents + Monte-Carlo | Comportements émergents non capturables analytiquement ; permet de stress-tester les allocations avant déploiement |

## Entraînement : pourquoi si peu ?

Aucun modèle lourd n'est entraîné localement :
- **TimesFM** est utilisé en zéro-shot — pas d'entraînement du tout.
- **ResNet18** est pré-entraîné ImageNet et **gelé** ; seules les 3 têtes
  (quelques milliers de paramètres) sont entraînées, sur des features
  pré-calculées — quelques secondes sur CPU.
- Les poids des têtes (`outputs/vision_cnn.pt`) sont réutilisés d'un
  lancement à l'autre ; supprimez le fichier pour ré-entraîner.
- Hors-ligne (checkpoints non téléchargeables), chaque module a un repli
  documenté : baseline saisonnière pour la prévision, entraînement bout en
  bout du petit ResNet pour la vision.

## Limites assumées (à reprendre dans le rapport — Compétence 5)

- La tête « objet suspect » est un **proof of concept sur données synthétiques** :
  la détection réelle d'objets fins (seringue) en foule exige des caméras
  haute résolution positionnées sur des points de passage, un dataset dédié,
  et pose des questions RGPD à traiter explicitement.
- Les images sont des vues de dessus **simulées** (conformément au sujet) ;
  le pipeline (données → entraînement → inférence → alerte → ré-allocation)
  est en revanche complet et fonctionnel de bout en bout.
- Les durées de trajet ne sont plus une matrice arbitraire : elles sont
  **dérivées de la géométrie du site** (longueur d'allée réelle × échelle
  0,5 m/u ÷ vitesse d'intervention 1,5 m/s), l'échelle étant calée sur le plan
  de gestion de foule public d'un festival réel comparable (Standon Calling —
  arène main stage ~15 000 m²). Un intervenant traversant une foule dense est
  ralenti selon le diagramme fondamental piéton de Weidmann. Tous les paramètres
  chiffrés (temps de réponse cibles, débits, panier moyen, vitesses) sont
  sourcés dans `docs/calibration-donnees-reelles.md`.
- La vue simulation échantillonne la foule (1 point ≙ K personnes, ≤ 800
  points) et **interpole** les positions entre deux relevés de 15 min : les
  points ne sont pas des individus suivis mais un rendu représentatif du flux
  agrégé. La géométrie du plan est désormais la **source de vérité** des durées
  (la matrice `TRAVEL` du MAS en est dérivée) — vue et KPIs partagent la même
  carte et ne peuvent donc pas se contredire.
- Le modèle de population est **agrégé par type** (comptes par pas), pas
  micro-agent individuel : il reproduit les courbes réelles (arrivées, file,
  egress, campeurs) sans prétendre suivre chaque festivalier.
- **Dépassements de capacité de zone (assumés).** Certaines zones dépassent
  transitoirement 100 % de leur capacité nominale au pic (SecondStage ~114 %,
  FoodCourt ~114 %, Entrance ~200 % — transit/file par conception). L'évitement
  des zones saturées (`CROWD_AVERSION`) est une pénalité **souple** : elle
  modère mais n'interdit pas la suroccupation, car le public s'entasse
  réellement devant une scène populaire (surdensité tête d'affiche, cf.
  littérature crowd-crush). La vue simulation **encode explicitement** ces
  dépassements (hachures + anneau ambré + libellé « ⚠ »), au lieu de les masquer
  en saturant la couleur à 100 %.
- **Précision du CNN en exploitation (limite majeure et assumée).** Sur la
  journée rejouée, le détecteur brut émet ~112 alertes pour 15 incidents réels
  (ratio 7:1) — c'est la conséquence normale d'un classifieur imparfait face à
  une prévalence quasi nulle, pas une erreur de mesure. Deux garde-fous sont
  désormais en place : (1) un **gate de plausibilité** supprime les alertes
  physiquement improbables (« personne au sol » dans une zone à <15 % de densité),
  (2) le pipeline **corrobore** les alertes (1 signal = « à vérifier », ≥2 signaux
  = « confirmé ») et **publie précision/rappel**. Le « 99 % » du CNN reste une
  exactitude in-distribution ; la précision opérationnelle, elle, est affichée
  honnêtement plutôt que masquée dans le flot d'alertes.

## Correspondance avec les 6 compétences

| # | Compétence | Où c'est démontré |
|---|---|---|
| 1 | ⚙️ Produire | 4 modules fonctionnels + boucle intégrée + dashboard (`run_demo.py`) |
| 2 | 🗃️ Gérer | Pipeline de données automatisé : génération → CSV structurés → features → journaux JSON |
| 3 | 🧩 Concevoir | Choix justifiés module par module (tableau ci-dessus), architecture cohérente |
| 4 | 🤝 Agir | Répartition des modules par binôme, revues croisées de code (voir ci-dessous) |
| 5 | 📋 Formaliser | README, limites explicitées, dashboard de démonstration, structure de rapport fournie |
| 6 | 🧭 Piloter | Découpage en modules indépendants + sprints d'intégration ; suivi Git recommandé |

## Répartition suggérée (groupe de 6)

| Binôme | Modules | Livrables |
|---|---|---|
| A | `data/` + `forecasting/` | Données, Transformer, métriques de prévision |
| B | `vision/` + `allocation/` | CNN, CSP dynamique, tests de contraintes |
| C | `simulation/` + `integration/` + `dashboard/` | MAS, boucle de contrôle, dashboard, rapport |

Chaque binôme relit le code d'un autre binôme (revue croisée = preuve
tangible pour la Compétence 4). Sync de 15 min tous les 2-3 jours, aligné sur
la consultation de la grille demandée par le sujet.

## Structure de rapport suggérée

1. Contexte et problématiques (reprendre les 4 problématiques du sujet)
2. Architecture générale (schéma ci-dessus)
3. Données simulées : hypothèses, génération, schéma
4. Module par module : méthode, justification, résultats, limites
5. Intégration : la boucle de contrôle, déclencheurs, exemple d'exécution
6. Évaluation de scénarios : protocole Monte-Carlo, KPIs, comparaison
7. Limites et perspectives (RGPD, données réelles, passage à l'échelle)
8. Organisation du groupe (Git, répartition, jalons)

## Dépendances

`torch` · `ortools` · `simpy` · `plotly` · `pandas` · `numpy` · `scikit-learn`
· `opencv-python-headless` (flux optique)

La vue simulation elle-même n'ajoute **aucune** dépendance : le lecteur HTML est
autonome (JavaScript vanilla + Canvas, JSON en ligne, aucun CDN).
