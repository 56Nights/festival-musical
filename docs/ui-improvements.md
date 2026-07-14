# Vue simulation — plan d'amélioration UI

Objectif : rendre la vue simulation **lisible par quelqu'un qui ne connaît pas
le projet**, et rendre visibles les quatre choses que le système fait vraiment :
la foule se densifie, les équipes interviennent, les incidents éclatent, le
modèle **anticipe**. Chaque proposition indique où elle s'implémente
(`viewer` = `dashboard/viewer_template.html` seul ; `replay` =
`simulation/replay_sim.py` + format de `replay.json` ; `pipeline` =
`integration/pipeline.py`).

Fait important : `header.steps[*].forecast_peak` (prévision T+2h par zone à
chaque pas) et `frames[*].dens` (densité réelle par frame) sont **déjà** dans
`replay.json` → tout le volet « prévision vs réel » est faisable côté viewer,
sans toucher au moteur.

---

## 1. Double encodage de la densité : la foule qui se **tasse** (replay + viewer)

Aujourd'hui les points sont tirés uniformément dans la zone et flânent d'un
bruit gaussien constant : à 95 % de densité la foule a la même texture qu'à
20 %. Seule la couleur de fond change.

**a. Ancrage focal + tassement (replay).** Chaque zone reçoit un point focal :
le devant de scène (milieu du bord supérieur intérieur) pour MainStage et
SecondStage, le centre pour FoodCourt ; Camping reste dispersé (des tentes).
La position « posée » d'un point est tirée à `focal + dir · R · u^γ(d)` où
`γ` croît avec la densité `d` de la zone (≈ 0.6 uniforme à d faible → ≈ 2.5
très concentré à d ≥ 0.9). À chaque pas, les points posés sont **re-ciblés en
douceur** (glissement de quelques u/frame, pas de téléportation) vers leur
rayon compatible avec la densité courante.

**b. Répulsion de contact au-delà de d > 0.6 (replay).** Réutiliser la
physique granulaire du sablier (`_settle_funnel`) en version légère (hachage
par cellules, seulement zones denses) pour que les points **pavent** l'espace
sans se chevaucher — l'effet « masse compacte » demandé. Coût payé à la
génération (Python), pas au rendu.

**c. Flânerie ∝ (1 − d) (replay, 3 lignes).** Une foule tassée ne bouge plus ;
une zone creuse fourmille. Gratuit et immédiatement lisible.

**d. Lueur additive (viewer).** Deuxième passe de dessin des points avec
`globalCompositeOperation:'lighter'` et un dégradé radial quand d > 0.5 : les
recouvrements créent des **points chauds lumineux** émergents. Rayon des
points légèrement décroissant avec d (petits et serrés = dense).

Moment payant : à 21h, un coin de points pressés contre la scène, luminescent
et quasi immobile ; à 14h, la même zone est un semis lâche qui fourmille.

## 2. Interventions visibles des équipes (replay : +3 champs ; viewer)

Données à ajouter : `inc += [type_idx, unit_id, prog%]`,
`resp += [target_inc_id]` (formats actuels :
`inc=[id,x,y,sev,state,detected]`, `resp=[id,rtype,x,y,state]`).

- **Faisceau de dépêche** : trait pointillé animé (marching ants) de l'unité
  vers son incident pendant `responding`, avec pointe de flèche. L'unité
  clignote (halo alterné type gyrophare) → « secours en route » lisible en 1 s.
- **Prise en charge** : arc de progression circulaire autour de la paire
  unité+incident pendant `treating` (durée déjà connue : `busy_until`) ; la
  pulsation rouge de l'incident se calme à l'orange dès l'arrivée.
- **Compte à rebours d'abandon** : un incident `pending` porte un anneau qui
  se vide sur 30 min (ABANDON_MIN) et pulse de plus en plus vite — la tension
  « personne ne vient » devient visible avant le ✗.
- **Résolution** : éclat vert expansif (~0.5 s) + entrée au journal
  « ✓ résolu en 6 min (M2, FoodCourt) ».
- **Sécurité sur les bagarres (couche visuelle)** : sur `crowd_surge`, les 1–2
  unités sécurité les plus proches se placent en **périmètre** autour de
  l'incident (positions en anneau, posture statique) pendant le traitement.
  Les KPIs restent gouvernés par la réponse médicale (fidèle à `mas.py`) —
  c'est une couche de présentation, à documenter. Option plus profonde :
  dépêche typée (fallen→médical, surge→sécurité) dans `mas.py` ET le replay,
  mais cela change la comparaison Monte-Carlo → décision d'équipe.

## 3. Incidents typés + réaction de foule (replay + viewer)

Le type existe dans `truth_incidents` mais est perdu au rejeu : tout incident
est le même disque « ! ». À faire :

- **Pictogrammes distincts** (SVG inline / tracés canvas, autonomes — pas de
  CDN) : `fallen_person` = silhouette au sol dans un disque rouge ;
  `crowd_surge` = étoile d'impact orange + **anneaux de choc** concentriques
  expansifs au spawn ; `suspicious_object` = losange jaune « ? ». Légende mise
  à jour avec les mêmes pictos.
- **Réaction de la foule (précalculée dans replay)** — le vrai vendeur :
  - bagarre / `crowd_surge` : onde de vitesse radiale sur les points dans un
    rayon R (poussés vers l'extérieur ~10 frames avec décroissance, puis
    retour lent) → un **trou qui s'ouvre dans la foule**, panique lisible ;
  - `fallen_person` : petite clairière (répulsion faible, r ≈ 25 u) + 3–4
    points « badauds » orientés vers l'incident ;
- **Flash de zone** : le contour de la zone flashe blanc 2 frames au spawn
  pour attirer l'œil.
- **Détecté vs manqué** : garder l'anneau pointillé (manqué) mais l'assumer :
  étiquette « non détecté » au survol + au moment de la détection CNN d'un
  incident couvert, petit chip « 👁 CNN » qui s'envole vers le journal.

## 4. Prévision vs réel — montrer que TimesFM **anticipe** (viewer seul)

C'est l'argument de démo le plus fort et le moins visible aujourd'hui
(barres statiques + pointillé jaune conditionnel).

- **Sparklines par zone** (remplace les barres du panneau) : ligne de densité
  RÉELLE tracée jusqu'au playhead + courbe `forecast_peak` **décalée de +2h**
  en orange pointillé (« ce que le modèle voyait venir 2h plus tôt ») + ligne
  de seuil 0.85 + curseur. En lecture, on VOIT l'orange monter avant le trait
  plein. Toutes les données sont déjà dans le JSON.
- **Anneau de pré-chauffe sur la carte** : bande de bordure extérieure de
  chaque zone colorée par `densityColor(forecast_peak)` → la zone « annonce »
  son état futur ; sa bordure chauffe ~2h avant son remplissage. Étiquette de
  zone : `78 % → 92 % ↗` (maintenant → T+2h).
- **Marqueurs d'anticipation sur la timeline** : tick orange quand la
  prévision d'une zone franchit le seuil, tick rouge quand le RÉEL le
  franchit. L'écart entre les deux ticks = l'avance du modèle, visible sans
  explication. Bannière au premier franchissement : « TimesFM prévoit la
  saturation de MainStage (~21h) — 2h d'avance ».
- **KPI d'avance** : « avance moyenne de détection des pics : 1h45 » ou MAE
  glissante des prévisions réalisées.
- Option (pipeline) : journaliser le vecteur de prévision 8 pas complet
  (`forecast_path`) pour tracer un cône/éventail au lieu du seul pic.

## 5. Narration pour un spectateur extérieur (viewer ; icônes bienvenues)

- **Bandeau de chapitres sur la timeline** : phases nommées (Ouverture ·
  Après-midi · Ruée 16–18h · Pré-headliner + file · TÊTE D'AFFICHE · Egress)
  + sous-bandes colorées du **programme des concerts** (couleurs de zone,
  depuis `SCHEDULE`). Cliquer = sauter au moment.
- **Barre de légende narrative** (une phrase, auto-générée des données) :
  « 19:45 — Ruée pré-headliner : ~1 900 pers. en file, le CSP renforce
  l'Entrée (+2 séc.) ».
- **Badge "en concert"** sur la scène active : ♪ + barres d'égaliseur animées
  + popularité — explique CAUSALEMENT les migrations de foule.
- **Compteur de file à la porte** : « file : ~1 200 pers. » flottant près du
  sablier quand la file est significative.
- **Boucle de contrôle rendue visible** : sur ré-allocation déclenchée par
  événement, enchaîner visuellement alerte (chip 👁) → bannière → flash de la
  ligne du tableau d'allocation → badge « +1 » et traînée colorée sur les
  unités qui bougent. Detect → décide → déplace, sans commentaire audio.
- **Journal cliquable** : cliquer une entrée déplace le playhead.
- **Overlay d'accueil** (première ouverture, désactivable, bouton « ? ») :
  4 annotations fléchées — points = foule (1 pt ≙ K pers.), formes = équipes,
  disques pulsés = incidents, timeline = journée 10h→minuit.
- Pictogrammes : SVG inline (silhouette, bouclier, clé, ♪, 👁) — rester
  autonome (aucun CDN), cohérent avec la légende existante.

## 6. Finitions

- KPIs qui « tiquent » (flash bref à l'incrément) ; flèches de tendance sur
  les % de zone ; raccourcis ←/→ (frame) et 1–6 (chapitres).
- **Mode démo/projecteur** : masque le panneau latéral, agrandit horloge +
  bannière narrative (`?demo=1`).
- Taille du fichier : les champs ajoutés (~3 octets/incident, 1/resp) sont
  négligeables ; le tassement ne change que des positions. Si besoin :
  encodage delta des points ou `MAX_DOTS` réduit.

---

## Priorités suggérées

| Prio | Lot | Effort | Impact |
|---|---|---|---|
| P1 | Sparklines prévision + anneau de pré-chauffe + ticks d'anticipation (viewer seul) | S | Prouve l'IA — l'argument jury |
| P1 | Incidents typés + anneaux de choc + faisceaux de dépêche + arc de traitement | M | Rend la boucle vivante |
| P1 | Chapitres + bannière narrative + programme sur la timeline | S | Accessibilité immédiate |
| P2 | Tassement de foule (focal + répulsion + flânerie ∝ 1−d) + lueur | M | Le « wow » visuel |
| P2 | Réaction de foule aux incidents (onde de panique, clairière) | M | Vend la bagarre |
| P2 | Périmètre sécurité sur crowd_surge (couche visuelle) | S | Cohérence métier |
| P3 | Overlay d'accueil, mode démo, KPIs animés, journal cliquable | S | Polish soutenance |

Ordre de dépendance : les lots « replay » (types d'incident, unit_id, prog,
tassement) modifient le format de `replay.json` → les faire ensemble pour ne
régénérer qu'une fois ; tout le lot prévision et la narration sont
indépendants et purement viewer.
