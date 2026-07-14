"""
Allocation dynamique de ressources par CSP (OR-Tools CP-SAT).

Boucle de re-planification :
- déclenchement périodique (toutes les 30 min) OU événementiel
  (alerte CNN, pic prévu par le Transformer)
- contraintes DURES  : effectif total, minimum de sécurité par zone
  (réduit à 0 pour les zones basses-priorité en cas de masse d'urgences)
- contraintes SOUPLES: couverture proportionnelle à la demande,
  pénalité de réaffectation (stabilité), triage par sévérité

Sévérité des incidents (triage) :
  fallen_person    -> 3  (vie en danger immédiat)
  crowd_surge      -> 2  (risque d'escalade rapide)
  suspicious_object -> 1 (surveillance suffisante)

Robustesse : les exigences d'urgence sont des contraintes SOUPLES à forte
pénalité — le solver reste toujours faisable même si plusieurs zones sont
en crise simultanément. La solution dégradée (shortage > 0) est préférable
à une infaisabilité qui laisserait l'allocation précédente indéfiniment.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from ortools.sat.python import cp_model
import config as C

SEVERITY = {
    "fallen_person":     3,
    "crowd_surge":       2,
    "fight":             2,   # bagarre : risque d'escalade rapide (comme un surge)
    "suspicious_object": 1,
}
# pénalité par équipe manquante selon la sévérité (domaine entier : *SCALE)
EMERGENCY_PENALTY = {3: 2000, 2: 800, 1: 200}
SCALE = 100          # mise à l'échelle pour rester en entiers


def _hare_with_minimums(weights: dict[str, float]) -> dict[str, dict[str, int]]:
    """Répartit chaque ressource proportionnellement à `weights` (plus fort
    reste / Hare), puis garantit les minimums de sécurité par zone."""
    tot = sum(weights.values()) or 1.0
    alloc = {}
    for res, n in C.RESOURCES.items():
        shares = {z: n * weights[z] / tot for z in C.ZONES}
        base = {z: int(shares[z]) for z in C.ZONES}
        rem = n - sum(base.values())
        for z in sorted(C.ZONES, key=lambda z: shares[z] - base[z], reverse=True)[:rem]:
            base[z] += 1
        mn = C.MIN_STAFF_PER_ZONE[res]
        for z in C.ZONES:
            while base[z] < mn:
                donor = max(C.ZONES, key=lambda d: base[d])
                if base[donor] <= mn:
                    break
                base[donor] -= 1
                base[z] += 1
        alloc[res] = base
    return alloc


def static_allocation() -> dict[str, dict[str, int]]:
    """Plan d'équipes FIXE (postes proportionnels à la capacité des zones,
    décidés à l'ouverture, jamais réoptimisés). Conservé comme point de
    comparaison historique ; la baseline « sans » utilise désormais
    `scheduled_allocation` (planning pré-établi, bien plus réaliste)."""
    return _hare_with_minimums({z: float(C.ZONE_CAPACITY[z]) for z in C.ZONES})


def scheduled_allocation(df=None) -> list[dict[str, dict[str, int]]]:
    """PLANNING PRÉ-ÉTABLI par quart d'heure — la baseline « sans prédiction ».

    Un organisateur compétent n'a pas besoin de ML pour savoir que MainStage
    sera pleine à la tête d'affiche ou le FoodCourt à midi : il connaît le
    programme et a OBSERVÉ les jours précédents. Pour chaque pas du jour, ce
    plan répartit les équipes proportionnellement à l'affluence MOYENNE
    observée les jours précédents à la même heure (Hare + minimums de
    sécurité). Les équipes suivent ce planning scrupuleusement ; seul un
    incident les fait dévier (dépêche), puis elles REVIENNENT à leur poste.

    Ce que ce plan n'a PAS : la demande réelle du jour (météo, affluence du
    jour ≠ moyenne historique), la détection automatique, ni la granularité
    fine — un roster réel tourne par BLOCS HORAIRES, pas par quart d'heure :
    le plan est donc constant sur chaque heure (dimensionné sur la moyenne de
    l'heure) et ne peut pas suivre les rampes intra-heure. C'est exactement la
    valeur ajoutée que la comparaison avec/sans doit isoler.

    Retourne une liste de STEPS_PER_DAY allocations {res: {zone: n}}
    (la même allocation répétée sur les 4 pas de chaque heure).
    """
    import pandas as pd
    if df is None:
        df = pd.read_csv(C.DATA_CSV)
    hist = df[df.day < C.FESTIVAL_DAYS - 1].copy()   # jours PRÉCÉDENTS uniquement
    hist["tod"] = hist["step"] % C.STEPS_PER_DAY
    mean_att = hist.groupby(["tod", "zone"])["attendance"].mean()

    steps_per_hour = 60 // C.STEP_MINUTES
    plans = []
    for h0 in range(0, C.STEPS_PER_DAY, steps_per_hour):
        sids = range(h0, min(h0 + steps_per_hour, C.STEPS_PER_DAY))
        weights = {z: max(float(np.mean([mean_att.get((sid, z), 0.0)
                                         for sid in sids])), 1.0)
                   for z in C.ZONES}
        alloc = _hare_with_minimums(weights)
        plans.extend([alloc] * len(list(sids)))
    return plans


def solve_allocation(demand: dict[str, float],
                     emergencies: dict[str, list[str]] | None = None,
                     previous: dict[str, dict[str, int]] | None = None):
    """
    demand      : {zone: affluence prévue / capacité}    (issu du Transformer)
    emergencies : {zone: [types d'incident]}             (issu du CNN)
    previous    : allocation précédente pour la stabilité

    Retourne : ({res_type: {zone: n}}, status_str)
               ou (None, status_str) si vraiment infaisable (ne devrait plus arriver)
    """
    emergencies = emergencies or {}
    model = cp_model.CpModel()
    zones = C.ZONES

    # ---- sévérité maximale par zone ----
    zone_severity = {
        z: max((SEVERITY.get(k, 0) for k in kinds), default=0)
        for z, kinds in emergencies.items()
    }
    # zones en urgence haute ou moyenne -> peuvent recevoir toutes les équipes
    high_priority = {z for z, s in zone_severity.items() if s >= 2}

    x = {}
    for res, total in C.RESOURCES.items():
        for z in zones:
            x[res, z] = model.NewIntVar(0, total, f"{res}_{z}")
        # contrainte dure : somme = total disponible
        model.Add(sum(x[res, z] for z in zones) == total)
        # contrainte dure : minimum de sécurité, relâché à 0 pour zones
        # basses-priorité quand des urgences hautes mobilisent les ressources
        for z in zones:
            minimum = C.MIN_STAFF_PER_ZONE[res]
            if high_priority and z not in high_priority:
                minimum = 0     # on peut temporairement vider une zone calme
            model.Add(x[res, z] >= minimum)

    # ---- termes de l'objectif ----
    cost_terms = []

    # 1. urgences : contraintes SOUPLES (shortage pénalisé fortement)
    for z, kinds in emergencies.items():
        sev = zone_severity[z]
        pen = EMERGENCY_PENALTY[sev]
        required_med = 2 if sev >= 2 else 1
        required_sec = 2 if sev >= 2 else 1

        for res, req in [("medical", required_med), ("security", required_sec)]:
            shortage = model.NewIntVar(0, C.RESOURCES[res], f"short_{res}_{z}")
            model.Add(shortage >= req - x[res, z])
            model.Add(shortage >= 0)
            cost_terms.append(pen * SCALE * shortage)

    # 2. couverture proportionnelle à la demande
    tot_dem = sum(demand.values()) or 1.0
    for res, total in C.RESOURCES.items():
        for z in zones:
            target = round(total * SCALE * demand.get(z, 0) / tot_dem)
            dev = model.NewIntVar(0, total * SCALE, f"dev_{res}_{z}")
            model.Add(dev >= x[res, z] * SCALE - target)
            model.Add(dev >= target - x[res, z] * SCALE)
            cost_terms.append(dev)

    # 3. stabilité : pénaliser les changements d'affectation inutiles
    if previous:
        for res in C.RESOURCES:
            for z in zones:
                prev_val = previous.get(res, {}).get(z, 0)
                ch = model.NewIntVar(0, C.RESOURCES[res], f"ch_{res}_{z}")
                model.Add(ch >= x[res, z] - prev_val)
                model.Add(ch >= prev_val - x[res, z])
                cost_terms.append(C.REASSIGNMENT_PENALTY * SCALE * ch)

    model.Minimize(sum(cost_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, solver.StatusName(status)

    alloc = {res: {z: int(solver.Value(x[res, z])) for z in zones}
             for res in C.RESOURCES}

    # vérification de cohérence (garde-fou)
    for res, total in C.RESOURCES.items():
        for z in zones:
            v = alloc[res][z]
            if not (0 <= v <= total):
                return None, f"INVALID_VALUE_{res}_{z}={v}"

    return alloc, solver.StatusName(status)


if __name__ == "__main__":
    # demo : situation normale
    demand = {"MainStage": .3, "SecondStage": .3, "FoodCourt": .4,
              "Camping": .2, "Entrance": .5}
    a1, s1 = solve_allocation(demand)
    print("Situation calme :", s1)
    for r, d in a1.items():
        print(f"  {r:9s} {d}")

    # masse d'urgences simultanées (stress test)
    mass_em = {
        "MainStage":   ["fallen_person", "crowd_surge"],
        "SecondStage": ["fallen_person"],
        "FoodCourt":   ["crowd_surge"],
    }
    a2, s2 = solve_allocation(
        {"MainStage": .95, "SecondStage": .8, "FoodCourt": .7,
         "Camping": .1, "Entrance": .1},
        emergencies=mass_em, previous=a1)
    print("\nMasse d'urgences simultanées :", s2)
    for r, d in a2.items():
        print(f"  {r:9s} {d}")
    if a2 is None:
        print("  -> solver infaisable (ne devrait pas arriver)")
