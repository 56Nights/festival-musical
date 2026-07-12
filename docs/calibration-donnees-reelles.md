# Calibration sur données réelles — paramètres sourcés

> **État : IMPLÉMENTÉ** (cf. `docs/changelog.md` §6). Les valeurs de ce document
> sont appliquées dans le code : échelle 0,5 m/u, durées de trajet dérivées de
> la géométrie, diagramme fondamental de Weidmann, `TREAT_MIN`/`MCE_MIN`/
> `MEAL_BASKET_EUR`/`FIRST_AID_TARGET_MIN` re-sourcés, egress dérivé du Green
> Guide. Vérifier : `python simulation/geometry.py` (échelle, aires m²/pers·m²,
> durées) et `python simulation/kpis.py`. Ce fichier reste la **référence
> sourcée** (dimensions réelles, temps de déplacement, temps d'intervention,
> files d'attente) pour le rapport. Chaque paramètre de `config.py` visé est
> mappé à une valeur réelle **avec sa source** ; les valeurs non sourçables
> sont explicitement marquées *hypothèse de modélisation* (garde-fou
> d'honnêteté, Compétence 5). Ce document **corrige aussi trois citations**
> des docs existants (voir §7).
>
> Hiérarchie des sources utilisée : (1) littérature académique / revues à
> comité de lecture, (2) guides officiels (Purple Guide, Green Guide/SGSA,
> StatPearls/NIH, rapports d'enquête officiels), (3) plans opérationnels
> réels publiés (licensing), (4) presse spécialisée / blogs industrie
> (Ticket Fairy…) — les niveaux 3-4 sont signalés.

---

## 1. Déplacements piétons & vitesse selon la densité

| Grandeur | Valeur réelle | Source |
|---|---|---|
| Vitesse de marche libre | **1,34 m/s** (80,4 m/min) | Weidmann 1993 (ETH Zürich, IVT n°90), via Kretz, [arXiv:0901.0170](https://arxiv.org/abs/0901.0170) ; confirmé par la revue Vanumu et al., *Eur. Transp. Res. Rev.* 9:49 (2017) |
| Diagramme fondamental vitesse-densité | v(ρ) = v_libre·[1 − exp(−γ(1/ρ − 1/ρ_max))], **γ = 1,913 m⁻², ρ_max = 5,4 p/m²** (formule de Kladek reprise par Weidmann) | idem [arXiv:0901.0170](https://arxiv.org/abs/0901.0170), éq. 11 |
| Points dérivés de la formule *(calculés, pas cités)* | 0,5 p/m² → 1,30 m/s · 1 → 1,06 · 2 → 0,61 · 3 → 0,33 · 4 → 0,16 · 5 → 0,04 · 5,4 → 0 | dérivation de la formule ci-dessus |
| Vitesse résiduelle en foule extrême | ~18 m/min (0,3 m/s) à 6 p/m² ; au-delà de 7 p/m² le contrôle individuel du mouvement est perdu (turbulence) | Helbing, Johansson & Al-Abideen, *Crowd turbulence*, [arXiv:0708.3339](https://arxiv.org/abs/0708.3339) |

**Application au code.**
- `WALK_SPEED` devient dérivé : `WALK_SPEED = 1.34 * 60 / METERS_PER_U` u/min
  (foule) ; équipes en intervention ~1,6 m/s (marche rapide, borne haute de la
  distribution de Weidmann — *hypothèse : facteur 1,2, non sourcé finement*).
- Étape 5.3 du plan : vitesse des points multipliée par
  `1 − exp(−1.913·(1/ρ − 1/5.4))` avec ρ = densité locale convertie en p/m²
  (voir §2) — la ruée pré-headliner ralentit *mécaniquement*.

## 2. Densités de foule : correspondance avec notre « densité » (0-1)

Notre `density` = affluence/capacité. Correspondance sourcée à documenter dans
le rapport :

| Seuil réel | Valeur | Source |
|---|---|---|
| Densité de planification événement plein air | **2 p/m²** (0,5 m²/pers) | Purple Guide / Event Safety Guide, cité dans le plan de gestion de foule de **Standon Calling** (licensing East Herts Council, [PDF public](https://democracy.eastherts.gov.uk/documents/s70465/Appendix%20E%20Crowd%20Management%20Plan.pdf?J=1)) |
| Devant de scène réel en concert | **3-4 p/m²** (arrière : ~2 p/m²) | Standon Calling CMP (verbatim : « front of stage locations will likely have a crowd density of 3-4 people per square metre ») |
| Maximum réglementaire debout | 4,7 p/m² (47 p/10 m²) | Green Guide (Guide to Safety at Sports Grounds), cité idem |
| Début des forces dangereuses | ~5,4 p/m² (2 sq ft/pers, Fruin) ; « congested and unstable » ≥ 6 p/m² | Fruin, *Crowd Dynamics* ([archive G.K. Still](https://www.gkstill.com/Support/crowd-flow/fruin/Fruin3.html)) ; [InCrowd Safety](https://incrowdsafety.co.uk/flow-rates-densities-and-the-maths/) |
| Turbulence de foule / accidents | **6-7+ p/m²** | Helbing et al., [arXiv:0708.3339](https://arxiv.org/abs/0708.3339) |

**Application.** `SURGE_DENSITY = 0.85` reste un **proxy** : on documente que
`density = 1.0` d'une zone scène ≙ ~4 p/m² au devant de scène (pic focal du
tassement), donc 0,85 ≙ zone en régime 3-4 p/m² local avec poches à 6+ —
c'est le régime où la littérature situe le danger. À imprimer par
l'auto-vérification de `geometry.py` (p/m² au pic par zone, cf. §3).

## 3. Dimensions du site (référence : festival réel de taille comparable)

Référence retenue : **Standon Calling** (~17 000 pers/jour, licencié ~38 000
pic) — seul festival de notre ordre de grandeur avec un plan de gestion de
foule **public et chiffré** :

| Grandeur | Valeur réelle | Source |
|---|---|---|
| Arène main stage | **15 357 m²** (+ 7 858 m² d'arène secondaire) | Standon Calling CMP (PDF ci-dessus) |
| Capacité arène | aire × 2 p/m² (main) et × 1 p/m² (secondaire) = 38 572 pers | idem, formule verbatim |
| Traversée de site, festival géant | Glastonbury : 364 ha, « jusqu'à 1h30 » de marche à travers le site ; 700 m-2 km entre camping accessible et zones | [Ordnance Survey](https://osmaps.com/discover/guides/walking-around-glastonbury-festival/) ; [glastonburyfestivals.co.uk](https://www.glastonburyfestivals.co.uk/information/access-information/distances/) |
| Entre deux scènes, grand festival | Coachella : **~15 min** de marche | [Stage Hoppers](https://stagehoppers.com/stage-hoppers-guide-to-coachella/) *(guide, niveau 4)* |

**Choix d'échelle recommandé** : `METERS_PER_U = 0.5` → site simulé
500 × 350 m (~17,5 ha), MainStage ≈ 14 300 m² (≈ l'arène de Standon),
trajets inter-zones dérivés de la géométrie ≈ 2-5 min à 1,34 m/s — cohérent
avec un site de 16-20 k personnes (entre « quelques minutes » à cette
échelle et les 15 min de Coachella pour un site 10× plus grand).
**Validation** : le `__main__` de `geometry.py` imprimera aire (m²), capacité
et p/m² au pic par zone ; l'écart avec les seuils du §2 doit rester
défendable.

## 4. Portes : débits d'entrée et de sortie

| Grandeur | Valeur réelle | Source |
|---|---|---|
| Débit d'un point d'entrée (tourniquet) | **660 pers/h** max par point d'entrée | SGSA, Green Guide — [Ingress](https://sgsa.org.uk/physical-factors/circulation/ingress/) |
| Couloir de fouille | ~**300 pers/h** par agent ; fouille de sac +20-40 s/pers | Ticket Fairy, [Festival Entry and Exit Design](https://www.ticketfairy.com/blog/festival-entry-and-exit-design-gate-layouts-and-security-screening) *(niveau 4)* |
| Débit d'egress | **82 p/m/min** (surface plane, Green Guide) ; variante plein air 109 ; **déclassé à 70 p/m/min** terrain humide/public alcoolisé | SGSA — [Egress](https://sgsa.org.uk/physical-factors/circulation/egress/) ; Standon Calling CMP ; [Sabre Risk](https://www.sabre-risk.com/post/major-events-capacity-and-emergency-egress-calculations) |
| Temps d'egress d'urgence | 8 min (stade) ; ≤ 15 min festival greenfield ; Standon : 10 min notionnels | Sabre Risk ; Standon CMP |
| Sortie normale d'un stade | ~25-30 min à pied | [SecurityInfoWatch](https://www.securityinfowatch.com/alarms-monitoring/fire-life-safety/article/10592478/an-introduction-to-stadium-and-arena-egress-design) *(presse pro)* |

**Application.**
- `GATE_CAP_STEP = 560`/15 min = 2 240/h ≙ **3-4 points d'entrée** Green Guide
  (ou ~7 couloirs de fouille) — valeur actuelle conservée, désormais sourcée ;
  documenter « la porte simulée = un module de 3-4 lignes ».
- Nouveau paramètre `EXIT_WIDTH_M` : `NECK_EXIT_CAP_STEP` devient dérivé =
  `70 p/m/min × EXIT_WIDTH_M × 15`. Valeur actuelle (1 550/pas ≈ 103 p/min)
  ≙ **1,5 m de largeur effective** — étroit pour 16 k pers. (choix
  pédagogique qui crée la file d'egress) ; recommandation : 2 m
  (`NECK_EXIT_CAP_STEP = 2100`) et le documenter comme goulot volontaire
  sous-dimensionné vs les ~4-6 m qu'exigerait l'egress d'urgence en 15 min.

## 5. Médical (rassemblements de masse)

| Grandeur | Valeur réelle | Source |
|---|---|---|
| Cibles de réponse | **BLS ≤ 4 min, ALS ≤ 8 min**, évacuation ≤ 30 min | Wolin & Friedman, *EMS Mass Gatherings*, StatPearls/NCBI [NBK597369](https://www.ncbi.nlm.nih.gov/books/NBK597369/) (2023) |
| Défibrillation | 3-5 min → survie 50-70 % ; −10 %/min de retard | Resuscitation Council UK ([communiqué](https://www.resus.org.uk/about-us/news-and-events/make-defibs-accessible-247-help-increase-survival-rates-across-uk-say)) — **PAS dans StatPearls**, correction vs docs antérieurs |
| Dégradation sans RCP | **−7 à −10 %/min** | AHA, *Circulation* 2000 ([Part 4: AED](https://www.ahajournals.org/doi/10.1161/circ.102.suppl_1.i-60)) ; [Croix-Rouge US](https://www.redcross.org/take-a-class/resources/articles/cpr-facts-and-statistics) |
| RCP précoce par témoin | survie ×2-3 (pooled 7,6 % → 11,3 %) | AHA ([CPR facts](https://cpr.heart.org/en/resources/cpr-facts-and-stats)) ; Sasson et al., *Circ Cardiovasc Qual Outcomes* 2010 ([PubMed](https://pubmed.ncbi.nlm.nih.gov/20123673/)) |
| Fenêtre d'asphyxie compressive (crush) | ~30 s → inconscience ; ~6 min → décès | G. Keith Still (prof. crowd science), interviews [PBS](https://www.pbs.org/newshour/health/how-and-why-do-crowd-surges-turn-deadly)/NPR post-Astroworld — **témoignage d'expert, pas une mesure** |
| Crush massif, issue réelle | Itaewon 2022 : 119 arrêts cardiaques, 18,5 % de RCP avant secours, **0,8 % de survie**, ambulances à 59 min | Choi, Shin et al., *Resuscitation* 2025 ([PubMed](https://pubmed.ncbi.nlm.nih.gov/39709174/)) |
| Temps sur place des secours (urbain) | moyens 8-19,5 min ; médianes 15-19,5 min (IQR 11-28) | Alruwaili & Alanazy, revue systématique, *Healthcare* 2022 ([PMC9778378](https://pmc.ncbi.nlm.nih.gov/articles/PMC9778378/)) |
| Médics à vélo sur événement | réponse **< 2 min** | Gorham & Kramer, *Prehosp Disaster Med* 1997 ([PubMed](https://pubmed.ncbi.nlm.nih.gov/10187005/)) |
| Chaîne de soin sur site mesurée | Tokyo 2020 (stade) : 22 min médianes jusqu'au poste médical, 51 min de soin sur site | Sekizaki et al., *Front. Public Health* 2025 ([PMC12597977](https://pmc.ncbi.nlm.nih.gov/articles/PMC12597977/)) |
| PPR (patients / 1000 festivaliers) | Glastonbury 2022 : **13,47** (TTHR 0,30) ; Autriche 7 ans : médiane **12,01** (9,3-20,9) | Bennett & Cottrell, *Prehosp Disaster Med* 2024 ([PMC11035920](https://pmc.ncbi.nlm.nih.gov/articles/PMC11035920/)) ; Maleczek et al., *Wien Klin Wochenschr* 2021 ([PMC9023407](https://pmc.ncbi.nlm.nih.gov/articles/PMC9023407/)) |
| Astroworld : chronologie officielle | 21h02 début du set · **21h07 premier appel 911** · 21h38 task force ambulances · 21h39 début show-stop · **21h47 déclaration MCE** · 22h12 fin | Timeline officielle HPD via [ABC13](https://abc13.com/post/astroworld-timeline-what-happened-at-concert-crowd-crush/13441821/) |

**Application (`config.py`).**
- `RESPONSE_TARGET_MIN = 8` ✔ confirmé (ALS). **Ajouter
  `FIRST_AID_TARGET_MIN = 4`** (BLS) — on mesure déjà `t_premiers_gestes`,
  la cible sourcée existe : l'afficher dans le bilan (étape 2 du plan).
- `FALL_DECAY["standard"] = 0.07` ✔ sourcé (borne basse AHA 7-10 %/min).
- `FALL_DECAY["crush"] = 0.20` : **dérivé** de la fenêtre ~30 s/6 min de
  Still (expertise, pas mesure) — garder, marquer *dérivé d'expertise* +
  sensibilité ±50 %. Le cas réel (Itaewon, 0,8 % de survie) confirme que
  l'issue s'effondre vite sans prise en charge.
- `MCE_MIN = 30` → **40** : l'écart officiel premier-signal→MCE d'Astroworld
  est de 40 min (21h07→21h47), pas 30.
- `TREAT_MIN = (5, 12)` → **(8, 20)** : aligné sur les temps sur place
  urbains (moyennes 8-19,5 min) ; les cas mineurs de festival ressortent
  vite (90,7 % des patients de Glastonbury repartent directement), la borne
  basse 8 min reste raisonnable pour une équipe qui stabilise + relève.
- `FIRST_AID_HOLD_MIN = 4` ✔ compatible BLS (le secouriste tient jusqu'au
  relais).
- Justification vitesse médics ×(>1) sur allées (étape 6 du plan) : les
  médics vélo réels répondent < 2 min (Gorham 1997).
- Validation d'échelle : 10-25 incidents aigus/jour simulés pour 16-20 k
  pers. ↔ PPR 12-13,5/1000 dont ~5-10 % aigus ✔ (déjà dans
  `docs/incident-model.md`, sources désormais primaires).

## 6. FoodCourt : files, service, panier

| Grandeur | Valeur réelle | Source |
|---|---|---|
| Abandon de file | moyenne UK : **5 min 54 s** ; 80 % n'attendent pas plus de 15 min ; tolérance festival : **6-10 min** | Omnico Group (via [QLess](https://www.qless.com/gone-in-6-minutes-average-queuing-time-uk-shoppers-are-willing-to-wait/)) ; [Waitwhile 2024](https://waitwhile.com/blog/consumer-survey-waiting-in-line-2024/) (n=1000) ; [Ticket Fairy SLA](https://www.ticketfairy.com/blog/food-vendor-slas-for-throughput-and-safety-at-summer-festivals) *(niveau 4)* |
| **Balking** (renoncement à l'arrivée) | P(renoncer \| attente estimée W) = **1 − exp(−(W − seuil)/échelle)** pour W > seuil (patience exponentielle) ; forme bornée, le « 1/e^(−t) » naïf diverge | Erlang-A / Palm 1957 ; Garnett, Mandelbaum & Reiman, *MSOM* 2002 ([INFORMS](https://pubsonline.informs.org/doi/10.1287/msom.4.3.208.7753)). Patience réelle non-exponentielle (Brown et al., *JASA* 2005) → simplification assumée |
| ⚠ « 73 % abandonnent après 5 min » | **INTRAÇABLE** — folklore marketing (attribué à ICMI, absent de l'article ICMI cité) | vérification directe ; **ne plus citer** (correction §7) |
| Temps de service par client | SLA festival : **< 2 min/client** au pic (~30 clients/h/caisse) ; drive-thru US total moyen 5 min 29 s (2024) | Ticket Fairy SLA *(niveau 4)* ; [QSR Magazine 2024](https://www.qsrmagazine.com/story/the-2024-qsr-drive-thru-report/) (étude mystère) |
| Dépense F&B | **~65 $/festivalier/jour** (≈ 60 €), ~4,2 boissons + 2,3 plats ; panier alimentaire pivot ~**16 $** | atVenu (données POS, 650+ festivals) : [1](https://www.atvenu.com/post/are-fans-spending-less-at-concerts-festivals-with-ticket-prices-increasing), [2](https://www.atvenu.com/features/festival-insights-2023) |
| Stands / festivalier | ~1 stand / 500 (Glastonbury : 400+ pour 200 k) à 1/1 250 (grands campings) | Ticket Fairy [1](https://www.ticketfairy.com/blog/feeding-50000-per-hour-festival-food-court-design-strategies), [2](https://www.ticketfairy.com/blog/food-vendor-management-101-curating-quality-eats-safely-for-festival-fans) *(niveau 4)* |
| Attente « normale » vs échec | ≤ 10 min bon · 15-20 min pic tendu (signalétique réelle « ~15 min to order ») · ≥ 30-45 min état d'échec | Ticket Fairy (design food court) ; presse (Download 2026 : 3 h au merch = extrême) — *calage interprétatif, pas une mesure unique* |
| Part des présents qui mangent au pic | ~85 % sur un créneau déjeuner d'événement ; ~2 achats food/jour/fan | [ezCater](https://www.ezcater.com/lunchrush/office/order-proper-catering-portions-next-event/) (guide traiteur) ; atVenu — **hypothèse interpolée : 60-85 % par fenêtre de 2 h** |

**Application (`config.py`).**
- `SERVICE_MIN_PER_CUSTOMER = 2.0` ✔ sourcé tel quel (SLA Ticket Fairy,
  cohérent avec 30 clients/h/caisse).
- **Balking** (`BALK_THRESHOLD_MIN = 10`, `BALK_SCALE_MIN = 4`) : à l'arrivée,
  le client OBSERVE la file et renonce avec P(W) = 1 − exp(−(W−10)/4). Seuil de
  grâce 10 min (choix d'équipe, généreux vs la tolérance sourcée 6-10 min) puis
  montée exponentielle → tolérance moyenne ~14 min. Remplace l'ancien seuil sec
  « tout le monde part au-delà de 8 min » ; une file RÉELLE se forme au pic
  (auto-régulation) au lieu d'une coupure brutale. Forme Erlang-A (Palm 1957 ;
  Garnett-Mandelbaum-Reiman 2002) ; `ABANDON_WAIT_MIN` conservé pour l'affichage.
- `MEAL_BASKET_EUR = 12` → **14** (≈ pivot 16 $ atVenu ; ordre de grandeur
  validé par les 65 $/jour ÷ ~4-6 transactions).
- `SERVICE_POINTS_PER_STAFF = 18` : une « unité logistique » = un îlot de
  ~18 points de vente à 30 clients/h chacun (540 clients/h) — cohérent avec
  le benchmark stands/festivalier une fois nos 7 stands lus comme des
  **îlots multi-caisses** ; à documenter ainsi.
- `MEAL_PEAKS` / `MEAL_JOIN_PEAK = 0.30` : encadré par l'hypothèse 60-85 %
  par fenêtre de 2 h étalée sur 8 pas — *hypothèse de modélisation
  documentée*, ancrée ezCater/atVenu.
- File visible (étape 5.2 du plan) : signalétique réelle « 15-20 min
  d'attente » = référence pour l'échelle visuelle de la serpentine.

## 7. Sécurité & incidents

| Grandeur | Valeur réelle | Source |
|---|---|---|
| Ratio stewards/festivaliers | **1:250 minimum**, resserré à **1:100** si risque élevé ; le HSG195 impose une approche par analyse de risque, pas de formule ; règle australienne : 2 agents pour les 100 premiers + 1/100 supplémentaires | Green Guide via [guidance Lichfield DC](https://www.lichfielddc.gov.uk/street-trading-licences/event-management-plan/8) ; HSE, *Event Safety Guide* HSG195 §312-313 ([PDF](https://www.huntingdonshire.gov.uk/media/2746/hse-event-safety-guide.pdf)) ; Harris et al. 2015, NDLERF n°54 ([PDF](https://www.gkstill.com/Support/Links/Documents/crowd-controller-ratios.pdf)) |
| Délai signalement→décision | **aucune cible officielle chiffrée** n'existe ; référence d'échec documentée : Astroworld, ~38 min entre les premières demandes d'arrêt (21h11) et la fin du show ; ultimatum policier de 2 min à 22h08 | Texas Task Force on Concert Safety, rapport au gouverneur, avr. 2022 ([PDF officiel](https://gov.texas.gov/uploads/files/press/2022_report_texas_task_force_on_concert_safety.pdf)) ; [Houston Landing](https://www.houstonlanding.org/six-takeaways-from-the-houston-police-investigation-of-the-travis-scott-astroworld-concert/) (rapport HPD) |
| Vidéosurveillance humaine | surveillance ciblée moyenne 16,5 min ; incident détecté dans **46 %** des surveillances ciblées ; **69 %** seulement des détections remontées aux patrouilles | Piza & Moton 2023, *J. Criminal Justice* ([résumé](https://ericpiza.net/2023/05/09/cctv-sso/)) |
| Détection automatique (vision) | anomalie de foule à **≥ 40 fps** (« better than real-time ») — la latence système d'alerte n'est pas documentée académiquement | Marsden et al. 2016 ([arXiv:1606.05310](https://arxiv.org/abs/1606.05310)) |
| Doctrine bagarre / éjection | désescalade verbale d'abord, force en dernier recours, **prise d'escorte à DEUX agents** ; aucune durée type publiée | SIA (Home Office UK), [règles d'éjection & formation door supervisors](https://www.gov.uk/government/publications/sia-rules-and-training-about-ejecting-customers-from-the-premises/sia-rules-and-training-about-ejecting-customers-from-the-premises) |
| Containment surge / show-stop | « action immédiate » (annonces, artistes) + contrôles de conception (pens, fermeture des accès devant de scène) ; post-Astroworld : **déclencheurs de show-stop pré-négociés** + détenteur de l'autorité show-stop sur site ; **aucune cible « show-stop en X min » officielle** | HSE HSG195 §306-308 ; Texas Task Force 2022 (verbatim : « clearly outlined triggers for pausing or canceling … agreed upon … in advance ») |
| Incidents sécurité / 1000 pers. | arrestations : Glastonbury ~0,15-0,31/1000 ; Reading 2023 : 48 arrestations + 50 éjections policières / ~100 000 (~0,5/1000 chacun) — borne BASSE (les éjections par la sécurité privée ne sont pas publiées) | [Full Fact](https://fullfact.org/crime/notting-hill-carnival-glastonbury/) ; [Reading Today](https://rdg.today/reading-festival-arrests-slightly-up-from-last-year-but-remains-close-to-5-year-average/) (Thames Valley Police) |
| Intervenant en foule dense | pas d'étude dédiée — proxy : diagramme fondamental (§1) ; à 4+ p/m² un intervenant avance à **< ~30 % de sa vitesse libre** | Weidmann/Fruin (§1) ; Lohner et al. 2018, *Collective Dynamics* ([A13](https://collective-dynamics.eu/index.php/cod/article/view/A13)) |

**Application (`config.py`).**
- `FIGHT_CONTAIN_UNITS = 2` ✔ **sourcé** (doctrine SIA : escorte à deux
  agents ; désescalade d'abord).
- `FIGHT_DEESC_MIN = 3` / `FIGHT_CONTROL_MIN = 10` : **hypothèses de
  modélisation** (aucune durée publiée) — garder, marquer *illustratif* +
  sensibilité ±50 % (déjà prévue dans `docs/incident-model.md` §7).
- `RADIO_DELAY_MIN = 2` : **hypothèse ancrée** — pas de cible officielle ;
  l'ultimatum « 2 minutes » de la police à Astroworld et le « seconds
  matter » du rapport texan donnent l'ordre de grandeur d'une chaîne radio
  qui fonctionne ; l'échec documenté (38 min) borne le scénario SANS.
- `HUMAN_DISCOVERY_MIN = 4.5` (+ occlusion ∝ densité) : **hypothèse
  renforcée** par Piza & Moton — même un opérateur CCTV *ciblé* ne détecte
  que 46 % des incidents et n'en remonte que 69 % : la découverte humaine
  lente/incomplète du scénario SANS est réaliste, sinon optimiste.
- `CNN_LATENCY_MIN = 1.0` ✔ défendable : l'inférence tourne en
  temps réel (40 fps) ; la minute couvre la chaîne alerte→PC — borne
  conservatrice, à défaut de latence système publiée.
- `SURGE_CONTAIN_UNITS = 3`, `SURGE_CONTAIN_MIN = 5` : **hypothèses** (la
  doctrine réelle est qualitative : couper le flux entrant, ouvrir
  l'espace, show-stop) ; le KPI `t_containment` reproduit l'esprit des
  « show-stop triggers » du rapport texan.
- `RESOURCES["security"] = 12` équipes : à documenter comme **équipes
  mobiles d'intervention uniquement** — le socle de stewards fixes (1:250 →
  ~64-160 agents pour notre site) n'est pas simulé individuellement, il est
  implicite dans le modèle de découverte humaine. Une équipe = binôme SIA.
- Fréquence de bagarres simulée : à valider contre la borne basse réelle
  (~0,5 éjection/1000, sécurité privée non publiée → notre poignée de
  bagarres/jour pour 16-20 k est dans l'ordre de grandeur).

## 8. Corrections aux documents existants

1. **`docs/ab-demo.md`** cite « 73 % abandonnent > 5 min » : intraçable
   (marketing). Remplacer par Omnico 5 min 54 s + Waitwhile 2024 (80 % ≤ 15
   min) + tolérance festival 6-10 min (Ticket Fairy).
2. **`docs/incident-model.md`** : « MCE déclaré ~30 min après le début du
   set » → la chronologie officielle HPD donne **40 min entre le premier
   appel 911 (21h07) et la déclaration MCE (21h47)** ; `MCE_MIN` 30 → 40.
3. **`docs/ab-demo.md` / `config.py`** : « défib < 5 min — StatPearls/NIH » :
   la cible défib n'est **pas** dans StatPearls NBK597369 (vérifié) ; citer
   Resuscitation Council UK (3-5 min, −10 %/min) à la place. Les cibles BLS
   4 min / ALS 8 min, elles, y figurent bien.

## 9. Récapitulatif des changements `config.py`

| Paramètre | Actuel | Recommandé | Statut source |
|---|---|---|---|
| `METERS_PER_U` *(nouveau)* | — | 0.5 | calé sur Standon Calling CMP |
| `WALK_SPEED` | 90 u/min (arbitraire) | dérivé : 1,34 m/s → ~161 u/min | Weidmann 1993 |
| vitesse(densité) *(nouveau)* | — | formule de Kladek (γ=1,913, ρ_max=5,4) | Weidmann/Kretz |
| `TRAVEL` (mas.py) | matrice arbitraire | dérivée : longueur d'allée × `METERS_PER_U` / vitesse | géométrie + Weidmann |
| `GATE_CAP_STEP` | 560 | conservé (≙ 3-4 points d'entrée × 660/h) | Green Guide/SGSA |
| `NECK_EXIT_CAP_STEP` | 1550 | dérivé : 70 p/m/min × `EXIT_WIDTH_M`(=2 m) × 15 | SGSA + Standon |
| `RESPONSE_TARGET_MIN` | 8 | conservé (ALS) | StatPearls |
| `FIRST_AID_TARGET_MIN` *(nouveau)* | — | 4 (BLS) | StatPearls |
| `TREAT_MIN` | (5, 12) | **(8, 20)** | revue Healthcare 2022 |
| `MCE_MIN` | 30 | **40** | timeline officielle HPD |
| `FALL_DECAY` | 0.07 / 0.20 | conservés | AHA (std) ; dérivé Still (crush) |
| `MEAL_BASKET_EUR` | 12 | **14** | atVenu POS |
| `ABANDON_WAIT_MIN` | 8 | conservé, re-sourcé | Omnico/Waitwhile/TicketFairy |
| `SERVICE_MIN_PER_CUSTOMER` | 2.0 | conservé | Ticket Fairy SLA |
| `FIGHT_CONTAIN_UNITS` | 2 | conservé | doctrine SIA (binôme d'escorte) |
| `FIGHT_DEESC_MIN` / `FIGHT_CONTROL_MIN` | 3 / 10 | conservés | *hypothèse illustrative* (±50 %) |
| `RADIO_DELAY_MIN` | 2 | conservé | *hypothèse ancrée* (Astroworld : ultimatum 2 min ; échec = 38 min) |
| `HUMAN_DISCOVERY_MIN` | 4.5 | conservé | *hypothèse renforcée* (Piza & Moton : CCTV humain 46 %/69 %) |
| `CNN_LATENCY_MIN` | 1.0 | conservé | Marsden 2016 (40 fps) — borne conservatrice |
| `SURGE_CONTAIN_UNITS` / `SURGE_CONTAIN_MIN` | 3 / 5 | conservés | *hypothèse* (doctrine qualitative HSG195 + show-stop triggers Texas TF) |

Tout changement de valeur s'applique **pendant** les étapes du plan (pas en
vrac), avec re-exécution de `python simulation/kpis.py` et de
`run_demo.py` après chaque lot : les auto-vérifications AVEC/SANS doivent
rester vraies (l'analyse de sensibilité ±50 % couvre les paramètres marqués
*hypothèse* ou *dérivé d'expertise*).
