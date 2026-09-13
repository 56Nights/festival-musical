# Festival Musical Intelligent

Système de gestion de festival en temps réel : prévision d'affluence,
détection d'anomalies, allocation dynamique de ressources et évaluation de
scénarios, intégrés dans une boucle de contrôle unique.

## Démarrage rapide

```bash
uv sync                          # installe les dépendances (torch, ortools, opencv-python-headless…)
uv run python run_demo.py        # ~20 s : données -> boucle -> MAS -> vue simulation -> dashboard -> narration
open outputs/festival_map.html   # vue simulation animée (plan du site, foule, équipes, incidents)
open outputs/dashboard.html      # dashboard système (courbes, heatmap, KPIs)
```

Sans `uv` : `pip install -e .` (ou `pip install -r requirements.txt`) puis
`python run_demo.py`. La vue simulation nécessite `opencv-python-headless`
(flux optique), installé automatiquement par `uv sync`.

## Tests

Le projet n'utilise pas de framework de tests dédié : chaque module embarque
son propre contrôle exécutable (`python -m` ou exécution directe). Le test
d'intégration de référence est `run_demo.py`, qui doit se terminer sans
erreur de bout en bout.

```bash
# test d'intégration bout en bout
uv run python run_demo.py                 # doit afficher les 8 étapes puis « Terminé »

# vérifications par module
uv run python simulation/replay_sim.py    # vue simulation : conservation de la foule (600 points),
                                           #   incidents tous clôturés, 24 équipes ; génère replay.json
uv run python simulation/geometry.py      # plan du site : calibration géométrie ↔ matrice TRAVEL
uv run python simulation/mas.py           # MAS : compare allocation CSP vs uniforme (Monte-Carlo)
uv run python allocation/dynamic_csp.py   # CSP : situation calme + stress-test masse d'urgences
uv run python vision/optical_flow.py      # flux optique : calme vs bousculade + fusion 3 signaux
uv run python data/generate_data.py       # données : régénère et résume attendance.csv / events.csv

# régénérer uniquement la vue simulation
uv run python dashboard/festival_map.py   # relit replay.json -> outputs/festival_map.html
```

Ce que vérifie chaque contrôle lié à la vue simulation :

| Contrôle | Vérification |
|---|---|
| `replay_sim.py` | conservation de la foule (600 points sur 360 images) ; tout incident réel finit *résolu* ou *non couvert* ; effectif de 24 unités (médical 4 · sécurité 12 · logistique 8) |
| `geometry.py` | l'échelle (1 u = 0,5 m, calée sur un festival réel), les aires par zone et les durées de trajet dérivées de la géométrie restent dans une plage plausible — la vue et les KPIs partagent la même géométrie |
| `run_demo.py` | la boucle écrit `control_log.json` avec `truth_incidents`, puis `replay.json` et `festival_map.html` se génèrent sans erreur |

Inspection manuelle : ouvrir `outputs/festival_map.html` dans un navigateur et
cliquer sur ▶. Pour ouvrir sur un instant précis :
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

Le LLM intervient uniquement en sortie du pipeline : il convertit les alertes
CNN, les décisions du CSP et les KPIs du MAS en rapport de situation en
français pour un opérateur non technique (`narration/llm_narrator.py`).

- Fournisseur auto-détecté par variable d'environnement : `GEMINI_API_KEY`
  (tier gratuit), `GROQ_API_KEY` (tier gratuit) ou `OLLAMA=1` (modèle local).
- Sans clé API, un gabarit déterministe prend le relais : la démo ne dépend
  jamais du réseau ; le LLM améliore la rédaction mais n'est pas un point de
  défaillance.
- Le LLM n'est pas utilisé pour la prévision, la vision ou l'optimisation —
  ce sont de mauvais usages pour ce type de modèle. Il est utilisé là où il
  est pertinent : générer du texte contraint par des faits structurés, sans
  invention (température basse, prompt strict).

```bash
export GEMINI_API_KEY=...        # optionnel — repli gabarit sinon
python narration/llm_narrator.py # sortie : outputs/situation_report.md
```

## Structure du projet

| Dossier | Contenu |
|---|---|
| `data/` | Modèle de population jour complet (arrivées, file, egress, campeurs) → `attendance.csv` · `flow.csv` · `events.csv` |
| `forecasting/` | Prévision d'affluence : TimesFM zéro-shot (repli saisonnier-naïf) |
| `vision/` | Détection d'anomalies : ResNet18 pré-entraîné gelé + 3 têtes |
| `allocation/` | Allocation de ressources : CSP dynamique OR-Tools CP-SAT |
| `simulation/` | Évaluation de scénarios : simulation multi-agents SimPy + Monte-Carlo |
| `integration/` | Boucle de contrôle reliant les 4 modules |
| `narration/` | Rapport de situation en langage naturel (LLM) |
| `dashboard/` | Dashboard HTML Plotly + vue simulation Canvas |

## Modèle de population

Les données d'affluence ne sont pas des courbes en cloche indépendantes par
zone : `data/generate_data.py` simule une journée complète (10h → minuit, 56
pas) avec une population conservée (Σ affluence des zones = population sur
site), calée sur des observations réelles de festivals (cf. sources) :

| Comportement observé | Modélisation |
|---|---|
| Types de public (étude Bluetooth ~130 000 festivaliers) | 4 types : campeurs (présents jour et nuit), lève-tôt, gros pic d'après-midi, public tête d'affiche |
| ~50 % des visiteurs arrivent 16h-18h ; ruée pré-headliner | demande d'arrivée modélisée par un processus de Poisson non-homogène par type (log-normale, mode ~15h20 + normale ~90 min avant la tête d'affiche) ; le goulot d'admission étale les admissions effectives, la file absorbant le pic 16h-18h — ~63 % du public arrive l'après-midi, pic de population ~18h |
| File d'attente aux portes en fin d'après-midi | goulot d'admission (capacité/pas) : une file se forme dès que le flux la dépasse |
| Egress compressé après le concert | départs quasi nuls avant 20h, puis egress borné par la capacité de sortie (~45 min pour vider l'essentiel) |
| Faible mobilité une fois installé autour d'une scène | choix de zone par softmax du programme des concerts avec forte inertie (seule une fraction re-décide par pas) → migrations en vagues, pas de téléportation |
| Évitement des zones saturées | pénalité d'attractivité au-delà de 85 % de capacité → débordement réaliste |

Résultat : le site démarre avec les campeurs déjà présents (~3 600 personnes
à l'ouverture), se remplit progressivement, sature à la tête d'affiche, puis
se vide ; seuls les campeurs restent la nuit. `python data/generate_data.py`
imprime et vérifie ces propriétés (conservation, pic, file, T90 d'egress,
population résiduelle).

## Vue simulation

`outputs/festival_map.html` est un plan du site vu de dessus qui rejoue
spatialement la journée complète du dernier jour (56 pas → 840 images d'une
minute, horloge 10h → minuit) :

- population dynamique : les points entrent par la porte le matin, saturent
  à la tête d'affiche, puis sortent le soir (1 point ≙ K personnes) ; compteur
  « sur site » avec flux entrant/sortant ;
- goulot d'entrée : la foule s'entasse visiblement à l'extérieur pendant la
  ruée pré-headliner et à l'intérieur pendant l'egress ;
- zones colorées par densité (alerte au-delà du seuil), migrations en vagues
  au fil du programme (bascule vers la scène principale pour la tête
  d'affiche, retour au camping la nuit) ;
- équipes (médical, sécurité, logistique) postées à des emplacements par
  défaut par zone, qui se déplacent physiquement à chaque ré-allocation du
  CSP ;
- files de restauration : aux pics déjeuner/dîner, les festivaliers
  s'alignent devant les stands (la file affichée correspond à la file
  mesurée par l'évaluateur) ; la foule ralentit dans les zones denses
  (diagramme fondamental piéton) ;
- incidents réels répartis sur la journée, mobilisant une équipe (trajet →
  prise en charge → résolu, ou non couvert après 30 min), avec distinction
  détecté / manqué par le CNN ;
- panneau de suivi temps réel des incidents en cours ;
- écran de bilan en fin de journée (bouton Σ ou `?summary=1`) : chaque KPI
  avec / sans gestion prédictive, expliqué en une phrase ;
- lecture / pause / vitesse (×1–×8) / défilement, marqueurs de ré-allocation
  sur la timeline, journal d'événements et compteurs de KPI synchronisés.

Ce n'est pas un second simulateur : c'est un jumeau numérique piloté par les
artefacts déjà produits (`attendance.csv`, `flow.csv`, `events.csv`,
`control_log.json`). Une seule source de vérité — ce qui est affiché est ce
que le système a décidé. La logique de réponse aux incidents et les durées
de trajet reprennent fidèlement le MAS (`simulation/mas.py`), donc la vue ne
peut pas contredire les KPIs.

```bash
python data/generate_data.py      # modèle de population + contrôles de cohérence
python simulation/geometry.py     # calibration géométrie ↔ matrice TRAVEL
python simulation/replay_sim.py   # auto-vérification + génère outputs/replay.json
python dashboard/festival_map.py  # génère outputs/festival_map.html (autonome)
```

Ouvrir sur un instant précis : `festival_map.html?f=665&theme=light&play=1`
(pic tête d'affiche ~21h). Repères utiles : `f=30` (matin, site vide),
`f=610` (ruée + file), `f=785` (egress).

**Sources (comportement réel) :** [étude Bluetooth ~130 000 festivaliers
(arXiv:1306.3133)](https://arxiv.org/abs/1306.3133) ·
[FHWA — Managing Travel for Planned Special Events](https://ops.fhwa.dot.gov/publications/fhwaop04010/handbook.pdf)
· pratiques ingress/egress (Ticket Fairy).

## Résultats

- **Prévision** : TimesFM zéro-shot (télécharge ~200 Mo au premier
  lancement) ; repli saisonnier-naïf documenté en cas d'usage hors-ligne.
- **CNN** : chute ≈ 99 % · objet ≈ 88–99 % · densité MAE ≈ 0,10. Ce sont des
  exactitudes sur un split synthétique in-distribution (prévalence ~30 %),
  pas la précision en exploitation. Sur la journée rejouée, la prévalence
  réelle des chutes est quasi nulle, donc même une bonne spécificité produit
  beaucoup de faux positifs : ~112 alertes caméra pour 15 incidents réels
  (7:1). Le pipeline filtre ces faux positifs (gate de plausibilité par
  densité) et rapporte précision/rappel plutôt que la seule exactitude (voir
  aussi §Limites).
- **Flux optique** : la métrique de cohérence (calculée sur les pixels au
  mouvement significatif) passe son auto-vérification — situation calme non
  signalée, bousculade détectée. Le flux ajoute un signal temporel
  corroborant aux alertes de bousculade (fusion 2/3 signaux).
- **Boucle intégrée** : alertes CNN filtrées (gate de plausibilité + veilles
  densité séparées) → ratio alertes:incidents ramené de ~7:1 à ~2,5:1 ;
  ré-allocations CSP stables (hystérésis).
- **MAS** : au pic (incidents concentrés sur la scène principale),
  l'allocation CSP tient un p95 de ~29 min et ~0 incident non couvert,
  contre ~38 min et des dizaines de non-couverts pour une allocation
  uniforme naïve (20 runs Monte-Carlo).
- **Impact avec / sans gestion prédictive** (évaluateur `kpis.py`, mêmes
  incidents). Le scénario « sans » n'est pas une base de comparaison
  dégradée artificiellement : c'est un planning pré-établi compétent
  (équipes postées par blocs horaires sur l'affluence observée les jours
  précédents, renforts planifiés aux repas, retour au poste après incident)
  — il manque seulement l'ajustement temps réel. Écarts mesurés : détection
  ~4,7 vs ~5,3 min, arrivée médic ~5,0 vs ~5,9 min (88 % vs 76 % sous la
  cible ALS de 8 min), issue des victimes 58 % vs 53 %, file de restauration
  au-delà du seuil de renoncement (10 min) pendant ~15 vs ~30 min cumulées,
  ~1 700 € de ventes préservées. Détail dans l'écran de bilan de la vue
  simulation.

## Choix de conception

| Problème | Méthode | Justification |
|---|---|---|
| Prévision d'affluence | TimesFM (zéro-shot) | Modèle de fondation pré-entraîné sur un très large corpus de séries temporelles : plus robuste qu'un entraînement from scratch sur données simulées limitées ; aucun entraînement local, simple forward CPU |
| Détection d'anomalies | ResNet18 pré-entraîné + 3 têtes | Transfert d'apprentissage : features ImageNet réutilisées, backbone gelé, seules les têtes sont entraînées sur features pré-calculées (quelques secondes sur CPU) |
| Allocation | CSP (CP-SAT) | Ressources discrètes et contraintes dures (minimums de sécurité) ; contraintes souples avec pénalité de réaffectation pour la stabilité opérationnelle |
| Évaluation de scénarios | Multi-agents + Monte-Carlo | Comportements émergents difficiles à capturer analytiquement ; permet de stress-tester les allocations avant déploiement |

## Entraînement

Aucun modèle lourd n'est entraîné localement :

- **TimesFM** est utilisé en zéro-shot — pas d'entraînement.
- **ResNet18** est pré-entraîné ImageNet et gelé ; seules les 3 têtes
  (quelques milliers de paramètres) sont entraînées, sur des features
  pré-calculées, en quelques secondes sur CPU.
- Les poids des têtes (`outputs/vision_cnn.pt`) sont réutilisés d'un
  lancement à l'autre ; supprimer le fichier pour ré-entraîner.
- En cas d'usage hors-ligne (checkpoints non téléchargeables), chaque module
  a un repli documenté : baseline saisonnière pour la prévision,
  entraînement bout en bout du petit ResNet pour la vision.

## Limites connues

- La tête « objet suspect » est un proof of concept sur données
  synthétiques : la détection réelle d'objets fins en foule nécessite des
  caméras haute résolution positionnées sur des points de passage, un
  dataset dédié, et soulève des questions de conformité (RGPD) à traiter
  explicitement.
- Les images sont des vues de dessus simulées ; le pipeline (données →
  entraînement → inférence → alerte → ré-allocation) est en revanche complet
  et fonctionnel de bout en bout.
- Les durées de trajet sont dérivées de la géométrie du site (longueur
  d'allée réelle × échelle 0,5 m/u ÷ vitesse d'intervention 1,5 m/s),
  l'échelle étant calée sur le plan de gestion de foule public d'un festival
  réel comparable (Standon Calling, arène main stage ~15 000 m²). Un
  intervenant traversant une foule dense est ralenti selon le diagramme
  fondamental piéton de Weidmann. Les paramètres chiffrés (temps de réponse
  cibles, débits, panier moyen, vitesses) sont sourcés dans
  `docs/calibration-donnees-reelles.md`.
- La vue simulation échantillonne la foule (1 point ≙ K personnes, ≤ 800
  points) et interpole les positions entre deux relevés de 15 min : les
  points ne sont pas des individus suivis mais un rendu représentatif du
  flux agrégé. La géométrie du plan est la source de vérité des durées (la
  matrice `TRAVEL` du MAS en est dérivée) — vue et KPIs partagent la même
  carte.
- Le modèle de population est agrégé par type (comptes par pas), pas
  micro-agent individuel : il reproduit les courbes réelles (arrivées, file,
  egress, campeurs) sans prétendre suivre chaque festivalier.
- **Dépassements de capacité de zone.** Certaines zones dépassent
  transitoirement 100 % de leur capacité nominale au pic (scène secondaire
  ~114 %, restauration ~114 %, entrée ~200 % — transit/file par conception).
  L'évitement des zones saturées (`CROWD_AVERSION`) est une pénalité souple :
  elle modère mais n'interdit pas la suroccupation, le public s'entassant
  réellement devant une scène populaire. La vue simulation encode
  explicitement ces dépassements (hachures, anneau ambré, libellé
  d'avertissement) plutôt que de les masquer en saturant la couleur à 100 %.
- **Précision du CNN en exploitation.** Sur la journée rejouée, le détecteur
  brut émet ~112 alertes pour 15 incidents réels (ratio 7:1) — conséquence
  normale d'un classifieur imparfait face à une prévalence quasi nulle, pas
  une erreur de mesure. Deux garde-fous sont en place : un gate de
  plausibilité supprime les alertes physiquement improbables (personne au
  sol dans une zone à faible densité), et le pipeline corrobore les alertes
  (un seul signal = à vérifier, deux signaux ou plus = confirmé) et publie
  précision/rappel plutôt que la seule exactitude in-distribution.

## Dépendances

`torch` · `ortools` · `simpy` · `plotly` · `pandas` · `numpy` ·
`scikit-learn` · `opencv-python-headless` (flux optique)

La vue simulation n'ajoute aucune dépendance supplémentaire : le lecteur
HTML est autonome (JavaScript vanilla + Canvas, JSON en ligne, aucun CDN).