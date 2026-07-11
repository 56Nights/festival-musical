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


if __name__ == "__main__":
    from simulation.mas import TRAVEL, travel_time

    print("Calibration géométrie vs matrice TRAVEL du MAS")
    print(f"WALK_SPEED = {C.WALK_SPEED} u/min\n")
    print(f"{'paire':28s} {'long.(u)':>9s} {'TRAVEL(min)':>11s} "
          f"{'implicite':>10s} {'écart %':>8s}")
    ratios = []
    zones = C.ZONES
    for i in range(len(zones)):
        for j in range(i + 1, len(zones)):
            a, b = zones[i], zones[j]
            L = zone_travel_length(a, b)
            tmin = travel_time(a, b)
            implied = L / tmin                       # u/min qu'il faudrait
            dev = 100 * (L / C.WALK_SPEED - tmin) / tmin
            ratios.append(implied)
            print(f"{a+'-'+b:28s} {L:9.0f} {tmin:11.1f} "
                  f"{implied:10.1f} {dev:+8.0f}")
    best = sum(ratios) / len(ratios)
    print(f"\nVitesse de meilleur ajustement ~ {best:.0f} u/min "
          f"(config WALK_SPEED = {C.WALK_SPEED}).")
    print("Note : les durées des équipes suivent TRAVEL (autoritatif) ; la "
          "géométrie ne fixe que la position affichée. WALK_SPEED ne sert "
          "qu'aux points de foule.")
