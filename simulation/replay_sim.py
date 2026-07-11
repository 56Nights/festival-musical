"""
Ré-enactment spatial du festival — « jumeau numérique » animé.

Ce module NE simule PAS un nouveau festival : il REJOUE spatialement les faits
déjà produits par le pipeline —
    attendance.csv     (affluence par zone / pas de 15 min)
    flow.csv           (population sur site, admissions, départs, file d'attente)
    events.csv         (incidents réels injectés)
    control_log.json   (alertes CNN, déclencheurs, allocations CSP par pas)
— en leur donnant une position et un mouvement sur le plan du site.

La foule est désormais DYNAMIQUE : le site part vide le matin, se remplit
progressivement (points qui entrent par la porte), sature à la tête d'affiche,
puis se vide (points qui sortent par la porte) ; seuls les campeurs restent la
nuit. 1 point ≙ K personnes (K = population au pic / MAX_DOTS).

Une seule source de vérité : ce qu'on voit à l'écran EST ce que la boucle de
contrôle a décidé. La logique de réponse aux incidents reprend fidèlement
`simulation/mas.py` ; les DURÉES de trajet des équipes suivent la matrice
TRAVEL (autoritative pour les KPIs).

Sortie : outputs/replay.json — état du monde image par image (1 image = 1 min).

Exécution autonome (auto-vérification) :
    python simulation/replay_sim.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import Counter
import numpy as np
import pandas as pd

import config as C
from simulation import geometry as G
from simulation.mas import travel_time
from allocation.dynamic_csp import SEVERITY

rng = np.random.default_rng(2027)

RES_TYPES = ["medical", "security", "logistics"]
RES_IDX = {r: i for i, r in enumerate(RES_TYPES)}
INC_STATE = {"pending": 0, "responding": 1, "treating": 2,
             "resolved": 3, "uncovered": 4}
# état d'un point de foule (encodé pour le lecteur : file/entrant/actif/sortant)
# état d'un point : entassé au col (q_in/q_out), en chemin vers une zone
# (moving), posé (idle), vers la sortie (leaving), ou rejoignant le bulbe de
# sortie (to_out). Les q_* s'écoulent par PHYSIQUE GRANULAIRE (sablier de balles).
DOT_STATE = {"q_in": 0, "moving": 1, "idle": 2, "leaving": 3,
             "q_out": 4, "to_out": 5}
# état d'une équipe (perimeter = cordon de sécurité autour d'une bagarre)
RESP_STATE = {"idle": 0, "relocating": 1, "responding": 2, "busy": 3,
              "perimeter": 4}
# types d'incident (index stable pour le lecteur -> pictogramme dédié)
INC_TYPES = ["fallen_person", "crowd_surge", "suspicious_object", "fight"]
INC_TYPE_IDX = {t: i for i, t in enumerate(INC_TYPES)}

# écoulement granulaire au col (« balles dans un sablier »)
FUNNEL_R = 6.2           # rayon d'un point (répulsion) -> les points s'empilent
FUNNEL_ATTRACT = 2.3     # attraction vers le col (u/frame)
FUNNEL_REPULSE = 0.55    # force de répulsion (empêche le chevauchement)

# --- foule qui se TASSE avec la densité (double encodage visuel) ------------
# La position « posée » d'un point est tirée à un rayon r = R·u^γ(d) autour d'un
# point focal de la zone. γ croît avec la densité -> à forte affluence tout le
# monde se resserre contre le focal (devant de scène) ; à faible affluence la
# foule est un semis lâche. Chaque point garde un rang `u` et un angle fixes :
# seul le rayon se contracte quand la zone se remplit -> compaction FLUIDE.
PACK_GAMMA_LO = 0.72     # exposant à densité faible (semis large)
PACK_GAMMA_HI = 2.9      # exposant à densité forte (masse compacte)
PACK_GLIDE = 0.16        # fraction rattrapée vers la cible de repos / frame
PACK_RELAX_ITERS = 3     # itérations de répulsion des cibles de repos / pas
PACK_MIN_SEP = 9.0       # séparation minimale visée entre points posés (u)

# réaction de la foule aux incidents (le « trou » qui s'ouvre) --------------
SURGE_WAVE_LEN = 9       # frames d'onde de choc après une bagarre
SURGE_WAVE_R = 120.0     # portée de l'onde (u)
SURGE_WAVE_PUSH = 26.0   # impulsion radiale au centre (u, décroît en temps/dist)
CLEAR_R = {"crowd_surge": 78.0, "fallen_person": 34.0,
           "suspicious_object": 46.0}   # clairière maintenue tant qu'actif

# zones où les gens séjournent (l'Entrée n'est que transit)
ACT_ZONES = ["MainStage", "SecondStage", "FoodCourt", "Camping"]
ENT_IDX = C.ZONES.index("Entrance")

# point focal de rassemblement par zone (devant de scène pour les scènes ;
# centre pour FoodCourt ; le Camping reste dispersé — des tentes).
def _focal(zone):
    x0, y0, x1, y1 = G.ZONE_BBOX[zone]
    cx = (x0 + x1) / 2.0
    if zone in ("MainStage", "SecondStage"):
        return (cx, y0 + (y1 - y0) * 0.34)      # devant de scène (haut de zone)
    return (cx, (y0 + y1) / 2.0)                 # centre

FOCAL = {z: _focal(z) for z in ACT_ZONES}
# rayon de dispersion max + « aplatissement » (le Camping reste très étalé)
PACK_RMAX = {z: 0.62 * ((G.ZONE_BBOX[z][2] - G.ZONE_BBOX[z][0]) ** 2
                        + (G.ZONE_BBOX[z][3] - G.ZONE_BBOX[z][1]) ** 2) ** 0.5
             for z in ACT_ZONES}
PACK_GAMMA_ZONE = {"MainStage": 1.0, "SecondStage": 1.0,
                   "FoodCourt": 0.85, "Camping": 0.45}   # facteur sur γ_hi

BOTTOM_EXIT = (510.0, 690.0)     # bas du sablier (extérieur) : arrivées / sorties


def _zidx(name):
    return C.ZONES.index(name) if name in C.ZONES else ENT_IDX

RESOLVED_LINGER = 6      # frames pendant lesquelles un incident résolu reste affiché
ABANDON_MIN = 30         # abandon après 30 min sans prise en charge (cf. mas.py)


def _clock(step, minute_in_step=0):
    sid = step % C.STEPS_PER_DAY
    total_min = sid * C.STEP_MINUTES + minute_in_step
    h = 10 + total_min // 60
    m = total_min % 60
    return f"{int(h):02d}:{int(m):02d}"


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
class Dot:
    """Un point de foule (1 point ≙ K personnes ; pas un individu suivi).

    `id` stable : le lecteur interpole les positions d'une image à l'autre en
    appariant les points par identifiant (la liste est dynamique — les points
    apparaissent à la porte et disparaissent en sortant).
    """
    __slots__ = ("id", "zone", "oz", "x", "y", "state", "path", "t0", "dur",
                 "dead", "sx", "sy", "u", "ang", "rx", "ry")

    def __init__(self, did, zone, x, y, state="idle"):
        self.id = did
        self.zone = zone            # zone de destination (activité) ou None
        self.oz = ENT_IDX           # index de la zone d'ORIGINE (dégradé de couleur)
        self.x = x
        self.y = y
        self.state = state          # q_in | moving | idle | leaving | q_out
        self.path = None
        self.t0 = 0
        self.dur = 0.0
        self.dead = False           # marqué pour retrait (sorti du site)
        self.sx = x                 # emplacement cible dans la file (queue slot)
        self.sy = y
        # --- tassement : rang radial + angle FIXES ; seul le rayon se contracte
        self.u = 0.0                # rang dans [0,1] (place dans la foule)
        self.ang = 0.0              # angle autour du focal (fixe)
        self.rx = x                 # cible de repos courante (glissement doux)
        self.ry = y


class Responder:
    __slots__ = ("id", "rtype", "home", "x", "y", "state",
                 "path", "t0", "dur", "dest", "incident", "busy_until",
                 "escort")

    def __init__(self, uid, rtype, home, x, y):
        self.id = uid
        self.rtype = rtype
        self.home = home            # poste assigné (issu de l'allocation CSP)
        self.x = x
        self.y = y
        self.state = "idle"
        self.path = None
        self.t0 = 0
        self.dur = 0.0
        self.dest = (x, y)          # point de destination courant
        self.incident = None
        self.busy_until = 0
        self.escort = None          # incident encadré (cordon sécurité), sinon None


class Incident:
    __slots__ = ("id", "zone", "x", "y", "sev", "state", "spawn", "detected",
                 "dispatch_zone", "best_t", "unit", "resolved_at",
                 "itype", "treat_start", "treat_end", "parent")

    def __init__(self, iid, zone, x, y, sev, spawn, detected,
                 itype="fallen_person", parent=-1):
        self.id = iid
        self.zone = zone
        self.x = x
        self.y = y
        self.sev = sev
        self.state = "pending"
        self.spawn = spawn
        self.detected = detected
        self.itype = itype          # fallen_person | crowd_surge | fight | object
        self.parent = parent        # id de l'incident parent (chaîne) ou -1
        self.dispatch_zone = None
        self.best_t = 1.0
        self.unit = None
        self.treat_start = None     # frame de début de prise en charge (arc)
        self.treat_end = None       # frame de fin de prise en charge (arc)
        self.resolved_at = None


# ---------------------------------------------------------------------------
# Moteur
# ---------------------------------------------------------------------------
class ReplayEngine:
    def __init__(self, df, log, flow):
        self.log = log
        self.steps = [e["step"] for e in log]
        self.n_steps = len(log)
        self.frames_per_step = C.FRAMES_PER_STEP
        self.n_frames = self.n_steps * self.frames_per_step

        need_steps = set(self.steps) | {self.steps[-1] + 1}
        sub = df[df["step"].isin(need_steps)]
        self.att = {(int(r.step), r.zone): float(r.attendance)
                    for r in sub.itertuples()}
        self.cap = C.ZONE_CAPACITY

        # flux (population sur site, file, admissions, départs) par pas
        self.onsite = {int(r.step): float(r.onsite) for r in flow.itertuples()}
        self.queue = {int(r.step): float(r.queue) for r in flow.itertuples()}
        self.admit = {int(r.step): float(r.admitted) for r in flow.itertuples()}
        self.depart = {int(r.step): float(r.departed) for r in flow.itertuples()}
        self.arrived = {int(r.step): float(r.arrived) for r in flow.itertuples()}

        # échelle : 1 point ≙ K personnes (borne le nombre de points affichés)
        peak = max((self.onsite.get(s, 0.0) for s in self.steps), default=1.0)
        self.scale = max(1.0, np.ceil(peak / C.MAX_DOTS))

        self.init_alloc = next((e["allocation"] for e in log
                                if e.get("allocation")), None)

        self.dots = []
        self.responders = []
        self.incidents = []
        self._next_inc_id = 0
        self._next_dot_id = 0
        self._pending = []            # mouvements étalés sur le pas
        self.wait_in = []             # FILE d'entrée au col (avant = index 0, au col)
        self.wait_out = []            # FILE de sortie au col
        self.response_times = []

    def _mk_dot(self, zone, x, y, state):
        d = Dot(self._next_dot_id, zone, x, y, state)
        d.oz = _zidx(zone)
        d.u = float(rng.uniform(0.0, 1.0))          # rang radial dans la foule
        d.ang = float(rng.uniform(0.0, 2 * np.pi))  # secteur (fixe)
        d.rx, d.ry = x, y
        self._next_dot_id += 1
        self.dots.append(d)
        return d

    # ---- helpers ----
    def _att(self, step, zone):
        return self.att.get((step, zone), self.att.get((self.steps[-1], zone), 0.0))

    def density(self, step, zone):
        return self._att(step, zone) / self.cap[zone]

    def _onsite(self, step):
        return self.onsite.get(step, self.onsite.get(self.steps[-1], 0.0))

    def zone_targets(self, step):
        """Nombre de points cible par zone d'activité (affluence / échelle)."""
        return {z: int(round(self._att(step, z) / self.scale)) for z in ACT_ZONES}

    def assigned(self):
        """Points présents dans les zones (posés ou en chemin vers une zone)."""
        by = {z: [] for z in ACT_ZONES}
        for d in self.dots:
            if d.state in ("moving", "idle") and d.zone in by:
                by[d.zone].append(d)
        return by

    # ---- écoulement granulaire au col (sablier de balles) ----
    def _settle_funnel(self, f):
        """Physique granulaire : les points en attente sont attirés vers le col,
        se repoussent (pas de chevauchement) et sont confinés par les parois de
        l'entonnoir -> ils s'ENTASSENT et s'écoulent comme des balles dans un
        sablier. Peu de points = ils atteignent le col aussitôt (flux libre) ;
        beaucoup = ils bouchonnent (goulot)."""
        gx, gy = G.GATE_POINT
        r2 = (2 * FUNNEL_R) ** 2
        for state, bulb in (("q_in", G.ENT_BOT), ("q_out", G.ENT_TOP)):
            parts = [d for d in self.dots if d.state == state]
            for p in parts:
                ax, ay = gx - p.x, gy - p.y
                an = (ax * ax + ay * ay) ** 0.5 or 1.0
                vx = ax / an * FUNNEL_ATTRACT
                vy = ay / an * FUNNEL_ATTRACT
                for q in parts:
                    if q is p:
                        continue
                    dx, dy = p.x - q.x, p.y - q.y
                    d2 = dx * dx + dy * dy
                    if 1e-6 < d2 < r2:
                        dd = d2 ** 0.5
                        force = (2 * FUNNEL_R - dd) / dd * FUNNEL_REPULSE
                        vx += dx * force
                        vy += dy * force
                p.x, p.y = G.bulb_clamp(p.x + vx, p.y + vy, bulb)

    def _nearest_neck(self, pool):
        gx, gy = G.GATE_POINT
        return min(pool, key=lambda p: (p.x - gx) ** 2 + (p.y - gy) ** 2)

    def _add_arrival(self, f):
        """Un arrivant apparaît DEHORS (base du bulbe) et remonte l'entonnoir."""
        x = 510.0 + rng.uniform(-110, 110)
        y = G.ENT_BOT["base_y"] - rng.uniform(0, 14)
        x, y = G.bulb_clamp(x, y, G.ENT_BOT)
        self.wait_in.append(self._mk_dot(None, x, y, "q_in"))

    def _cross_in(self, zone, f):
        """La « balle » la PLUS PROCHE du col le franchit et gagne sa zone."""
        if self.wait_in:
            d = self._nearest_neck(self.wait_in)
            self.wait_in.remove(d)
            d.oz = ENT_IDX
            wp = G.path_between("Entrance", zone)
            path = [(d.x, d.y), G.GATE_POINT] + list(wp[1:-1]) + [G.random_point_in(zone, rng)]
            d.zone = zone
            d.path, d.t0, d.state = path, f, "moving"
            d.dur = max(1.0, G.path_length(path) / C.WALK_SPEED * rng.uniform(0.8, 1.2))
        else:
            self._spawn_dot(zone, f)                 # entonnoir vide -> flux libre

    def _cross_out(self, f):
        if not self.wait_out:
            return
        d = self._nearest_neck(self.wait_out)
        self.wait_out.remove(d)
        d.oz = _zidx(d.zone)                         # dégradé zone -> porte
        ex = BOTTOM_EXIT[0] + rng.uniform(-45, 45)
        ey = BOTTOM_EXIT[1] + rng.uniform(-4, 4)
        path = [(d.x, d.y), G.GATE_POINT, (ex, ey)]
        d.path, d.t0, d.state = path, f, "leaving"
        d.dur = max(1.0, G.path_length(path) / C.WALK_SPEED * rng.uniform(0.8, 1.2))

    def _start_depart(self, d, f):
        """Le partant quitte sa zone et rejoint le bulbe de SORTIE (au-dessus du
        col) ; il y devient une « balle » qui s'écoule ensuite par le col."""
        tx = 510.0 + rng.uniform(-95, 95)
        ty = G.ENT_TOP["base_y"] + rng.uniform(0, 14)
        tx, ty = G.bulb_clamp(tx, ty, G.ENT_TOP)
        wp = G.path_between(d.zone, "Entrance") if d.zone in C.ZONES else [(d.x, d.y)]
        path = [(d.x, d.y)] + list(wp[1:-1]) + [(tx, ty)]
        d.oz = _zidx(d.zone)
        d.path, d.t0, d.state = path, f, "to_out"
        d.dur = max(1.0, G.path_length(path) / C.WALK_SPEED * rng.uniform(0.8, 1.2))

    # ---- initialisation ----
    def setup(self):
        step0 = self.steps[0]
        for z, n in self.zone_targets(step0).items():
            for _ in range(n):
                x, y = G.random_point_in(z, rng)
                self._mk_dot(z, x, y, "idle")
        for _ in range(int(round(self.queue.get(step0, 0) / self.scale))):
            self._add_arrival(0)                     # file d'entrée initiale
        uid = 0
        for rtype in RES_TYPES:
            zc = self.init_alloc[rtype]
            for z in C.ZONES:
                for _ in range(int(zc[z])):
                    x, y = G.random_point_in(z, rng, margin=14)
                    self.responders.append(Responder(uid, rtype, z, x, y))
                    uid += 1

    # ---- transitions de pas (toutes les 15 frames) ----
    def on_step(self, si, f):
        entry = self.log[si]
        step = entry["step"]

        alloc = entry.get("allocation") or self.init_alloc
        for rtype in RES_TYPES:
            self._apply_alloc(rtype, alloc[rtype], f)

        self._update_crowd(step, f)

        alert_keys = {(a["zone"], t) for a in entry.get("alerts", [])
                      for t in a["types"]}
        for inc in entry.get("truth_incidents", []):
            z, typ = inc["zone"], inc["type"]
            x, y = G.random_point_in(z, rng, margin=16)
            sev = SEVERITY.get(typ, 1)
            detected = (z, typ) in alert_keys
            spawn = f + int(rng.integers(0, self.frames_per_step))
            self.incidents.append(
                Incident(self._next_inc_id, z, x, y, sev, spawn, detected, typ))
            self._next_inc_id += 1

        self._repack(step, f)          # recale les cibles de repos (tassement)

    # ---- foule dynamique : migrations internes + files au col ----
    def _update_crowd(self, step, f):
        """Planifie les mouvements du pas, ÉTALÉS sur les 15 frames.

        - migrations inter-zones : directes (ne passent pas par la porte) ;
        - déficit restant : franchissements du col depuis la FILE d'entrée
          (au débit du déficit ≈ admissions) → la file grossit tant que les
          arrivées dépassent ce débit (goulot) ;
        - surplus : rejoint la FILE de sortie, franchie au débit du col
          (NECK_EXIT_CAP) → une file se forme à l'egress.
        """
        target = self.zone_targets(step)
        by = self.assigned()

        surplus = []
        for z in ACT_ZONES:
            extra = len(by[z]) - target[z]
            if extra > 0:
                cand = sorted(by[z], key=lambda d: 0 if d.state == "idle" else 1)
                surplus += cand[:extra]
        deficit = []
        for z in ACT_ZONES:
            need = target[z] - len(by[z])
            if need > 0:
                deficit += [z] * need
        rng.shuffle(deficit)

        fps = self.frames_per_step

        def when():
            return f + int(rng.integers(0, fps))

        # migrations internes (surplus <-> déficit, ne passent pas par la porte)
        mig = min(len(surplus), len(deficit))
        for k in range(mig):
            self._pending.append((when(), "migrate", (surplus[k], deficit[k])))
        leftover_surplus = surplus[mig:]
        leftover_deficit = deficit[mig:]

        # départs (surplus restant) -> FILE DE SORTIE
        for d in leftover_surplus:
            self._pending.append((when(), "depart", d))

        # FILE D'ENTRÉE : alimentée au rythme des ARRIVÉES, vidée au rythme des
        # ADMISSIONS (débit du col). Arrivées > admissions -> la file grossit.
        for _ in range(int(round(self.arrived.get(step, 0) / self.scale))):
            self._pending.append((when(), "arrive", None))
        n_in = int(round(self.admit.get(step, 0) / self.scale))
        for j in range(n_in):
            zone = leftover_deficit[j] if j < len(leftover_deficit) \
                else ACT_ZONES[self._weighted_zone(target)]      # trop-plein -> churn
            self._pending.append((when(), "cross_in", zone))
        for z in leftover_deficit[n_in:]:                        # file vide -> flux libre
            self._pending.append((when(), "spawn", z))

        # FILE DE SORTIE : vidée au débit du col (< egress de pointe -> file)
        for _ in range(int(round(C.NECK_EXIT_CAP_STEP / self.scale))):
            self._pending.append((when(), "cross_out", None))

    def _weighted_zone(self, target):
        w = np.array([max(target[z], 1) for z in ACT_ZONES], dtype=float)
        return int(rng.choice(len(ACT_ZONES), p=w / w.sum()))

    # ---- tassement : recalcule les cibles de repos selon la densité ----------
    def _active_incidents(self, f):
        return [i for i in self.incidents
                if f >= i.spawn and i.state in ("pending", "responding", "treating")]

    def _repack(self, step, f):
        """Pour chaque zone d'activité, place les cibles de repos des points
        posés à un rayon r = R·u^γ(d) du focal (γ croît avec la densité -> la
        foule se resserre quand la zone se remplit), avec une répulsion légère
        (pavage sans chevauchement) et une clairière autour des incidents."""
        active = self._active_incidents(f)
        by = {z: [] for z in ACT_ZONES}
        for d in self.dots:
            if d.state == "idle" and d.zone in by:
                by[d.zone].append(d)
        for z in ACT_ZONES:
            group = by[z]
            if not group:
                continue
            dens = min(max(self.density(step, z), 0.0), 1.0)
            gamma = PACK_GAMMA_LO + (PACK_GAMMA_HI * PACK_GAMMA_ZONE[z]
                                     - PACK_GAMMA_LO) * dens
            fx, fy = FOCAL[z]
            R = PACK_RMAX[z]
            x0, y0, x1, y1 = G.ZONE_BBOX[z]
            poly = G.ZONE_SHAPES[z]
            P = np.empty((len(group), 2))
            for k, d in enumerate(group):
                r = R * (d.u ** gamma)
                P[k, 0] = fx + np.cos(d.ang) * r
                P[k, 1] = fy + np.sin(d.ang) * r
            # répulsion légère (pavage) — quelques itérations vectorisées
            n = len(group)
            if n > 1:
                for _ in range(PACK_RELAX_ITERS):
                    diff = P[:, None, :] - P[None, :, :]
                    dist = np.sqrt((diff ** 2).sum(-1)) + 1e-6
                    mask = (dist < PACK_MIN_SEP)
                    np.fill_diagonal(mask, False)
                    push = np.where(mask[..., None],
                                    diff / dist[..., None]
                                    * (PACK_MIN_SEP - dist)[..., None] * 0.5, 0.0)
                    P += push.sum(1)
            # clairière autour des incidents actifs de la zone
            for inc in active:
                if inc.zone != z:
                    continue
                cr = CLEAR_R.get(inc.itype, 40.0)
                dv = P - np.array([inc.x, inc.y])
                dd = np.sqrt((dv ** 2).sum(-1)) + 1e-6
                inside = dd < cr
                if inside.any():
                    P[inside] = np.array([inc.x, inc.y]) + \
                        dv[inside] / dd[inside, None] * cr
            # confinement dans la zone
            for k, d in enumerate(group):
                px = min(max(P[k, 0], x0 + 6), x1 - 6)
                py = min(max(P[k, 1], y0 + 6), y1 - 6)
                if not G.point_in_poly(px, py, poly):
                    px = px + (fx - px) * 0.5   # ramène vers le focal (dans la zone)
                    py = py + (fy - py) * 0.5
                d.rx, d.ry = px, py

    def _apply_shock(self, f):
        """Onde de choc : juste après une bagarre, les points posés proches sont
        POUSSÉS radialement vers l'extérieur (impulsion qui décroît en temps et
        distance) -> un trou s'ouvre dans la foule, puis le glissement les
        ramène. Effet « panique » lisible sans être un déplacement permanent."""
        waves = [i for i in self.incidents
                 if i.itype == "crowd_surge" and i.spawn <= f < i.spawn + SURGE_WAVE_LEN]
        if not waves:
            return
        for d in self.dots:
            if d.state != "idle":
                continue
            for inc in waves:
                dx, dy = d.x - inc.x, d.y - inc.y
                dist = (dx * dx + dy * dy) ** 0.5
                if 1e-3 < dist < SURGE_WAVE_R:
                    age = (f - inc.spawn) / SURGE_WAVE_LEN
                    mag = SURGE_WAVE_PUSH * (1 - age) * (1 - dist / SURGE_WAVE_R)
                    d.x += dx / dist * mag
                    d.y += dy / dist * mag

    def _release_due(self, f):
        if not self._pending:
            return
        keep = []
        for rf, kind, payload in self._pending:
            if rf > f:
                keep.append((rf, kind, payload))
                continue
            if kind == "migrate":
                d, z = payload
                if not d.dead and d.state == "idle":
                    self._start_dot_walk(d, d.zone, z, f)
            elif kind == "cross_in":
                self._cross_in(payload, f)
            elif kind == "spawn":
                self._spawn_dot(payload, f)
            elif kind == "depart":
                if not payload.dead and payload.state == "idle":
                    self._start_depart(payload, f)
            elif kind == "arrive":
                self._add_arrival(f)
            elif kind == "cross_out":
                self._cross_out(f)
        self._pending = keep

    # ---- mise en mouvement ----
    def _spawn_dot(self, dz, f):
        """Arrivée : apparaît DEHORS (bas), franchit le col, rejoint sa zone."""
        sx = BOTTOM_EXIT[0] + rng.uniform(-45, 45)
        sy = BOTTOM_EXIT[1] + rng.uniform(-4, 4)
        d = self._mk_dot(dz, sx, sy, "moving")
        d.oz = ENT_IDX                                  # arrive de la porte -> teinte zone
        wp = G.path_between("Entrance", dz)
        target = G.random_point_in(dz, rng)
        path = [(sx, sy), G.GATE_POINT] + list(wp[1:-1]) + [target]
        d.path, d.t0, d.state = path, f, "moving"
        d.dur = max(1.0, G.path_length(path) / C.WALK_SPEED * rng.uniform(0.8, 1.2))

    def _start_dot_walk(self, d, old, dz, f, from_pos=None):
        wp = G.path_between(old, dz)
        target = G.random_point_in(dz, rng)
        start = from_pos if from_pos is not None else (d.x, d.y)
        path = [start] + list(wp[1:-1]) + [target]
        length = G.path_length(path)
        dur = max(1.0, length / C.WALK_SPEED * rng.uniform(0.8, 1.2))
        d.oz = _zidx(old)                               # origine -> dégradé vers dz
        d.zone = dz
        d.path, d.t0, d.dur, d.state = path, f, dur, "moving"

    def _start_leave(self, d, f):
        """Sortie : rejoint le col par l'intérieur, le franchit, disparaît dehors."""
        wp = G.path_between(d.zone, "Entrance") if d.zone in C.ZONES else [(d.x, d.y)]
        ex = BOTTOM_EXIT[0] + rng.uniform(-45, 45)
        ey = BOTTOM_EXIT[1] + rng.uniform(-4, 4)
        path = [(d.x, d.y)] + list(wp[1:-1]) + [G.GATE_POINT, (ex, ey)]
        dur = max(1.0, G.path_length(path) / C.WALK_SPEED * rng.uniform(0.8, 1.2))
        d.oz = _zidx(d.zone)                            # origine -> dégradé vers la porte
        d.path, d.t0, d.dur, d.state = path, f, dur, "leaving"

    def _start_move(self, u, old, dz, f, back):
        """Déplace une équipe de `old` vers `dz` ; durée = TRAVEL (autoritatif)."""
        wp = G.path_between(old, dz)
        dest = G.random_point_in(dz, rng, margin=14)
        path = [(u.x, u.y)] + list(wp[1:-1]) + [dest]
        dur = max(1.0, travel_time(old, dz))
        u.path, u.t0, u.dur, u.dest, u.state = path, f, dur, dest, "relocating"

    def _apply_alloc(self, rtype, counts, f):
        units = [u for u in self.responders if u.rtype == rtype]
        cur = Counter(u.home for u in units)
        movers = []
        for z in C.ZONES:
            extra = cur[z] - int(counts.get(z, 0))
            if extra > 0:
                cand = [u for u in units if u.home == z]
                cand.sort(key=lambda u: 0 if u.state == "idle" else 1)
                movers += cand[:extra]
        slots = []
        for z in C.ZONES:
            need = int(counts.get(z, 0)) - cur[z]
            if need > 0:
                slots += [z] * need
        for u in movers:
            if not slots:
                break
            dz = min(slots, key=lambda z: travel_time(u.home, z))
            slots.remove(dz)
            old = u.home
            u.home = dz
            if u.state == "idle":
                self._start_move(u, old, dz, f, back=False)

    # ---- pas de temps (1 min / frame) ----
    def _advance_movers(self, f):
        si = min(f // self.frames_per_step, self.n_steps - 1)
        step = self.log[si]["step"]
        wander = {z: 0.85 * (1.0 - min(max(self.density(step, z), 0.0), 1.0))
                  for z in ACT_ZONES}   # foule tassée = quasi immobile
        for d in self.dots:
            if d.state in ("moving", "leaving", "to_out"):
                frac = (f - d.t0) / d.dur
                if frac >= 1.0:
                    d.x, d.y = d.path[-1]
                    d.path = None
                    if d.state == "leaving":
                        d.dead = True                       # sorti du site
                    elif d.state == "to_out":               # arrivé au bulbe de sortie
                        d.state = "q_out"
                        self.wait_out.append(d)
                    else:
                        d.state = "idle"
                        d.oz = _zidx(d.zone)                # arrivé : couleur = zone
                        d.u = float(rng.uniform(0.0, 1.0))  # prend une place
                        d.ang = float(rng.uniform(0.0, 2 * np.pi))
                        d.rx, d.ry = d.x, d.y
                else:
                    d.x, d.y = G.position_along(d.path, frac)
            elif d.state in ("q_in", "q_out"):
                pass                                        # positions -> _settle_funnel
            else:                                           # posé : glisse vers la cible
                x0, y0, x1, y1 = G.ZONE_BBOX[d.zone]
                amp = wander.get(d.zone, 0.5)
                d.x += (d.rx - d.x) * PACK_GLIDE + rng.normal(0, amp)
                d.y += (d.ry - d.y) * PACK_GLIDE + rng.normal(0, amp)
                d.x = min(max(d.x, x0 + 5), x1 - 5)
                d.y = min(max(d.y, y0 + 5), y1 - 5)
        if any(d.dead for d in self.dots):
            self.dots = [d for d in self.dots if not d.dead]

        for u in self.responders:
            if u.state in ("relocating", "responding"):
                frac = (f - u.t0) / u.dur
                if frac >= 1.0:
                    u.x, u.y = u.path[-1]
                    u.path = None
                    if u.state == "responding":
                        self._on_arrival(u, f)
                    elif u.escort is not None:
                        u.state = "perimeter"          # tient le cordon
                    else:
                        u.state = "idle"
                else:
                    u.x, u.y = G.position_along(u.path, frac)
            elif u.state == "busy":
                if f >= u.busy_until:
                    self._on_treated(u, f)

    def _on_arrival(self, u, f):
        inc = u.incident
        u.state = "busy"
        treat = float(rng.uniform(5, 12))
        u.busy_until = f + treat
        inc.state = "treating"
        inc.treat_start = f
        inc.treat_end = f + treat
        self.response_times.append(f - inc.spawn)

    def _on_treated(self, u, f):
        inc = u.incident
        inc.state = "resolved"
        inc.resolved_at = f
        u.incident = None
        self._start_move(u, inc.zone, u.home, f, back=True)

    def _dispatch(self, f):
        pending = [i for i in self.incidents if i.state == "pending"]
        pending.sort(key=lambda i: (-i.sev, i.spawn))
        for inc in pending:
            if f < inc.spawn:
                continue
            if f - inc.spawn >= ABANDON_MIN:
                inc.state = "uncovered"
                continue
            if inc.dispatch_zone is None:
                inc.dispatch_zone, inc.best_t = self._choose_zone(inc.zone)
            if inc.dispatch_zone is None:
                inc.state = "uncovered"
                continue
            unit = next((u for u in self.responders
                         if u.rtype == "medical" and u.state == "idle"
                         and u.home == inc.dispatch_zone), None)
            if unit is None:
                continue
            wp = G.path_between(inc.dispatch_zone, inc.zone)
            path = [(unit.x, unit.y)] + list(wp[1:-1]) + [(inc.x, inc.y)]
            unit.path, unit.t0, unit.dur = path, f, max(1.0, inc.best_t)
            unit.state = "responding"
            unit.incident = inc
            inc.unit = unit
            inc.state = "responding"

    def _escort(self, f):
        """Cordon de sécurité : sur une BAGARRE (crowd_surge) active, les 2
        équipes de sécurité les plus proches et libres viennent former un
        périmètre autour de l'incident, puis rentrent quand il est clos.

        Couche de PRÉSENTATION : les KPIs restent gouvernés par la réponse
        médicale (fidèle à `mas.py`) ; ce cordon ne fait que rendre la réaction
        des forces de l'ordre visible sur le plan."""
        surges = [i for i in self.incidents
                  if i.itype in ("crowd_surge", "fight") and f >= i.spawn
                  and i.state in ("pending", "responding", "treating")]
        active = {i.id for i in surges}
        for inc in surges:
            assigned = [u for u in self.responders if u.escort is inc]
            need = 2 - len(assigned)
            if need <= 0:
                continue
            free = [u for u in self.responders if u.rtype == "security"
                    and u.state == "idle" and u.escort is None]
            free.sort(key=lambda u: (u.x - inc.x) ** 2 + (u.y - inc.y) ** 2)
            for k in range(min(need, len(free))):
                u = free[k]
                u.escort = inc
                ang = 2 * np.pi * (len(assigned) + k) / 2.0 + 0.6
                rx, ry = inc.x + np.cos(ang) * 34, inc.y + np.sin(ang) * 34
                u.path, u.t0 = [(u.x, u.y), (rx, ry)], f
                u.dur = max(1.0, travel_time(u.home, inc.zone))
                u.dest, u.state = (rx, ry), "relocating"
        for u in self.responders:                    # relève : incident clos -> retour
            if u.escort is not None and u.escort.id not in active:
                old = u.escort.zone
                u.escort = None
                if u.state == "perimeter":
                    self._start_move(u, old, u.home, f, back=True)

    def _choose_zone(self, zone):
        homes = Counter(u.home for u in self.responders if u.rtype == "medical")
        if homes.get(zone, 0) > 0:
            return zone, travel_time(zone, zone)
        cands = [(z, travel_time(z, zone)) for z in C.ZONES if homes.get(z, 0) > 0]
        if not cands:
            return None, 0.0
        best = min(cands, key=lambda c: c[1])
        return best[0], best[1]

    # ---- enregistrement ----
    def _dot_zone_index(self, d):
        return _zidx(d.zone)

    def _prog(self, d, f):
        if not d.dur:
            return 100
        return int(min(max((f - d.t0) / d.dur, 0.0), 1.0) * 100)

    def _record(self, si, fi, f):
        step = self.log[si]["step"]
        minute = f - si * self.frames_per_step
        # point = [id, x, y, to_zi, from_zi, blend%, state] — le lecteur interpole
        # la COULEUR de from_zi vers to_zi selon blend (dégradé pendant le trajet)
        dots = []
        for d in self.dots:
            if d.state == "leaving":
                to_zi, blend = ENT_IDX, self._prog(d, f)       # se fond vers la porte
            elif d.state == "moving":
                to_zi, blend = self._dot_zone_index(d), self._prog(d, f)
            else:
                to_zi, blend = self._dot_zone_index(d), 100
            dots.append([d.id, int(d.x), int(d.y), to_zi, d.oz, blend,
                         DOT_STATE[d.state]])
        # équipe = [id, rtype, x, y, state, target_inc_id] (-1 si aucun)
        resp = []
        for u in self.responders:
            tid = (u.incident.id if u.incident is not None
                   else u.escort.id if u.escort is not None else -1)
            resp.append([u.id, RES_IDX[u.rtype], int(u.x), int(u.y),
                         RESP_STATE[u.state], tid])
        # incident = [id, x, y, sev, state, detected, type, unit_id, aux%, parent]
        #   aux = compte à rebours d'abandon (pending) ou avancement du soin
        #   (treating) en % ; parent = id de l'incident déclencheur (chaîne) ou -1.
        inc = []
        for i in self.incidents:
            if i.state == "resolved" and i.resolved_at is not None \
                    and f - i.resolved_at > RESOLVED_LINGER:
                continue
            if f < i.spawn:
                continue
            if i.state == "pending":
                aux = int(min(100, (f - i.spawn) / ABANDON_MIN * 100))
            elif i.state == "treating" and i.treat_start is not None \
                    and i.treat_end and i.treat_end > i.treat_start:
                aux = int(min(100, max(0, (f - i.treat_start)
                                       / (i.treat_end - i.treat_start) * 100)))
            else:
                aux = 0
            inc.append([i.id, int(i.x), int(i.y), i.sev,
                        INC_STATE[i.state], 1 if i.detected else 0,
                        INC_TYPE_IDX.get(i.itype, 0),
                        i.unit.id if i.unit is not None else -1, aux, i.parent])
        dens = {z: round(self.density(step, z), 3) for z in C.ZONES}
        open_n = sum(1 for i in self.incidents
                     if i.state in ("pending", "responding", "treating")
                     and f >= i.spawn)
        res_n = sum(1 for i in self.incidents if i.state == "resolved")
        unc_n = sum(1 for i in self.incidents if i.state == "uncovered")
        mean_rt = round(float(np.mean(self.response_times)), 1) \
            if self.response_times else 0.0
        return {
            "t": f, "step": step, "clock": _clock(step, minute),
            "dots": dots, "resp": resp, "inc": inc, "dens": dens,
            "kpi": {"open": open_n, "resolved": res_n,
                    "uncovered": unc_n, "mean_rt": mean_rt,
                    "onsite": int(round(self._onsite(step))),
                    "flow_in": int(round(self.admit.get(step, 0) / C.STEP_MINUTES)),
                    "flow_out": int(round(self.depart.get(step, 0) / C.STEP_MINUTES))},
        }

    # ---- boucle principale ----
    def run(self):
        self.setup()
        frames = []
        for si in range(self.n_steps):
            for fi in range(self.frames_per_step):
                f = si * self.frames_per_step + fi
                if fi == 0:
                    self.on_step(si, f)
                self._release_due(f)
                self._incident_chains(f)
                self._dispatch(f)
                self._escort(f)
                self._settle_funnel(f)
                self._advance_movers(f)
                self._apply_shock(f)
                frames.append(self._record(si, fi, f))
        return frames

    # ---- réaction en chaîne (visuel) : un mouvement de foule / une bagarre non
    # contenu engendre des chutes induites tant qu'il reste ouvert. Le lecteur
    # relie l'enfant au parent. (Le comptage KPI autoritatif est dans kpis.py ;
    # ici c'est le jumeau visuel du branchement.)
    def _incident_chains(self, f):
        remaining = self.n_frames - f
        if remaining < ABANDON_MIN + 6:        # pas d'enfant trop tard (il se clôt)
            return
        step = self.log[min(f // self.frames_per_step,
                             self.n_steps - 1)]["step"]
        for i in list(self.incidents):
            if i.itype not in ("crowd_surge", "fight"):
                continue
            # la chaîne court tant que l'incident n'est PAS clos (l'onde de foule
            # continue de faire tomber des gens même pendant la prise en charge)
            if i.state in ("resolved", "uncovered") or f < i.spawn:
                continue
            d = self.density(step, i.zone)
            if d < 0.5:
                continue
            age = f - i.spawn
            if age < 3 or age > 22:
                continue
            rate = (0.10 if i.itype == "crowd_surge" else 0.07) * d
            if i.state == "treating":
                rate *= 0.4                    # une fois l'équipe sur zone, ça calme
            if rng.random() < rate and self._chain_budget(i):
                self._spawn_induced(i, f)

    def _chain_budget(self, parent):
        n = sum(1 for c in self.incidents if c.parent == parent.id)
        return n < 4                           # borne le nombre d'enfants induits

    def _spawn_induced(self, parent, f):
        x, y = G.random_point_in(parent.zone, rng, margin=20)
        child = Incident(self._next_inc_id, parent.zone, x, y,
                         SEVERITY.get("fallen_person", 3), f, True,
                         "fallen_person", parent=parent.id)
        self._next_inc_id += 1
        self.incidents.append(child)


# ---------------------------------------------------------------------------
# En-tête + assemblage
# ---------------------------------------------------------------------------
def _chapters():
    """Chapitres narratifs (minute-de-journée = index de frame, 1 frame=1 min)."""
    marks = [(0, "Ouverture"),
             (360, "Ruée 16–18h"),
             (C.HEADLINER_START_MIN - 90, "Pré-headliner + file"),
             (C.HEADLINER_START_MIN, "Tête d'affiche"),
             (C.HEADLINER_END_MIN, "Egress")]
    return [[m, lab] for m, lab in marks]


def _comparison():
    """Bloc COMPARAISON avec/sans (léger : séries par pas + agrégats, PAS de
    frames) chargé depuis outputs/kpi_comparison.json s'il existe. Alimente le
    bandeau « AVEC / SANS » du lecteur et les horodatages jumeaux du journal.
    Retourne None si l'évaluateur n'a pas encore tourné (démo dégradée)."""
    path = os.path.join(C.OUT, "kpi_comparison.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        cmp = json.load(fh)

    def slim(side):
        return {
            "mean_response_min": side["mean_response_min"]["mean"],
            "mean_detect_min": side["mean_detect_min"]["mean"],
            "mean_first_aid_min": side["mean_first_aid_min"]["mean"],
            "pct_within_target": side["pct_within_target"],
            "mean_uncovered": side["mean_uncovered"],
            "mean_induced": side["mean_induced"],
            "r_eff": side["r_eff"],
            "mean_mce": side["mean_mce"],
            "mean_outcome": side["mean_outcome"],
            "foodcourt_wait_mean_min": side["foodcourt_wait_mean_min"],
            "lost_customers": side["lost_customers"],
            "lost_revenue_eur": side["lost_revenue_eur"],
            "step_series": side["step_series"],
        }

    a, s = cmp["avec"], cmp["sans"]
    # horodatages jumeaux par incident (clé = ordre d'apparition)
    pa = {p["idx"]: p for p in a["per_incident"]}
    ps = {p["idx"]: p for p in s["per_incident"]}
    per_inc = []
    for idx in sorted(pa):
        A, S = pa[idx], ps.get(idx, {})
        per_inc.append({
            "step": A["step"], "zone": A["zone"], "type": A["type"],
            "detect_avec": A["detect_min"], "detect_sans": S.get("detect_min"),
            "resp_avec": A["response_min"], "resp_sans": S.get("response_min"),
        })
    return {"avec": slim(a), "sans": slim(s),
            "targets": cmp["targets"], "per_incident": per_inc}


def _header(log, engine):
    zones = {z: {"poly": G.ZONE_SHAPES[z],
                 "center": [round(v, 1) for v in G.ZONE_CENTER[z]],
                 "focal": [round(v, 1) for v in FOCAL[z]] if z in FOCAL
                          else [round(v, 1) for v in G.ZONE_CENTER[z]],
                 "color": G.ZONE_COLORS[z]["light"],
                 "color_dark": G.ZONE_COLORS[z]["dark"],
                 "capacity": C.ZONE_CAPACITY[z]}
             for z in C.ZONES}
    paths = [G.path_between(a, b)
             for i, a in enumerate(C.ZONES) for b in C.ZONES[i + 1:]]
    steps = []
    for e in log:
        st = e["step"]
        steps.append({
            "step": st,
            "clock": _clock(st),
            "trigger": e.get("trigger"),
            "resolved": e.get("resolved", False),
            "alerts": e.get("alerts", []),
            "truth_incidents": e.get("truth_incidents", []),
            "forecast_peak": e.get("forecast_peak", {}),
            "dens": {z: round(engine.density(st, z), 3) for z in C.ZONES},
            "queue": int(round(engine.queue.get(st, 0))),
            "allocation": e.get("allocation"),
            "solver_status": e.get("solver_status"),
        })
    return {
        "map_w": C.MAP_W, "map_h": C.MAP_H,
        "zones_order": C.ZONES,
        "zones": zones, "paths": paths,
        "gate": list(G.GATE_POINT), "bottom_exit": list(BOTTOM_EXIT),
        "res_types": RES_TYPES,
        "resp_states": RESP_STATE, "inc_states": INC_STATE, "dot_states": DOT_STATE,
        "inc_types": INC_TYPES,
        "schedule": [[z, s, en, p] for (z, s, en, p) in C.SCHEDULE],
        "chapters": _chapters(),
        "headliner": [C.HEADLINER_START_MIN, C.HEADLINER_END_MIN],
        "density_threshold": C.DENSITY_ALERT_THRESHOLD,
        "resources_total": C.RESOURCES,
        "step_minutes": C.STEP_MINUTES,
        "frames_per_step": C.FRAMES_PER_STEP,
        "comparison": _comparison(),
        "steps": steps,
    }


def _load():
    df = pd.read_csv(C.DATA_CSV)
    flow = pd.read_csv(C.FLOW_CSV)
    with open(os.path.join(C.OUT, "control_log.json")) as fh:
        log = json.load(fh)
    return df, flow, log


def build_replay(out_path=None):
    out_path = out_path or C.REPLAY_JSON
    df, flow, log = _load()
    engine = ReplayEngine(df, log, flow)
    frames = engine.run()

    payload = {"header": _header(log, engine), "frames": frames}
    with open(out_path, "w") as fh:
        json.dump(payload, fh, separators=(",", ":"))

    size_mb = os.path.getsize(out_path) / 1e6
    max_dots = max(len(fr["dots"]) for fr in frames)
    print(f"-> replay : {out_path}  "
          f"({len(frames)} frames, ≤{max_dots} points foule, 1 pt ≙ "
          f"{int(engine.scale)} pers., {len(engine.incidents)} incidents, "
          f"{size_mb:.1f} Mo)")
    return payload


# ---------------------------------------------------------------------------
# Auto-vérification
# ---------------------------------------------------------------------------
def _self_check():
    df, flow, log = _load()
    engine = ReplayEngine(df, log, flow)
    frames = engine.run()
    scale = engine.scale

    # (a) borne du nombre de points affichés (actifs + files au col)
    max_dots = max(len(fr["dots"]) for fr in frames)
    assert max_dots <= C.MAX_DOTS * 1.6, \
        f"trop de points affichés : {max_dots} > {C.MAX_DOTS}*1.6"

    # (b) conservation approx : Σ points actifs ≈ onsite / échelle
    #     (échantillonné en fin de pas, une fois les flux étalés libérés)
    worst = 0.0
    for si, e in enumerate(log):
        fr = frames[si * C.FRAMES_PER_STEP + C.FRAMES_PER_STEP - 1]
        active = sum(1 for d in fr["dots"] if d[6] in (1, 2))  # moving|idle
        expect = engine._onsite(e["step"]) / scale
        if expect > 5:
            worst = max(worst, abs(active - expect) / expect)
    assert worst < 0.30, f"conservation foule violée (écart {worst*100:.0f} %)"

    # (c) progression « se remplit puis se vide » : le site est léger à
    #     l'ouverture et à la fermeture, le pic est au milieu de la journée,
    #     et les scènes se vident nettement à la fin par rapport à leur pic.
    onsite_seq = [engine._onsite(e["step"]) for e in log]
    peak_val = max(onsite_seq)
    peak_at = onsite_seq.index(peak_val)
    assert onsite_seq[0] < 0.7 * peak_val, "site déjà plein à l'ouverture"
    assert onsite_seq[-1] < 0.7 * peak_val, "site encore plein à la fermeture"
    assert 0.4 * len(onsite_seq) <= peak_at <= 0.9 * len(onsite_seq), \
        f"pic de population mal placé (pas {peak_at}/{len(onsite_seq)})"

    def stages_dots(fr):
        idx = {C.ZONES.index("MainStage"), C.ZONES.index("SecondStage")}
        return sum(1 for d in fr["dots"] if d[3] in idx and d[6] in (1, 2))
    stage_peak = max(stages_dots(fr) for fr in frames)
    assert stages_dots(frames[-1]) < 0.35 * max(stage_peak, 1), \
        "scènes pas assez vidées à la fermeture"

    # (d) tous les incidents réels finissent résolus ou non couverts
    open_states = {"pending", "responding", "treating"}
    unfinished = [i for i in engine.incidents if i.state in open_states]
    assert not unfinished, f"{len(unfinished)} incident(s) jamais clôturé(s)"

    onsite_peak = max(engine.onsite.get(s, 0) for s in engine.steps)
    onsite_end = engine._onsite(engine.steps[-1])
    n_res = sum(1 for i in engine.incidents if i.state == "resolved")
    n_unc = sum(1 for i in engine.incidents if i.state == "uncovered")
    mean_rt = float(np.mean(engine.response_times)) if engine.response_times else 0.0
    print("Auto-vérification OK")
    print(f"  frames                 : {len(frames)} (jour complet 10h->minuit)")
    print(f"  points de foule        : ≤{max_dots} (1 pt ≙ {int(scale)} pers.)")
    print(f"  population pic / fin    : {onsite_peak:.0f} -> {onsite_end:.0f} "
          f"(campeurs restants la nuit)")
    print(f"  conservation foule     : écart max {worst*100:.0f} %")
    print(f"  incidents rejoués      : {len(engine.incidents)} "
          f"({n_res} résolus, {n_unc} non couverts)")
    print(f"  temps de réponse moyen : {mean_rt:.1f} min (arrivée des secours)")
    print(f"  équipes                : {len(engine.responders)} unités "
          f"({', '.join(f'{r}={C.RESOURCES[r]}' for r in RES_TYPES)})")


if __name__ == "__main__":
    _self_check()
    print()
    build_replay()
