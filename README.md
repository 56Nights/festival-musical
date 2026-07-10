# 🎶 Festival Musical Intelligent — SAE S8 (SCIA 2027)

Système intelligent de gestion de festival : prévision d'affluence, détection
d'anomalies, allocation dynamique de ressources et évaluation de scénarios,
intégrés dans une boucle de contrôle unique.

## Démarrage rapide

```bash
pip install -r requirements.txt
python run_demo.py          # ~2 min : données -> entraînements -> boucle -> narration -> dashboard
open outputs/dashboard.html
```

## Architecture

```
                       ┌─────────────────────────────┐
                       │   Données simulées (CSV)     │
                       │ affluence · zones · météo    │
                       └──────┬──────────────┬───────┘
                              │              │
              ┌───────────────▼──┐    ┌──────▼───────────────┐
              │  TRANSFORMER     │    │  CNN MULTI-TÂCHES    │
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
| `data/` | Génération des données simulées (affluence, incidents) | Environnement simulé |
| `forecasting/` | Transformer encoder multi-horizon | 📈 Prévision de l'affluence |
| `vision/` | CNN multi-tâches (3 têtes, backbone partagé) | ⚠️ Détection de situations anormales |
| `allocation/` | CSP dynamique OR-Tools CP-SAT | 🔧 Allocation des ressources |
| `simulation/` | Simulation multi-agents SimPy + Monte-Carlo | 🧪 Évaluation de scénarios |
| `integration/` | Boucle de contrôle reliant les 4 modules | Cohérence du système |
| `narration/` | Rapport de situation en langage naturel (LLM) | Sortie actionnable pour un opérateur |
| `dashboard/` | Dashboard HTML Plotly | Démo soutenance |

## Résultats de la démo

- **Transformer** : MAE ≈ 3,5 % de la capacité sur la validation (split temporel)
- **CNN** : densité MAE ≈ 0,05–0,10 · chute 100 % · objet 99 % (données synthétiques)
- **Boucle intégrée** : alertes CNN détectées → ré-allocations CSP déclenchées
- **MAS** : l'allocation CSP réduit le pire temps de réponse p95 de ~25 à ~18 min
  vs une allocation uniforme naïve (20 runs Monte-Carlo, incidents pondérés
  par la densité de foule)

## Justification des choix (Compétence 3 — Concevoir)

| Problème | Méthode | Pourquoi |
|---|---|---|
| Prévision d'affluence | Transformer encoder | Dépendances temporelles longues (arrivées du matin → pic du soir), covariables connues à l'avance (headliner, heure, météo), sortie multi-horizon |
| Détection d'anomalies | CNN multi-tâches | Backbone partagé = 1 inférence/frame ; avg-pool pour la densité (signal global), max-pool pour les petits objets saillants ; taux d'échantillonnage découplés par tête |
| Allocation | CSP (CP-SAT) | Ressources discrètes + contraintes dures (minimums de sécurité) ; contraintes souples avec pénalité de réaffectation pour la stabilité opérationnelle |
| Évaluation de scénarios | Multi-agents + Monte-Carlo | Comportements émergents non capturables analytiquement ; permet de stress-tester les allocations avant déploiement |

## Limites assumées (à reprendre dans le rapport — Compétence 5)

- La tête « objet suspect » est un **proof of concept sur données synthétiques** :
  la détection réelle d'objets fins (seringue) en foule exige des caméras
  haute résolution positionnées sur des points de passage, un dataset dédié,
  et pose des questions RGPD à traiter explicitement.
- Les images sont des vues de dessus **simulées** (conformément au sujet) ;
  le pipeline (données → entraînement → inférence → alerte → ré-allocation)
  est en revanche complet et fonctionnel de bout en bout.
- La matrice de distances inter-zones est simplifiée ; un plan réel du site
  la remplacerait sans changer l'architecture.

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
