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
    "Camping": 3000,
    "Entrance": 1500,
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

# ---------- Chemins ----------
import os
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs")
DATA_CSV = os.path.join(OUT, "attendance.csv")
EVENTS_CSV = os.path.join(OUT, "events.csv")
FORECAST_MODEL = os.path.join(OUT, "forecaster.pt")
VISION_MODEL = os.path.join(OUT, "vision_cnn.pt")
DASHBOARD_HTML = os.path.join(OUT, "dashboard.html")
