# Démo A/B — prouver la valeur du système (avec vs sans)

> **État : implémenté.** Résultats de la démo (40 tirages Monte-Carlo, mêmes
> incidents) : détection **2,6 vs 5,7 min**, réponse **4,0 vs 6,8 min**
> (**89 % vs 75 %** sous la cible ALS de 8 min), **~2,5 incidents aggravés
> évités**, FoodCourt **~200 vs ~2 100 clients perdus → ~22 700 € de ventes
> sauvées**. Une file se forme TOUJOURS au pic (réaliste, même avec gestion
> prédictive : ~8 min d'attente au pic dîner) ; l'enjeu mesuré est de déployer
> les **équipes volantes AVANT le pic** (prévision) plutôt qu'après (réactif,
> avec 30 min de retard de mobilisation). Ablation : la **vision** porte la
> détection/réponse, la **prévision** porte le service (CA). Reproduire :
> `python simulation/kpis.py` (auto-vérif + ablation) ; artefacts
> `outputs/kpi_comparison.json` + `kpi_ablation.json` ; visibles dans le bandeau
> « AVEC / SANS » du lecteur et la section comparaison du dashboard. Régénéré
> par `run_demo.py` (étape 6/9).


Problème à résoudre : la démo actuelle montre que le système *fonctionne*
(prévision juste, alertes détectées, CSP faisable), pas ce qu'il *rapporte*.
Il manque le **contrefactuel** : que se passerait-il sans nous ? La grille
demande explicitement « Évaluation de scénarios d'organisation » et le niveau 3
de Produire/Concevoir/Formaliser exige une « réelle valeur ajoutée » démontrée.
La réponse : **deux runs identiques sauf le mode de gestion, comparés sur des
KPIs opérationnels**. Le produit ne vend pas des cartes de densité — il vend
des minutes gagnées et des ventes sauvées.

## 1. Le baseline « sans technologie » (recherche)

Gestion réelle d'un festival sans système intelligent (sources en bas) :

| Réalité terrain | Valeur de référence | Modélisation |
|---|---|---|
| Stewards en poste fixe + rondes, remontée par radio | ~1 steward / 100–250 festivaliers (Purple Guide ch. 13) | délai de DÉCOUVERTE humaine d'un incident ∝ densité de staff dans la zone |
| Chaîne observation → radio → décision → départ | délais documentés ; défaillances réelles (Astroworld 2021, retards de communication) | + délai radio/décision fixe (2–5 min) avant dispatch |
| Cibles médicales de rassemblement de masse | BLS < 4 min, ALS < 8 min (StatPearls/NIH NBK597369) ; défib 3-5 min (Resuscitation Council UK — PAS StatPearls) | cibles affichées sur le dashboard — le baseline les rate, le système les tient |
| Ressources en attente à la base, dispatch réactif | pratique par défaut sans prévision | allocation STATIQUE (tout à l'Entrance/base), trajet complet à chaque incident |
| File d'attente restauration | abandon moyen ~6 min (Omnico) ; 80 % n'attendent pas plus de 15 min (Waitwhile 2024) ; tolérance festival 6-10 min ; SLA de service ≈ 2 min/client | modèle de file au FoodCourt : service ∝ staff présent, abandons → CA perdu |

Les deux scénarios rejouent **les mêmes** `attendance.csv` / `events.csv`
(principe d'équité déjà appliqué dans `mas.py` : mêmes incidents, seule la
réponse varie).

- **AVEC (prédictif)** : pipeline actuel — TimesFM (pré-positionnement),
  CNN + flux optique (détection en ~1 min), CSP dynamique.
- **SANS (réactif)** : pas de prévision, pas de vision. Équipes à la base.
  Incident découvert par un steward (délai modélisé), remonté par radio
  (délai fixe), équipe part de la base (trajet TRAVEL complet).

### Modèle de découverte humaine (à sourcer dans le rapport)

`t_découverte ~ Exp(λ)` avec `λ ∝ staff_zone / (1 + k·densité)` — un steward
voit vite un malaise dans une zone clairsemée, tard dans une foule compacte
(occlusion). Paramètres calibrés pour donner ~3–10 min selon le staffing,
+ `t_radio = 2 min`. Analyse de sensibilité ±50 % dans le rapport (le
classement AVEC/SANS ne change pas → conclusion robuste).

## 2. Les KPIs (3 familles, celles proposées + affinage)

### A. Réponse aux incidents (sécurité)
- **t_détection** : apparition → signalement (CNN ~0–1 min vs humain 3–10 min).
- **t_réponse** : apparition → arrivée d'une unité compétente (p50 / p95) —
  déjà mesuré ; le pré-positionnement par prévision réduit le trajet, la
  détection auto réduit l'attente.
- **% dans les cibles** : réponses < 8 min (cible ALS) ; incidents non
  couverts (> 30 min, existant).

### B. Service / revenu (FoodCourt) — modèle capacité + réserve volante
Le sujet demande « allocation des ressources » : on l'étend au service.
- Demande de repas / pas = affluence FoodCourt × courbe d'appétence
  (pics déjeuner/dîner) — dérivée d'`attendance.csv`, rien à régénérer.
- **Capacité PERMANENTE** (vendeurs fixes) volontairement **insuffisante au
  pic** → une file se forme TOUJOURS (réaliste ; au pic dîner la demande
  dépasse même capacité permanente + toute la réserve → ~8 min d'attente
  incompressible, y compris avec gestion prédictive).
- **Équipes VOLANTES** (réserve non affectée) qui doivent INTERVENIR pour
  résorber la file — c'est le levier mesuré :
  - AVEC (prévision) : pré-déployées dès que le pic prévu dépasse le permanent
    (anticipation, pas de retard) ;
  - SANS (réactif) : appelées seulement quand l'attente observée dépasse un
    seuil, arrivant **une par une avec 30 min de retard** de mobilisation →
    il faut re-mobiliser à CHAQUE pic et la file grossit d'abord.
- File → **temps d'attente moyen / p95** ; attente > 8 min → **clients
  perdus** → **CA perdu** (panier ~12 €). Résultat : ~200 vs ~2 100 clients
  perdus sur la journée.

### C. Incidents & escalade
Le NOMBRE d'incidents de base ne doit PAS différer (équité). Ce qui diffère :
- **escalades** : un incident non traité s'aggrave — chute non prise en
  charge > 10 min en zone dense → mouvement de foule ; mouvement de foule
  non contenu > 15 min → chutes multiples. Déterministe (seuils), donc
  explicable. KPI : **incidents évités par le système**.
- **exposition au risque** : Σ sévérité × minutes-sans-prise-en-charge.
- comptage par type AVEC vs SANS (le baseline finit avec plus d'incidents
  *au total* à cause des escalades — c'est l'histoire à raconter).

### Ablation (rapport, pas la démo live)
4 variantes pour attribuer la valeur : complet · sans prévision (CNN seul) ·
sans vision (prévision seule) · sans rien. Monte-Carlo (20 tirages de délais
de découverte), moyennes + IC. Force le point Compétence 3/5.

## 3. Architecture d'implémentation

1. `config.py` — bloc SCENARIOS : délais (découverte, radio), taux de service,
   panier moyen, seuil d'abandon (8 min), seuils d'escalade, cibles (4/8 min).
2. `simulation/service_queue.py` *(nouveau)* — file de service FoodCourt par
   pas : demande, capacité(staffing), attente, abandons, CA. Auto-vérif
   `__main__` (conservation clients, attente↓ quand staff↑).
3. `integration/pipeline.py` — `run_control_loop(mode)` ; mode réactif :
   pas de forecast/alertes, allocation statique. Écrit
   `control_log_predictive.json` + `control_log_reactive.json`.
4. `simulation/kpis.py` *(nouveau)* — évaluateur commun : pour chaque log,
   modèle de découverte + dispatch TRAVEL + escalades + file de service →
   `kpi_comparison.json` (Monte-Carlo, IC). Auto-vérif : mêmes incidents de
   base dans les deux modes, prédictif ≥ réactif sur chaque famille.
5. `simulation/replay_sim.py` — intègre au header la **série KPI du scénario
   SANS** (quelques Ko, pas les frames !) + horodatages de détection par
   incident dans les deux modes.
6. Viewer — bandeau comparatif « AVEC / SANS » : compteurs jumeaux qui
   divergent au fil de la journée (réponse moyenne, clients perdus, escalades
   évitées) ; journal : « détecté 21:04 (flux optique) — sans : ~21:12 ».
7. `dashboard/build_dashboard.py` — section comparaison : CDF des temps de
   réponse, file FoodCourt dans le temps, barres AVEC/SANS par KPI, € perdus.
8. `narration/llm_narrator.py` — reçoit les deux jeux de KPIs → rapport
   comparatif + 2–3 vignettes narratives (« à 21h04… »).

Démo live (10 min) : la vue simulation AVEC + bandeau SANS qui diverge,
puis 1 slide dashboard comparaison. L'ablation reste dans le rapport.

## 4. Garde-fous d'honnêteté (Compétence 5)

- Le baseline est un **modèle** : chaque paramètre est sourcé (tableau §1)
  et listé comme hypothèse ; sensibilité ±50 % documentée.
- Même foule, mêmes incidents de base — on ne truque pas l'environnement.
- Les escalades sont déterministes et à seuils affichés.
- La densité/l'affluence ne changent PAS entre scénarios (le système actuel
  n'agit pas sur la foule) — dire explicitement que la valeur vient de la
  *réponse*, pas d'un contrôle de foule. Extension future : débit de porte
  fonction du staffing (changerait la dynamique → hors périmètre v1).

## Sources

- Purple Guide ch. 13 Crowd Management (ratios stewards) —
  thepurpleguide.co.uk ; synthèse ratios : liveforce.co/blog/how-to-calculate-staffing-ratios
- EMS Mass Gatherings, StatPearls/NIH (cibles BLS 4 min / ALS 8 min /
  défib 5 min, poste médical < 5 min de marche) — ncbi.nlm.nih.gov/books/NBK597369
- Ticket Fairy — Crowd Monitoring During the Festival (limites du monitoring
  humain, réactivité) ; Crowd Surge Contingencies (Astroworld, retards de
  communication) ; Food Vendor SLAs (< 2 min/client) — ticketfairy.com/blog
- Statistiques d'attente : abandon moyen ~6 min (Omnico), 80 % ≤ 15 min (Waitwhile 2024) —
  qless.com/gone-in-6-minutes · waitwhile.com/blog/consumer-survey-waiting-in-line-2024 ; ancien «73 %/5 min» retiré (intraçable) —
  scanqueue.com/blog/state-of-customer-waiting-2026, wavetec.com/blog/queue-management
