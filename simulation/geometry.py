"""
Géométrie du site — plan 2D vue de dessus pour la « vue simulation ».

Ce module ne contient AUCUNE logique de simulation : uniquement le plan du
site (polygones des zones, allées de circulation) et des utilitaires
géométriques (point aléatoire dans une zone, longueur d'un chemin,
interpolation le long d'un chemin).

Séparation des responsabilités importante :
- les DURÉES de trajet des équipes restent gouvernées par la matrice TRAVEL
  du MAS (`simulation/mas.py`) — elle reste la source de vérité pour les KPIs ;
- la géométrie ne gouverne QUE la POSITION affichée d'un agent pendant son
  trajet (fraction du chemin parcourue). Les deux ne peuvent donc pas se
  contredire : on étire le chemin sur la durée imposée par TRAVEL.

`WALK_SPEED` (config) ne sert qu'aux points de foule, qui n'ont pas d'entrée
dans TRAVEL. Le bloc __main__ imprime la calibration vitesse implicite vs
TRAVEL, à titre indicatif.
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as C

# ---------------------------------------------------------------------------
# Diagramme fondamental piéton (Weidmann/Kladek) — vitesse en fonction de la
# densité locale (pers/m²). v(ρ)/v_libre = 1 − exp(−γ(1/ρ − 1/ρ_max)).
# Sert à ralentir les points de foule dans les zones denses (ruée pré-headliner).
# Source : Weidmann 1993, via Kretz arXiv:0901.0170. cf. docs/calibration-*.md.
# ---------------------------------------------------------------------------
def crowd_speed_factor(ppsm):
    """Facteur de vitesse ∈ (0,1] à la densité `ppsm` (pers/m²)."""
    if ppsm <= 0.05:
        return 1.0
    if ppsm >= C.JAM_DENSITY_PPSM:
        return 0.05
    f = 1.0 - math.exp(-C.FD_GAMMA * (1.0 / ppsm - 1.0 / C.JAM_DENSITY_PPSM))
    return max(0.05, min(1.0, f))

# Densité LOCALE au pic (pers/m²) supposée quand une zone est à `density = 1`.
# Nos capacités sont « confortables » (~0,5 pers/m² en moyenne de zone) ; la foule
# se concentre au point focal (devant de scène) où la densité réelle est bien plus
# forte — 3-4 pers/m² devant scène vs 2 à l'arrière (Standon Calling CMP). On mappe
# donc density→ppsm local par ce facteur pour un ralentissement réaliste au pic.
PEAK_LOCAL_PPSM = {"MainStage": 4.0, "SecondStage": 4.0,
                   "FoodCourt": 2.5, "Camping": 1.0, "Entrance": 3.0}

# ---------------------------------------------------------------------------
# Polygones des zones (vue de dessus, repère x->droite, y->bas, unités « u »).
# Disposition : Entrée en bas (arrivée), MainStage en haut au centre (grande),
# SecondStage à gauche, FoodCourt au centre, Camping à droite.
# ---------------------------------------------------------------------------
# L'Entrée est un SABLIER : bulbe intérieur (côté site) + col étroit (la porte)
# + bulbe extérieur (côté ville). Le col force le goulot d'étranglement — on
# voit la foule s'entasser dans le bulbe extérieur à l'ouverture (tout le monde
# entre) et dans le bulbe intérieur à la fermeture (tout le monde sort).
ZONE_SHAPES = {
    "MainStage":   [(300, 40),  (700, 40),  (720, 180), (280, 180)],
    "SecondStage": [(40, 220),  (240, 220), (240, 430), (40, 430)],
    "FoodCourt":   [(400, 250), (620, 250), (620, 430), (400, 430)],
    "Camping":     [(785, 275), (955, 275), (955, 470), (785, 470)],
    "Entrance":    [(388, 538), (632, 538), (562, 610),
                    (648, 698), (372, 698), (458, 610)],   # sablier (col large)
}

# Couleur d'identité de chaque zone (teinte des points de foule + légende).
# Palette catégorielle validée (CVD-safe, cf. skill dataviz) — ordre des slots
# = mécanisme de sécurité daltonisme. Variantes clair / sombre.
ZONE_COLORS = {
    "MainStage":   {"light": "#2a78d6", "dark": "#3987e5"},   # bleu
    "SecondStage": {"light": "#1baf7a", "dark": "#199e70"},   # aqua
    "FoodCourt":   {"light": "#eda100", "dark": "#c98500"},   # jaune
    "Camping":     {"light": "#008300", "dark": "#008300"},   # vert
    "Entrance":    {"light": "#4a3aa7", "dark": "#9085e9"},   # violet
}


def polygon_centroid(poly):
    """Centroïde géométrique (formule de l'aire signée)."""
    a = 0.0
    cx = 0.0
    cy = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-9:                       # dégénéré -> moyenne des sommets
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    return (cx / (6 * a), cy / (6 * a))


ZONE_CENTER = {z: polygon_centroid(p) for z, p in ZONE_SHAPES.items()}


def polygon_area(poly):
    """Aire du polygone (formule du lacet, valeur absolue), en u²."""
    a = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return abs(a) * 0.5


# aires (u² et m²) et densité locale au pic (pers/m²) par zone — sert à la
# calibration (contrôle p/m² vs seuils réels) et au ralentissement de la foule.
ZONE_AREA_U2 = {z: polygon_area(p) for z, p in ZONE_SHAPES.items()}
ZONE_AREA_M2 = {z: ZONE_AREA_U2[z] * C.METERS_PER_U ** 2 for z in ZONE_SHAPES}


def _bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


ZONE_BBOX = {z: _bbox(p) for z, p in ZONE_SHAPES.items()}


def point_in_poly(x, y, poly):
    """Ray casting — vrai si (x, y) est à l'intérieur du polygone."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def random_in_poly(poly, rng, margin=8.0):
    """Point aléatoire uniforme dans un polygone quelconque (rejet sur bbox)."""
    x0, y0, x1, y1 = _bbox(poly)
    x0 += margin; y0 += margin; x1 -= margin; y1 -= margin
    for _ in range(60):
        x = rng.uniform(x0, x1)
        y = rng.uniform(y0, y1)
        if point_in_poly(x, y, poly):
            return (x, y)
    return polygon_centroid(poly)           # repli : centre


def random_point_in(zone, rng, margin=8.0):
    """Point aléatoire uniforme dans une zone."""
    return random_in_poly(ZONE_SHAPES[zone], rng, margin)


# ---------------------------------------------------------------------------
# Porte (col du sablier) et deux bulbes de congestion :
#  - bulbe EXTÉRIEUR (bas)   : file d'arrivée (matin / ruée pré-headliner) ;
#  - bulbe INTÉRIEUR (haut)  : embouteillage de sortie (egress de fin de soirée).
# Tout le flux passe par le col ; la foule bloquée s'entasse dans les bulbes.
# ---------------------------------------------------------------------------
GATE_POINT = (510.0, 610.0)                 # col du sablier (la porte, large)
NECK_HALF = 52.0                            # demi-largeur du col (passage)
# bulbes triangulaires (les « balles » s'y entassent et s'écoulent vers le col)
ENT_BOT = dict(apex_y=612.0, base_y=697.0, hw=137.0)   # entrée (sous le col)
ENT_TOP = dict(apex_y=608.0, base_y=540.0, hw=122.0)   # sortie (au-dessus)


def bulb_clamp(x, y, bulb):
    """Contraint (x, y) dans le triangle du bulbe (paroi en entonnoir)."""
    ay, by, hw = bulb["apex_y"], bulb["base_y"], bulb["hw"]
    span = by - ay
    y = min(max(y, min(ay, by) + 1), max(ay, by) - 1)
    frac = abs(y - ay) / abs(span) if span else 0.0
    half = max(NECK_HALF * 0.5, hw * frac)      # largeur autorisée à cette hauteur
    x = min(max(x, 510.0 - half), 510.0 + half)
    return x, y


# ---------------------------------------------------------------------------
# Allées de circulation : polyligne de points de passage entre chaque paire de
# zones. Les coudes contournent les scènes/zones pour un rendu crédible.
# Stockées dans un ordre canonique ; `path_between` réoriente au besoin.
# ---------------------------------------------------------------------------
def _c(z):
    return ZONE_CENTER[z]


_PATHS = {
    frozenset({"MainStage", "SecondStage"}):  [_c("MainStage"), (200, 200), _c("SecondStage")],
    frozenset({"MainStage", "FoodCourt"}):    [_c("MainStage"), (510, 220), _c("FoodCourt")],
    frozenset({"MainStage", "Camping"}):      [_c("MainStage"), (720, 150), _c("Camping")],
    frozenset({"MainStage", "Entrance"}):     [_c("MainStage"), (690, 210), (690, 480), _c("Entrance")],
    frozenset({"SecondStage", "FoodCourt"}):  [_c("SecondStage"), (330, 340), _c("FoodCourt")],
    frozenset({"SecondStage", "Camping"}):    [_c("SecondStage"), (500, 490), _c("Camping")],
    frozenset({"SecondStage", "Entrance"}):   [_c("SecondStage"), (320, 490), _c("Entrance")],
    frozenset({"FoodCourt", "Camping"}):      [_c("FoodCourt"), (690, 340), _c("Camping")],
    frozenset({"FoodCourt", "Entrance"}):     [_c("FoodCourt"), (510, 490), _c("Entrance")],
    frozenset({"Camping", "Entrance"}):       [_c("Camping"), (690, 490), _c("Entrance")],
}


def path_between(a, b):
    """Polyligne orientée de a vers b (liste de points, a inclus, b inclus)."""
    if a == b:
        return [ZONE_CENTER[a], ZONE_CENTER[a]]
    pts = _PATHS[frozenset({a, b})]
    # ordre canonique = premier point le plus proche du centre de a ?
    if _dist(pts[0], ZONE_CENTER[a]) <= _dist(pts[-1], ZONE_CENTER[a]):
        return list(pts)
    return list(reversed(pts))


def _dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def path_length(path):
    return sum(_dist(path[i], path[i + 1]) for i in range(len(path) - 1))


def position_along(path, fraction):
    """Point à `fraction` (0..1) de la longueur d'arc de la polyligne."""
    fraction = min(max(fraction, 0.0), 1.0)
    total = path_length(path)
    if total < 1e-9:
        return path[0]
    target = fraction * total
    acc = 0.0
    for i in range(len(path) - 1):
        seg = _dist(path[i], path[i + 1])
        if acc + seg >= target:
            t = (target - acc) / seg if seg > 1e-9 else 0.0
            x = path[i][0] + t * (path[i + 1][0] - path[i][0])
            y = path[i][1] + t * (path[i + 1][1] - path[i][1])
            return (x, y)
        acc += seg
    return path[-1]


def zone_travel_length(a, b):
    return path_length(path_between(a, b))


# ---------------------------------------------------------------------------
# Postes de staff par zone — points de stationnement par défaut, ordonnés du
# PLUS optimal au MOINS optimal (le CSP alloue des COMPTES par zone ; un mapping
# déterministe place la k-ième unité d'une zone au k-ième poste). Choix inspirés
# de la doctrine réelle : crash-barrier gauche/droite + régie devant les scènes,
# centre puis extrémités des rangées au FoodCourt, col + guichets à l'Entrée.
# ---------------------------------------------------------------------------
def _staff_posts(zone):
    x0, y0, x1, y1 = ZONE_BBOX[zone]
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    if zone in ("MainStage", "SecondStage"):
        fy = y0 + (y1 - y0) * 0.30                    # ligne de crash-barrier
        return [(cx, fy),                             # centre devant scène (optimal)
                (x0 + (x1 - x0) * 0.22, fy),          # barrière gauche
                (x1 - (x1 - x0) * 0.22, fy),          # barrière droite
                (cx, cy),                             # milieu de fosse
                (cx, y1 - 10)]                        # arrière (moins optimal)
    if zone == "FoodCourt":
        return [(cx, cy), (x0 + 14, cy), (x1 - 14, cy), (cx, y0 + 12)]
    if zone == "Camping":
        return [(cx, cy), (x0 + 18, y0 + 18), (x1 - 18, y0 + 18),
                (x0 + 18, y1 - 16), (x1 - 18, y1 - 16)]
    return [GATE_POINT, (447, 652), (573, 652), (cx, cy)]   # Entrance : col + guichets


STAFF_POSTS = {z: _staff_posts(z) for z in C.ZONES}


# ---------------------------------------------------------------------------
# Stands de restauration (fenêtres de service) — positions ALIGNÉES sur celles
# dessinées par le lecteur (`drawFoodStalls` : rangée avant à fx ∈ {0.16, 0.38,
# 0.62, 0.84} du bbox FoodCourt). Les festivaliers qui font la queue s'alignent
# en files serpentines DEVANT ces fenêtres (cf. replay_sim `_food_queue`).
# ---------------------------------------------------------------------------
def _food_stalls():
    x0, y0, x1, y1 = ZONE_BBOX["FoodCourt"]
    return [(x0 + (x1 - x0) * fx, y0 + 10.0) for fx in (0.16, 0.38, 0.62, 0.84)]


FOOD_STALLS = _food_stalls()


def food_queue_slots(n, row_gap=12.0, head_dy=22.0):
    """Emplacements de file (serpentine) devant les stands : une allée par stand
    (rangée avant), la tête de file au plus près de la fenêtre, la queue qui
    descend vers la plaza. Retourne les `n` premiers créneaux (tête d'abord)."""
    x0, y0, x1, y1 = ZONE_BBOX["FoodCourt"]
    lanes = [sx for sx, _ in FOOD_STALLS]
    y_head = FOOD_STALLS[0][1] + head_dy
    y_max = y1 - 12.0
    slots, row = [], 0
    while len(slots) < n:
        y = y_head + row * row_gap
        if y > y_max:
            break
        for lx in lanes:
            slots.append((lx, y))
            if len(slots) >= n:
                break
        row += 1
    return slots


def _intra_zone_min(zone):
    """Temps moyen de déplacement DANS une zone (poste optimal -> incident),
    dérivé de la taille de zone et de la vitesse d'intervention. Même au sein
    d'un stage, rejoindre un incident prend du temps (≥ 0,5 min)."""
    x0, y0, x1, y1 = ZONE_BBOX[zone]
    diag_u = math.hypot(x1 - x0, y1 - y0)
    mean_dist_m = 0.35 * diag_u * C.METERS_PER_U       # distance moyenne poste->point
    minutes = mean_dist_m / (C.RESPONDER_SPEED_MPS * 60.0)
    return max(0.5, round(minutes * 2) / 2)            # arrondi à 0,5 min


INTRA_ZONE_MIN = {z: _intra_zone_min(z) for z in C.ZONES}


def travel_minutes(a, b):
    """Durée de trajet d'une équipe (min), DÉRIVÉE de la géométrie : longueur
    d'allée × échelle ÷ vitesse d'intervention. Intra-zone = INTRA_ZONE_MIN.
    C'est désormais la source de vérité des durées (mas.TRAVEL en dépend)."""
    if a == b:
        return INTRA_ZONE_MIN.get(a, 1.0)
    metres = zone_travel_length(a, b) * C.METERS_PER_U
    minutes = metres / (C.RESPONDER_SPEED_MPS * 60.0)
    return max(0.5, round(minutes * 2) / 2)            # arrondi à 0,5 min


if __name__ == "__main__":
    from simulation.mas import travel_time

    # --- 1. échelle physique + densité réelle par zone (calibration Standon) ---
    print(f"Échelle : 1 u = {C.METERS_PER_U} m  ->  site "
          f"{C.MAP_W * C.METERS_PER_U:.0f} × {C.MAP_H * C.METERS_PER_U:.0f} m "
          f"({C.MAP_W * C.MAP_H * C.METERS_PER_U ** 2 / 1e4:.1f} ha)")
    print(f"Vitesses : foule {C.WALK_SPEED_MPS} m/s ({C.WALK_SPEED:.0f} u/min) · "
          f"staff {C.RESPONDER_SPEED_MPS} m/s\n")
    print(f"{'zone':12s} {'aire (m²)':>10s} {'capacité':>9s} "
          f"{'p/m² moyen':>11s} {'p/m² focal':>11s}")
    for z in C.ZONES:
        a_m2 = ZONE_AREA_M2[z]
        avg = C.ZONE_CAPACITY[z] / a_m2
        print(f"{z:12s} {a_m2:10.0f} {C.ZONE_CAPACITY[z]:9d} "
              f"{avg:11.2f} {PEAK_LOCAL_PPSM[z]:11.1f}")
    print("  (réf. Standon Calling : arène main stage 15 357 m², 3-4 p/m² devant "
          "scène ; seuils réels : confort 2, danger 5-6, turbulence 6-7+ p/m²)\n")

    # --- 2. durées de trajet dérivées de la géométrie (source de vérité) ---
    print("Trajets équipe (dérivés de la géométrie, arrondis 0,5 min) :")
    print(f"{'paire':28s} {'long.(u)':>9s} {'long.(m)':>9s} {'trajet(min)':>11s}")
    zones = C.ZONES
    durations = []
    for i in range(len(zones)):
        for j in range(i + 1, len(zones)):
            a, b = zones[i], zones[j]
            L = zone_travel_length(a, b)
            tmin = travel_time(a, b)
            durations.append(tmin)
            print(f"{a+'-'+b:28s} {L:9.0f} {L*C.METERS_PER_U:9.0f} {tmin:11.1f}")
    print(f"\nIntra-zone : "
          + " · ".join(f"{z} {INTRA_ZONE_MIN[z]:.1f}" for z in C.ZONES) + " min")
    # contrôle de cohérence : des durées plausibles pour un site de ~17 ha
    assert all(0.5 <= d <= 12 for d in durations), \
        "durées de trajet hors plage plausible [0,5 ; 12] min"
    assert all(0.5 <= INTRA_ZONE_MIN[z] <= 6 for z in C.ZONES), \
        "temps intra-zone hors plage plausible"
    print("\nOK — durées dans la plage plausible ; la géométrie est la source de "
          "vérité (mas.TRAVEL et la vue simulation en dérivent).")
