"""
Génération de données simulées du festival (Compétence 2 — Gérer).

Modèle de POPULATION à jour complet, inspiré d'études réelles de festivals
(cf. README, section « Modèle de population ») :

  - le site part VIDE à 10h et se remplit progressivement ;
  - arrivées = processus de Poisson non-homogène, par TYPE de visiteur
    (campeurs présents dès l'ouverture · lève-tôt · gros pic d'après-midi
    16h-18h · public tête-d'affiche arrivant ~90 min avant) ;
  - goulot d'entrée : file d'attente aux portes quand le flux dépasse la
    capacité d'admission (la file de fin d'après-midi bien connue) ;
  - départs : quasi nuls avant 20h, puis egress compressé après la tête
    d'affiche (choix de départ individuel → étalement log-normal), lui aussi
    borné par une capacité de sortie ;
  - déplacements internes pilotés par le PROGRAMME des concerts, avec une forte
    INERTIE (les festivaliers campent autour d'une scène plutôt que de circuler
    sans cesse — constat empirique) ;
  - les campeurs restent la nuit : à minuit le site n'est pas vide, le Camping
    l'est encore.

Loi de conservation : Σ_zones affluence(t) == population sur site(t).

Produit :
- attendance.csv : affluence par zone / pas de 15 min (+ covariables)
- flow.csv       : population sur site, admissions, départs, file — par pas
- events.csv     : incidents injectés (vérité terrain pour la détection)
"""
import numpy as np
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as C

rng = np.random.default_rng(42)

# zones « d'activité » où les gens séjournent (l'Entrée n'est que du transit)
ACT_ZONES = ["MainStage", "SecondStage", "FoodCourt", "Camping"]


# --------------------------------------------------------------------------
# Formes temporelles
# --------------------------------------------------------------------------
def _step_minutes(s: int) -> float:
    """Minute (milieu) d'un pas depuis l'ouverture (10h = 0)."""
    return s * C.STEP_MINUTES + C.STEP_MINUTES / 2.0


def _arrival_weights(kind: str, S: int) -> np.ndarray:
    """Poids d'arrivée normalisés par pas (forme de la courbe d'affluence)."""
    w = np.zeros(S)
    for s in range(S):
        m = _step_minutes(s)
        if kind == "early":                       # décroissance dès l'ouverture
            w[s] = np.exp(-s / 6.0)               # étalé sur toute la matinée
        elif kind == "planner":                   # log-normale, mode ~13h45
            mu, sig = np.log(235.0), 0.27
            w[s] = np.exp(-(np.log(m) - mu) ** 2 / (2 * sig ** 2)) / m
        elif kind == "headliner":                 # ~90..10 min avant la tête d'affiche
            center = C.HEADLINER_START_MIN - 45
            if C.HEADLINER_START_MIN - 90 <= m <= C.HEADLINER_START_MIN - 10:
                w[s] = np.exp(-((m - center) ** 2) / (2 * 25.0 ** 2))
    tot = w.sum()
    return w / tot if tot > 0 else w


def _depart_hazard(kind: str, s: int) -> float:
    """Fraction de la population sur site (de ce type) qui part au pas s."""
    m = _step_minutes(s)
    if kind in ("camper",):
        return 0.0                                # les campeurs ne sortent pas
    if kind == "early":                           # départ progressif dès 18h
        if m < 480:
            return 0.0
        return min(0.35, 0.35 * (m - 480) / (C.HEADLINER_END_MIN - 480))
    # planner / headliner : rien avant la fin de la tête d'affiche, puis egress
    if m < C.HEADLINER_END_MIN:
        return 0.0
    k = int((m - C.HEADLINER_END_MIN) // C.STEP_MINUTES)   # pas depuis la fin
    curve = [0.35, 0.45, 0.60, 0.80, 1.0]
    return curve[k] if k < len(curve) else 1.0


_CAPS = np.array([C.ZONE_CAPACITY[z] for z in ACT_ZONES], dtype=float)


def _attractiveness(s: int, is_camper: bool, crowd_pen: np.ndarray) -> np.ndarray:
    """Attractivité par zone d'activité (pilote le softmax de choix).

    `crowd_pen` : pénalité d'évitement des zones proches de la saturation
    (rétroaction avec 1 pas de retard) — empêche la sur-occupation et crée le
    débordement réaliste vers les zones voisines pendant la tête d'affiche.
    """
    m = _step_minutes(s)
    # bases faibles pour les scènes (une scène SANS concert n'attire personne) ;
    # food/camping servent de points de ralliement hors concert.
    A = {"MainStage": 0.08, "SecondStage": 0.08, "FoodCourt": 0.25, "Camping": 0.15}

    # concerts en cours (montée 15 min avant, descente 15 min après)
    for zone, start, end, pop in C.SCHEDULE:
        if start - 15 <= m <= end + 15:
            ramp = 1.0
            if m < start:
                ramp = (m - (start - 15)) / 15.0
            elif m > end:
                ramp = max(0.0, (end + 15 - m) / 15.0)
            A[zone] += pop * 1.6 * ramp

    # repas
    if 120 <= m <= 240:
        A["FoodCourt"] += 0.35                    # déjeuner
    if 480 <= m <= 630:
        A["FoodCourt"] += 0.45                    # dîner
    # afflux food juste après la fin d'un concert (entractes)
    for zone, start, end, pop in C.SCHEDULE:
        if 0 <= m - end <= 25:
            A["FoodCourt"] += 0.40 * pop

    # affinité camping
    if is_camper:
        if m < 120:
            A["Camping"] += 1.5                   # réveil au camping le matin
        if m > 690:
            A["Camping"] += 0.4 + 0.02 * (m - 690)  # retour nuit (croissant)
    else:
        if m > C.HEADLINER_END_MIN:
            A["Camping"] += 0.2                   # quelques-uns traînent

    return np.array([A[z] for z in ACT_ZONES]) - crowd_pen


def _softmax(a: np.ndarray, temp: float) -> np.ndarray:
    z = a / temp
    z -= z.max()
    e = np.exp(z)
    return e / e.sum()


# --------------------------------------------------------------------------
# Simulation d'une journée -> affluence par zone + flux
# --------------------------------------------------------------------------
def _simulate_day(weather: float):
    S = C.STEPS_PER_DAY
    N_day = C.PEAK_POPULATION * C.DAY_TURNOVER * weather
    totals = {k: int(round(N_day * v)) for k, v in C.VISITOR_MIX.items()}
    types = list(C.VISITOR_MIX)

    # arrivées par type et par pas (multinomiale = Poisson à total fixé)
    arrivals = {}
    for k in types:
        if k == "camper":
            arrivals[k] = np.zeros(S, dtype=int)   # présents dès l'ouverture
        else:
            arrivals[k] = rng.multinomial(totals[k], _arrival_weights(k, S))

    onsite = {k: 0.0 for k in types}
    onsite["camper"] = float(totals["camper"])     # campeurs déjà là
    queue = {k: 0.0 for k in types}                # file d'attente aux portes

    # répartition par zone (4 zones d'activité), par type
    pop = {k: np.zeros(len(ACT_ZONES)) for k in types}
    camp_idx = ACT_ZONES.index("Camping")
    pop["camper"][camp_idx] = float(totals["camper"])  # campeurs au camping

    att = np.zeros((S, C.N_ZONES))                 # affluence par pas x zone
    flow = np.zeros((S, 5))                        # onsite, admis, partis, file, arrivées
    ent_idx = C.ZONES.index("Entrance")

    for s in range(S):
        # pénalité d'affluence (rétroaction, état du pas précédent)
        zprev = sum(pop[k] for k in types)
        crowd_pen = C.CROWD_AVERSION * np.maximum(0.0, zprev / _CAPS - 0.85)

        # ---- 1. admission (goulot d'entrée) ----
        arrived_tot = sum(int(arrivals[k][s]) for k in types)
        want = {k: arrivals[k][s] + queue[k] for k in types}
        want_tot = sum(want.values())
        admit_tot = min(want_tot, float(C.GATE_CAP_STEP))
        admit = {}
        for k in types:
            admit[k] = admit_tot * want[k] / want_tot if want_tot > 0 else 0.0
            queue[k] = want[k] - admit[k]
            onsite[k] += admit[k]
            if admit[k] > 0:                        # arrivants -> vers une zone
                share = _softmax(_attractiveness(s, k == "camper", crowd_pen),
                                 C.CHOICE_TEMP)
                pop[k] += admit[k] * share

        # ---- 2. départs (egress borné par la capacité de sortie) ----
        desired = {k: onsite[k] * _depart_hazard(k, s) for k in types}
        desired_tot = sum(desired.values())
        scale = min(1.0, C.EXIT_CAP_STEP / desired_tot) if desired_tot > 0 else 0.0
        depart_tot = 0.0
        for k in types:
            d = desired[k] * scale
            frac = d / onsite[k] if onsite[k] > 0 else 0.0
            pop[k] *= (1.0 - frac)
            onsite[k] -= d
            depart_tot += d

        # ---- 3. déplacements internes (inertie) ----
        for k in types:
            if onsite[k] <= 0:
                continue
            share = _softmax(_attractiveness(s, k == "camper", crowd_pen),
                             C.CHOICE_TEMP)
            desired_pop = onsite[k] * share
            pop[k] += C.MOBILITY[k] * (desired_pop - pop[k])
            pop[k] = np.clip(pop[k], 0, None)
            ssum = pop[k].sum()
            if ssum > 0:                            # renormalise -> conservation
                pop[k] *= onsite[k] / ssum

        # ---- 4. enregistrement ----
        zpop = sum(pop[k] for k in types)          # somme sur les types, par zone
        for zi, z in enumerate(ACT_ZONES):
            att[s, C.ZONES.index(z)] = zpop[zi]
        queue_tot = sum(queue.values())
        # Entrée = transit (file + moitié des flux entrant/sortant en gare)
        att[s, ent_idx] = queue_tot + 0.5 * (admit_tot + depart_tot)
        onsite_tot = sum(onsite.values())
        flow[s] = [onsite_tot, admit_tot, depart_tot, queue_tot, arrived_tot]

    return att, flow


# --------------------------------------------------------------------------
# Assemblage multi-jours + incidents
# --------------------------------------------------------------------------
def generate() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, flow_rows = [], []
    hl_lo = int(C.HEADLINER_START_MIN // C.STEP_MINUTES)   # pas de la tête d'affiche
    hl_hi = int(C.HEADLINER_END_MIN // C.STEP_MINUTES)

    for day in range(C.FESTIVAL_DAYS):
        weather = rng.uniform(0.78, 1.0)
        att, flow = _simulate_day(weather)

        for step in range(C.STEPS_PER_DAY):
            g = day * C.STEPS_PER_DAY + step
            is_head = hl_lo <= step < hl_hi
            for zi, zone in enumerate(C.ZONES):
                rows.append({
                    "step": g, "day": day, "tod": step / C.STEPS_PER_DAY,
                    "zone": zone, "attendance": max(0, int(round(att[step, zi]))),
                    "capacity": C.ZONE_CAPACITY[zone], "headliner": int(is_head),
                    "weather": round(weather, 3),
                })
            flow_rows.append({
                "step": g, "day": day,
                "onsite": int(round(flow[step, 0])),
                "admitted": int(round(flow[step, 1])),
                "departed": int(round(flow[step, 2])),
                "queue": int(round(flow[step, 3])),
                "arrived": int(round(flow[step, 4])),
            })

    df = pd.DataFrame(rows)
    flow_df = pd.DataFrame(flow_rows)

    # ---- incidents injectés (vérité terrain) ----
    ev = []
    for _ in range(12):
        step = int(rng.integers(C.STEPS_PER_DAY // 3, C.TOTAL_STEPS))
        zone = rng.choice(C.ZONES[:3])
        kind = rng.choice(["fallen_person", "suspicious_object", "crowd_surge"],
                          p=[0.4, 0.2, 0.4])
        ev.append({"step": step, "zone": zone, "type": kind})

    # bagarres : le SOIR (après 18h), dans les zones denses (foule + alcool) —
    # type distinct du mouvement de foule, détecté par la sécurité (pas la caméra)
    evening_lo = int(480 // C.STEP_MINUTES)     # 18h
    for _ in range(4):
        day = int(rng.integers(0, C.FESTIVAL_DAYS))
        sid = int(rng.integers(evening_lo, C.STEPS_PER_DAY))
        ev.append({"step": day * C.STEPS_PER_DAY + sid,
                   "zone": str(rng.choice(["MainStage", "SecondStage", "FoodCourt"])),
                   "type": "fight"})

    # incidents garantis répartis sur la journée rejouée (dernier jour) :
    # arrivée/file · dîner · plein headliner · egress — pour la démo
    w0 = C.TOTAL_STEPS - C.STEPS_PER_DAY
    ev += [
        {"step": w0 + 26, "zone": "FoodCourt",   "type": "fallen_person"},  # ~16h30, après-midi
        {"step": w0 + 40, "zone": "Entrance",    "type": "crowd_surge"},    # ~20h, ruée pré-headliner (file)
        {"step": w0 + 44, "zone": "FoodCourt",   "type": "fight"},          # ~20h30, file dîner
        {"step": w0 + 47, "zone": "MainStage",   "type": "crowd_surge"},    # ~21h45, plein headliner
        {"step": w0 + 49, "zone": "MainStage",   "type": "fight"},          # ~22h15, tête d'affiche
        {"step": w0 + 52, "zone": "MainStage",   "type": "fallen_person"},  # ~23h, egress
    ]
    events = pd.DataFrame(ev).sort_values("step").reset_index(drop=True)

    os.makedirs(C.OUT, exist_ok=True)
    df.to_csv(C.DATA_CSV, index=False)
    flow_df.to_csv(C.FLOW_CSV, index=False)
    events.to_csv(C.EVENTS_CSV, index=False)
    return df, events


# --------------------------------------------------------------------------
def _summary(df, flow):
    """Résumé + contrôles de cohérence du modèle de population."""
    S = C.STEPS_PER_DAY
    last = df[df.day == C.FESTIVAL_DAYS - 1]
    fl = flow[flow.day == C.FESTIVAL_DAYS - 1].reset_index(drop=True)

    # conservation : Σ zones == onsite
    for s in range(S):
        g = (C.FESTIVAL_DAYS - 1) * S + s
        zsum = last[last.step == g].attendance.sum()
        # l'Entrée est du transit (file surtout) -> on compare hors file
        onsite = fl.loc[s, "onsite"]
        diff = abs((zsum - fl.loc[s, "queue"] - 0.5 * (fl.loc[s, "admitted"]
                    + fl.loc[s, "departed"])) - onsite)
        assert diff <= max(5, 0.02 * max(onsite, 1)), \
            f"conservation violée au pas {s}: |Σzones - onsite|={diff:.0f}"

    peak = fl.onsite.max()
    peak_s = int(fl.onsite.idxmax())
    # arrivées (intention) dans la fenêtre 16h-18h (pas 24..31) — ancrage étude
    arr = fl.arrived.to_numpy()
    frac_16_18 = arr[24:32].sum() / max(arr.sum(), 1)
    # T90 egress après la tête d'affiche
    hl_end = int(C.HEADLINER_END_MIN // C.STEP_MINUTES)
    post = fl.onsite.to_numpy()[hl_end:]
    base = post[0]
    campers = int(round(C.PEAK_POPULATION * C.DAY_TURNOVER * C.VISITOR_MIX["camper"]))
    leavers = max(base - campers, 1)
    t90 = next((k for k in range(len(post))
                if base - post[k] >= 0.9 * leavers), len(post) - 1) * C.STEP_MINUTES

    def clk(s):
        mm = int(10 * 60 + s * C.STEP_MINUTES)
        return f"{mm//60:02d}:{mm%60:02d}"

    print("Modèle de population — contrôles OK (dernier jour)")
    print(f"  population au pic      : {peak:.0f} à {clk(peak_s)} "
          f"(cible {C.PEAK_POPULATION})")
    print(f"  arrivées 16h-18h       : {frac_16_18*100:.0f} % (+ ruée "
          f"pré-headliner ~20h ; ancrage étude ~50 %)")
    print(f"  file d'attente max     : {fl.queue.max():.0f} pers.")
    print(f"  egress T90 après 22h30 : {t90:.0f} min")
    print(f"  population à minuit     : {fl.onsite.iloc[-1]:.0f} "
          f"(campeurs ≈ {campers})")
    for z in C.ZONES:
        col = last[last.zone == z].attendance
        print(f"  {z:12s} pic {col.max():5.0f} / cap {C.ZONE_CAPACITY[z]}")


if __name__ == "__main__":
    df, events = generate()
    flow = pd.read_csv(C.FLOW_CSV)
    print(f"attendance.csv : {len(df)} lignes ({C.TOTAL_STEPS} pas x {C.N_ZONES} zones)")
    print(f"flow.csv       : {len(flow)} pas (onsite/admis/partis/file)")
    print(f"events.csv     : {len(events)} incidents injectés\n")
    _summary(df, flow)
