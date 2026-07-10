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

from ortools.sat.python import cp_model
import config as C

SEVERITY = {
    "fallen_person":     3,
    "crowd_surge":       2,
    "suspicious_object": 1,
}
# pénalité par équipe manquante selon la sévérité (domaine entier : *SCALE)
EMERGENCY_PENALTY = {3: 2000, 2: 800, 1: 200}
SCALE = 100          # mise à l'échelle pour rester en entiers


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
