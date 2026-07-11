# Modèle d'incidents v2 — cycles de vie, réactions en chaîne, chaîne de survie

> **État : implémenté.** Simulateur minute par minute dans `simulation/kpis.py`
> (dispatch typé, chaîne de survie à deux étages, chaînes surge/fight, MCE,
> issues). Nouveau type `fight` de bout en bout (données → CSP → KPI → lecteur).
> Résultats (40 tirages, mêmes incidents de base) : détection 3,8 / 5,5 min ·
> **premiers gestes 2,6 / 5,1 min** · **arrivée médic 3,1 / 7,8 min** (99 % / 77 %
> sous 8 min) · **blessés induits 5,0 / 7,6** (~2,5 évités) · **R_eff 0,46 / 0,69**
> · **MCE 0,03 / 0,47** · **issue des victimes 65 % / 35 %** (~2,7 issues
> défavorables évitées). Ablation : la **vision** porte détection/réponse/issue,
> la **prévision** porte le service + une part de R_eff/issue. Vérifier :
> `python simulation/kpis.py`. Visuel : pictogramme bagarre, **liens
> parent→enfant** des blessés induits, cordon sécurité sur surge/fight, bandeau
> « bilan chaîne » (blessés induits, R, issue) — `python simulation/replay_sim.py`.
>
> Deux honnêtetés à garder au rapport : (1) l'« issue » est un score de risque
> agrégé, pas une prédiction de décès individuel ; (2) le jumeau spatial
> (`replay_sim.py`) rejoue une chaîne *représentative* (RNG propre) — le
> comptage KPI autoritatif est celui de `kpis.py`. Les bagarres sont détectées
> par la sécurité (pas la caméra), d'où l'absence de speedup caméra sur ce type.


Objectif : remplacer le modèle actuel (incident ponctuel + escalade à seuil
unique) par des **cycles de vie par type** fondés sur la littérature des vrais
festivals. Deux idées structurantes :

1. **Réaction en chaîne** — bagarres et mouvements de foule ne sont pas des
   événements isolés : non contenus, ils *engendrent* d'autres incidents
   (processus de branchement). La valeur du système = maintenir le « taux de
   reproduction » R < 1.
2. **Chaîne de survie à deux étages** — pour chutes et blessés de bagarre, ce
   qui compte est (a) le temps avant les PREMIERS GESTES (n'importe quel staff
   formé : sécurité/steward — alerte, RCP, compression) qui **gèle** la
   dégradation, puis (b) le temps avant le MÉDIC qui résout. Réduire le temps
   total d'arrivée des médecins est l'objectif explicite ; les premiers gestes
   achètent ce temps.

## 1. Ce que disent les vrais festivals (sources en bas)

| Fait terrain | Valeur | Usage dans le modèle |
|---|---|---|
| Densité critique de foule | ~6–7 pers/m² : la foule devient « fluide », turbulence, ondes de choc | seuil de déclenchement d'un mouvement de foule (proxy : densité zone ≥ 0,85) |
| Effondrement progressif | une chute initiale en foule dense se propage en dominos → empilement, asphyxie compressive | chaîne surge → chutes induites, taux ∝ densité × intensité |
| Astroworld 2021 | artiste sur scène 21h, « mass casualty event » déclaré 30 min plus tard ; morts par asphyxie compressive | un surge non contenu > N min ⇒ état « MCE » (catastrophe) ; la durée SANS containment est LA variable |
| Asphyxie compressive | issue neurologique favorable < 1 % après ~4 min d'arrêt ; RCP immédiate sur place = survie beaucoup plus probable | fenêtre d'issue 4–6 min pour les victimes de crush ; les premiers gestes gèlent l'horloge |
| Arrêt cardiaque général | survie −7 à −10 %/min sans RCP | courbe d'issue des chutes « standard » (plus lente que crush) |
| Chaîne de secours réelle | sécurité/bénévoles = premiers intervenants (alerte, RCP, hémostase), puis équipes médicales à pied/vélo, puis poste médical | dispatch à DEUX étages : premier staff formé sur place, puis médic |
| Bagarres | intervention PRÉCOCE en binôme + désescalade verbale avant que ça grossisse ; les badauds alimentent l'escalade | intensité qui croît si non contenue ; containment = 2 sécurité ; tôt = désescalade rapide, tard = long + blessés |
| Taux de présentation patients (PPR) | 7–13,5 patients / 1 000 festivaliers (Glastonbury 13,47 ; étude autrichienne 12,0 ; collégial 7,0) | validation d'échelle : ~20 k visiteurs ⇒ 140–270 présentations, dont ~5–10 % d'urgences aiguës ⇒ nos 10–25 incidents/jour simulés sont le bon ordre de grandeur |

## 2. Cycles de vie par type (machines à états)

### 2.1 `fight` (NOUVEAU type, distinct du mouvement de foule)
```
déclenchée (I=1, 2 protagonistes)
  │ non contenue : I(t) croît (badauds aspirés) — I ×~1,3 / min si densité>0,5
  │ chaque minute : P(blessé) ∝ I → spawn fallen_person (léger)
  ▼
containment : 2 unités SÉCURITÉ sur place
  ├─ arrivée tôt (I < 3)  : désescalade verbale ~2–4 min, 0 blessé
  └─ arrivée tard (I ≥ 3) : maîtrise ~8–12 min, blessés déjà induits
  ▼ résolue (sécurité repart) ; blessés = incidents médicaux séparés
```
Génération : probabilité ∝ densité × facteur soirée/alcool (les bagarres
arrivent le soir dans les zones denses). À ajouter dans `generate_data.py`.

### 2.2 `crowd_surge` (mouvement de foule) — 3 phases + chaîne
```
turbulence (déclenchée si densité zone ≥ 0,85 — proxy des 6 pers/m²)
  │ intensité I(t) croît tant que la zone reste dense et non gérée
  │ CHAÎNE : chaque minute, spawn de chutes CRUSH au taux λ = k·densité·I
  │ (effondrement progressif en dominos)
  ▼
containment : K=3 unités SÉCURITÉ (ouvrir l'espace, couper le flux entrant)
  │ pendant T_contain ≈ 5 min → I décroît, la chaîne s'arrête
  ▼
si jamais contenu pendant 30 min → MASS CASUALTY EVENT (état catastrophe,
  rafale de chutes crush) — la leçon d'Astroworld : la durée non gérée est fatale
```

### 2.3 `fallen_person` — gravité évolutive + issue quantifiée
Deux classes :
- **standard** (malaise, blessure de bagarre) : dégradation lente,
  survie ≈ 100 % → décroît ~7 %/min sans premiers gestes ;
- **crush** (née d'un surge en zone dense) : fenêtre 4–6 min —
  dégradation ~20 %/min sans premiers gestes.

Horloge d'issue :
```
apparition → [t1 : PREMIERS GESTES par le staff formé le plus proche
              (sécurité compte !) → l'issue est GELÉE à sa valeur courante]
           → [t2 : MÉDIC arrive → traitement → résolu, issue finale]
issue(t1, t2) = décroissance(classe, t1) ; si t1 jamais : décroissance jusqu'à t2
```
KPIs : `t_premiers_gestes`, `t_medic` (l'objectif explicite du projet),
`issue attendue` (≈ « probabilité de survie ») par incident, agrégée en
**« issues défavorables évitées »** avec vs sans.

### 2.4 `suspicious_object` — inchangé (cordon sécurité), escalade = panique
(surge) si ignoré > 20 min en zone dense. Cas mineur, garder simple.

## 3. Dispatch v2 (dans `kpis.py`, notre modèle d'impact)

- **Typé** : bagarre/surge → sécurité (containment) ; chute → premiers gestes
  par le staff formé le plus proche (tout type) PUIS médic ; objet → sécurité.
- Les unités sécurité en containment sont indisponibles pour autre chose
  (le coût d'opportunité existe enfin).
- La détection reste celle du modèle actuel (caméra ~1 min vs découverte
  humaine ∝ densité/staff). La chaîne amplifie l'écart : détecter un surge
  3 min plus tôt = moins de chutes induites = moins de médics mobilisés.
- `mas.py` reste inchangé (comparaison d'allocations) ; le cycle de vie vit
  dans `kpis.py` (évaluateur d'impact) et, en visuel, dans `replay_sim.py`.

## 4. Formalisation « réaction en chaîne » (argument jury)

Processus de branchement : chaque incident non contenu engendre en moyenne
R enfants (R dépend du délai de containment et de la densité).
- R < 1 : les incidents s'éteignent (journée gérée) ;
- R ≥ 1 : cascade sur-critique (trajectoire Astroworld).
KPI : **R_eff mesuré** avec vs sans — « sans le système, chaque mouvement de
foule engendre ~1,4 incident secondaire ; avec, ~0,2 ». Une seule phrase,
tout le projet dedans.

## 5. Nouveaux KPIs (familles existantes enrichies)

| KPI | Définition | Remplace / complète |
|---|---|---|
| t_premiers_gestes (p50/p95) | apparition → premier staff formé sur place | nouveau |
| t_medic (p50/p95) | apparition → arrivée équipe médicale | = « réponse » actuel, gardé |
| t_containment | apparition → bagarre/surge contenu | nouveau |
| blessés induits | chutes nées des chaînes (avec vs sans) | remplace « escalades » |
| R_eff | enfants moyens par incident non contenu | nouveau (headline) |
| issues défavorables évitées | Σ (1 − issue) sans − avec | nouveau (le chiffre humain) |
| MCE | nb d'états « mass casualty » atteints | nouveau (binaire catastrophe) |

## 6. Implémentation (ordre de dépendance)

1. `config.py` — bloc INCIDENTS_V2 : seuils (densité crush 0,85, fenêtres
   4–6 min / 7 %/min, croissance bagarre, K et T de containment, 30 min MCE),
   tous commentés avec leur source.
2. `data/generate_data.py` — événements `fight` (soirée × densité) ; tagger
   les surges déclenchés par densité ; classe crush/standard sur les chutes.
3. `allocation/dynamic_csp.py` — SEVERITY : `fight` = 2 (comme surge).
4. `simulation/kpis.py` — cycles de vie ci-dessus dans `_simulate_incidents`
   (remplace l'escalade à seuil), dispatch typé, deux étages, nouveaux KPIs,
   auto-vérifs : R_eff(avec) < R_eff(sans) ; t_medic(avec) < t_medic(sans) ;
   0 MCE avec, possibles sans ; issues avec ≥ issues sans.
5. `simulation/replay_sim.py` + viewer — visuel : lien parent→enfant des
   incidents induits, anneau d'intensité qui grossit/rétrécit sur bagarre/surge,
   badge « premiers gestes » (bouclier) avant la croix médicale, état MCE
   (zone entière pulsée). Bandeau AVEC/SANS : + blessés induits et R_eff.
6. Dashboard/narration — R_eff, blessés induits, issues évitées.

## 7. Garde-fous d'honnêteté

- Chaque paramètre chiffré est sourcé (tableau §1) ; ceux qui ne le sont pas
  (croissance de bagarre ×1,3/min, λ de chutes induites) sont marqués
  « illustratifs » + analyse de sensibilité ±50 % (le classement avec/sans ne
  s'inverse pas — vérifié par l'auto-vérif).
- L'« issue » est un score de risque agrégé, PAS une prédiction de décès
  individuelle — le rapport doit le dire (on simule des vies, prudence de ton).
- Les incidents de BASE restent identiques entre scénarios ; seules les
  conséquences (chaînes, issues) divergent — l'équité de comparaison tient.
- Validation d'échelle par le PPR réel (7–13/1000) : à citer dans le rapport.

## Sources

- Crowd crush / turbulence / effondrement progressif : Helbing & Johansson,
  *Crowd turbulence: the physics of crowd disasters* (arxiv.org/pdf/0708.3339) ;
  Wikipedia *Crowd collapses and crushes* ; The Conversation *Ten tips for
  surviving a crowd crush* (~6–7 pers/m²).
- Astroworld : chronologie ABC13/ABC News (MCE déclaré ~30 min après le début
  du set) ; Wikipedia *Astroworld Festival crowd crush* (asphyxie compressive).
- Asphyxie / RCP : *CPR duration and prognosis in OHCA due to asphyxiation*
  (ScienceDirect, issue favorable <1 % après ~4 min) ; *Bystander CPR and
  outcomes of mass cardiac arrests caused by a crowd crush* (ScienceDirect).
- Chaîne médicale festival : *Glastonbury Festival: Medical Care…* (PPR 13,47/
  1000 ; équipes à pied/vélo + poste médical) ; étude autrichienne 7 ans
  (PPR ~12/1000) ; Ticket Fairy *Medical Emergency Response* (staff non médical
  = premiers intervenants : alerte, RCP, hémostase).
- Bagarres / désescalade : Ticket Fairy *Festival Security: A Visible, Helpful,
  and De-Escalatory Approach* (binômes, intervention précoce avant escalade) ;
  *Fans Behaving Badly* (signes précurseurs, badauds).
