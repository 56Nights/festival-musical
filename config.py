"""Configuration centrale du système intelligent de gestion de festival."""

# ---------- Festival ----------
ZONES = ["MainStage", "SecondStage", "FoodCourt", "Camping", "Entrance"]
N_ZONES = len(ZONES)
FESTIVAL_DAYS = 3
HOURS_PER_DAY = 14          # 10h -> minuit
STEP_MINUTES = 15           # résolution temporelle
STEPS_PER_DAY = HOURS_PER_DAY * 60 // STEP_MINUTES
TOTAL_STEPS = FESTIVAL_DAYS * STEPS_PER_DAY

ZONE_CAPACITY = {
    "MainStage": 8000,
    "SecondStage": 4000,
    "FoodCourt": 2500,
    "Camping": 4000,        # terrain de camping (accueille les campeurs la nuit)
    "Entrance": 700,        # étroit : sature à l'affluence d'entrée ET à l'egress
}

# ---------- Ressources ----------
RESOURCES = {
    "medical": 4,    # équipes médicales — réduit pour créer de la tension
    "security": 12,  # équipes de sécurité
    "logistics": 8,  # équipes logistiques
}

MIN_STAFF_PER_ZONE = {          # contraintes dures (sécurité minimale)
    "medical": 0,
    "security": 1,
    "logistics": 0,
}

# ---------- Prévision (Transformer) ----------
SEQ_LEN = 24        # 6h d'historique (24 pas de 15 min)
HORIZON = 8         # prévision à 2h (8 pas)
D_MODEL = 64
N_HEADS = 4
N_LAYERS = 2
EPOCHS_FORECAST = 15
LR = 1e-3

# ---------- Vision (CNN multi-tâches) ----------
IMG_SIZE = 64
EPOCHS_VISION = 6
DENSITY_ALERT_THRESHOLD = 0.85   # % de capacité déclenchant une alerte

# ---------- Allocation dynamique ----------
RESOLVE_EVERY_STEPS = 2          # re-résolution périodique (30 min)
REASSIGNMENT_PENALTY = 3         # coût de changement d'affectation (stabilité)

# ---------- Dynamique de population (jour complet simulé) ----------
# Modèle inspiré d'études réelles de festivals :
#  - arrivées non-homogènes (processus de Poisson) ~ 50 % des visiteurs 16h-18h ;
#  - egress compressé après la tête d'affiche (choix de départ individuel) ;
#  - campeurs présents jour et nuit ; forte inertie de déplacement (les gens
#    campent autour d'une scène plutôt que de circuler sans cesse) ;
#  - goulots d'entrée/sortie (files d'attente aux portes).
# Le site part vide à 10h, se remplit progressivement, culmine à la tête
# d'affiche, puis se vide ; seuls les campeurs restent la nuit.
VISITOR_MIX = {                    # part de la population journalière par type
    "camper":    0.16,             # sur site dès l'ouverture, dorment au Camping
    "early":     0.26,             # familles / lève-tôt : arrivent tôt, repartent tôt
    "planner":   0.40,             # gros pic d'après-midi (début-milieu)
    "headliner": 0.18,             # arrivent ~90 min avant la tête d'affiche
}
PEAK_POPULATION = 16000            # population simultanée cible au pic (calibrage)
DAY_TURNOVER = 1.25                # visiteurs uniques / jour = pic x turnover
GATE_CAP_STEP = 560                # personnes admises / pas (goulot : sature l'Entrée tôt)
NECK_EXIT_CAP_STEP = 1550          # débit de SORTIE du col (< egress de pointe -> file)
EXIT_CAP_STEP = 1800               # personnes sorties / pas (egress plus rapide)
MOBILITY = {                       # fraction re-décidant sa zone / pas (inertie)
    "camper": 0.15, "early": 0.20, "planner": 0.20, "headliner": 0.08,
}
CHOICE_TEMP = 0.55                 # température du softmax de choix de zone
CROWD_AVERSION = 4.0               # évitement des zones proches de la saturation

# Programme des concerts (jour) : (zone, début_min, fin_min, popularité 0-1)
# minutes depuis l'ouverture (10h = 0 min ; minuit = 840 min).
# Les scènes alternent ; la popularité croît vers le soir ; la tête d'affiche
# ferme la journée et la SecondStage finit avant elle (egress étagé — pratique
# réelle de décalage 15-30 min des fins de scènes secondaires).
SCHEDULE = [
    ("SecondStage", 120, 165, 0.30),   # 12:00
    ("MainStage",   180, 240, 0.45),   # 13:00
    ("SecondStage", 255, 315, 0.50),   # 14:15
    ("MainStage",   330, 405, 0.60),   # 15:30
    ("SecondStage", 420, 480, 0.65),   # 17:00
    ("MainStage",   495, 570, 0.80),   # 18:15
    ("SecondStage", 585, 645, 0.70),   # 19:45 — finit avant la tête d'affiche
    ("MainStage",   660, 750, 1.00),   # 21:00 — TÊTE D'AFFICHE (fin 22:30)
]
HEADLINER_START_MIN = 660          # repère (dérivé de SCHEDULE) pour la boucle
HEADLINER_END_MIN = 750

# ---------- Démo A/B : gestion PRÉDICTIVE (avec) vs RÉACTIVE (sans) ----------
# Deux runs rejouent les MÊMES données (affluence, incidents) ; seule la GESTION
# change. « Avec » = pipeline complet (prévision -> pré-positionnement,
# vision -> détection ~1 min, CSP dynamique). « Sans » = plan d'équipes FIXE
# (proportionnel à la capacité, jamais réoptimisé) + détection HUMAINE (un
# agent doit voir l'incident puis le signaler par radio). On mesure l'écart.
#
# Sources des paramètres (voir docs/ab-demo.md) : cibles médicales de
# rassemblement de masse (BLS 4 min / ALS 8 min — StatPearls/NIH), ratios de
# stewards (Purple Guide ch. 13), SLA vendeur ~2 min/client et abandon de file
# ~8 min (Ticket Fairy / statistiques d'attente).
RESPONSE_TARGET_MIN = 8.0        # cible d'arrivée d'une équipe compétente (ALS)
MC_RUNS = 40                     # tirages Monte-Carlo (délais de découverte)

# -- détection d'un incident --
CNN_LATENCY_MIN = 1.0            # caméra + flux optique : quasi immédiat
RADIO_DELAY_MIN = 2.0           # humain : observation -> radio -> PC -> ordre
HUMAN_DISCOVERY_MIN = 4.5       # base du délai de DÉCOUVERTE humaine (Exp)
DISCOVERY_DENSITY_K = 2.2       # occlusion : une foule dense cache l'incident

# -- escalade : un incident non pris en charge à temps s'aggrave --
ESCALATION_MIN = {              # minutes sans prise en charge avant aggravation
    "fallen_person": 10.0,      # malaise piétiné -> mouvement de foule
    "crowd_surge": 12.0,        # bousculade non contenue -> chutes
    "suspicious_object": 20.0,  # objet non traité -> panique
}
ESCALATION_CHILD = {            # incident induit par l'aggravation
    "fallen_person": "crowd_surge",
    "crowd_surge": "fallen_person",
    "suspicious_object": "crowd_surge",
}
ESCALATION_DENSITY = 0.55       # n'escalade qu'en zone assez dense (réaliste)

# -- service FoodCourt : capacité PERMANENTE insuffisante aux pics -> une file
#    se forme TOUJOURS ; des équipes VOLANTES (réserve non affectée) doivent
#    intervenir pour la résorber. Enjeu mesuré : les déployer EN AVANCE grâce à
#    la prévision (avec) vs EN RÉACTION, une fois la file déjà formée (sans).
SERVICE_MIN_PER_CUSTOMER = 2.0  # débit d'un point de vente (SLA vendeur)
SERVICE_POINTS_PER_STAFF = 18   # chaque unité logistique arme un îlot de ~18 points
# capacité d'une unité logistique (permanente OU volante) par pas de 15 min
SERVICE_CAP_PER_STAFF = int(STEP_MINUTES / SERVICE_MIN_PER_CUSTOMER
                            * SERVICE_POINTS_PER_STAFF)   # 7.5 * 18 = 135
FC_PERMANENT_STAFF = 2          # vendeurs permanents (base insuffisante au pic)
RESERVE_LOGISTICS = 3           # équipes logistiques VOLANTES (réserve mobilisable)
RESERVE_LEAD_MIN = 45           # avec : anticipation (pré-déployées avant le pic)
RESERVE_TRIGGER_WAIT_MIN = 5.0  # sans : attente déclenchant l'appel de renfort
RESERVE_MOBILIZE_STEPS = 2      # sans : délai d'arrivée du renfort (appel + trajet, 30 min)
MEAL_BASKET_EUR = 12.0          # panier moyen -> CA perdu par client parti
ABANDON_WAIT_MIN = 8.0          # au-delà de cette attente, le client quitte la file
MEAL_JOIN_PEAK = 0.30           # part des présents FoodCourt rejoignant la file au pic
MEAL_JOIN_BASE = 0.015          # appétit de fond hors pic
MEAL_PEAKS = [                  # pics d'appétit (min depuis 10h, largeur, intensité)
    (150.0, 55.0, 0.85),        # déjeuner ~12h30
    (600.0, 75.0, 1.0),         # dîner ~20h (avant la tête d'affiche)
]

# ---------- Modèle d'incidents v2 : cycles de vie, chaînes, chaîne de survie --
# Fondé sur la littérature des vrais festivals (cf. docs/incident-model.md) :
# densité critique ~6-7 pers/m² (proxy 0,85 de capacité) ; effondrement
# progressif (surge -> chutes crush en cascade) ; Astroworld (surge non contenu
# ~30 min -> mass casualty) ; asphyxie compressive (issue <1 % après ~4 min) ;
# chaîne de secours à deux étages (premiers gestes par staff formé, puis médic).
SURGE_DENSITY = 0.85            # densité entretenant un mouvement de foule
SURGE_GROWTH = 0.15            # intensité +0,15/min tant que dense et non contenu
SURGE_CHAIN_K = 0.055          # chutes crush induites/min = K · densité · intensité
SURGE_CONTAIN_UNITS = 3        # équipes SÉCURITÉ pour contenir un surge
SURGE_CONTAIN_MIN = 5.0        # durée de mise en sécurité une fois sur place
MCE_MIN = 30.0                 # surge non contenu 30 min -> MASS CASUALTY EVENT
MCE_CRUSH_BURST = 5            # rafale de chutes crush au déclenchement du MCE

FIGHT_GROWTH = 1.30            # intensité ×1,30/min (badauds aspirés)
FIGHT_GROWTH_DENSITY = 0.50    # les bagarres n'enflent qu'en zone assez dense
FIGHT_INJURY_K = 0.06          # P(blessé/min) = K · intensité
FIGHT_CONTAIN_UNITS = 2        # binôme de sécurité (doctrine réelle)
FIGHT_EARLY_INTENSITY = 3.0    # seuil « intervention précoce » (désescalade)
FIGHT_DEESC_MIN = 3.0          # containment si intervention précoce (I < seuil)
FIGHT_CONTROL_MIN = 10.0       # containment si intervention tardive (I ≥ seuil)
FIGHT_MAX_INTENSITY = 12.0     # borne d'intensité

# chaîne de survie des chutes : l'issue (∈[0,1], 1 = indemne) se dégrade jusqu'aux
# PREMIERS GESTES (n'importe quel staff formé, sécurité compris) qui la GÈLENT,
# puis le MÉDIC résout. Deux classes de gravité.
FALL_DECAY = {"standard": 0.07, "crush": 0.20}   # perte d'issue / min
FALL_CRUSH_DENSITY = 0.75      # une chute en zone ≥ 0,75 est de classe « crush »
FIRST_AID_HOLD_MIN = 4.0       # le secouriste reste ~4 min (stabilise, relève)
INDUCED_DETECT_MIN = 1.0       # incident induit = vu tout de suite (staff sur place)

# ---------- Visualisation / carte du site ----------
# La « vue simulation » rejoue spatialement ce que la boucle de contrôle a
# décidé (attendance.csv + events.csv + control_log.json). Ce n'est PAS un
# second simulateur : c'est un jumeau numérique animé des mêmes faits.
MAP_W, MAP_H = 1000, 700          # unités de carte (u)
WALK_SPEED = 90.0                 # u / min — meilleur ajustement sur TRAVEL (cf. geometry.py)
FRAMES_PER_STEP = 15              # 1 frame = 1 minute simulée -> 15 par pas de 15 min
MAX_DOTS = 800                    # plafond de points de foule affichés (1 point ≙ K pers.)

# ---------- Chemins ----------
import os
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs")
DATA_CSV = os.path.join(OUT, "attendance.csv")
FLOW_CSV = os.path.join(OUT, "flow.csv")
EVENTS_CSV = os.path.join(OUT, "events.csv")
FORECAST_MODEL = os.path.join(OUT, "forecaster.pt")
VISION_MODEL = os.path.join(OUT, "vision_cnn.pt")
DASHBOARD_HTML = os.path.join(OUT, "dashboard.html")
REPLAY_JSON = os.path.join(OUT, "replay.json")
FESTIVAL_MAP_HTML = os.path.join(OUT, "festival_map.html")
