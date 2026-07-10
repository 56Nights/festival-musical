"""
Allocation dynamique de ressources par CSP (OR-Tools CP-SAT).

Boucle de re-planification :
- déclenchement périodique (toutes les 30 min) OU événementiel
  (alerte CNN, pic prévu par le Transformer)
- contraintes DURES  : minimum de staff par zone, effectif total
- contraintes SOUPLES: couverture proportionnelle à la demande,
  pénalité de réaffectation (stabilité opérationnelle)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ortools.sat.python import cp_model
import config as C


def solve_allocation(demand: dict[str, float],
                     emergencies: dict[str, list[str]] | None = None,
                     previous: dict[str, dict[str, int]] | None = None):
    """
    demand      : {zone: affluence prévue / capacité}  (issu du Transformer)
    emergencies : {zone: [types d'incident]}            (issu du CNN)
    previous    : allocation précédente {res_type: {zone: n}} pour la stabilité
    Retourne    : {res_type: {zone: n}}, status
    """
    emergencies = emergencies or {}
    model = cp_model.CpModel()
    zones = C.ZONES

    x = {}  # x[res, zone] = nb d'équipes affectées
    for res, total in C.RESOURCES.items():
        for z in zones:
            x[res, z] = model.NewIntVar(0, total, f"{res}_{z}")
        # contrainte dure : tout le monde est affecté quelque part
        model.Add(sum(x[res, z] for z in zones) == total)
        # contrainte dure : minimum de sécurité par zone
        for z in zones:
            model.Add(x[res, z] >= C.MIN_STAFF_PER_ZONE[res])

    # urgence -> exigence dure renforcée dans la zone concernée
    for z, kinds in emergencies.items():
        if any(k in ("fallen_person", "crowd_surge") for k in kinds):
            model.Add(x["medical", z] >= 2)
            model.Add(x["security", z] >= 2)
        if "suspicious_object" in kinds:
            model.Add(x["security", z] >= 2)

    # ---- objectif : couverture proportionnelle + stabilité ----
    terms = []
    SCALE = 100
    for res, total in C.RESOURCES.items():
        tot_dem = sum(demand.values()) or 1.0
        for z in zones:
            target = round(total * SCALE * demand.get(z, 0) / tot_dem)
            dev = model.NewIntVar(0, total * SCALE, f"dev_{res}_{z}")
            model.Add(dev >= x[res, z] * SCALE - target)
            model.Add(dev >= target - x[res, z] * SCALE)
            terms.append(dev)

            if previous and z in previous.get(res, {}):
                ch = model.NewIntVar(0, total, f"ch_{res}_{z}")
                prev = previous[res][z]
                model.Add(ch >= x[res, z] - prev)
                model.Add(ch >= prev - x[res, z])
                terms.append(C.REASSIGNMENT_PENALTY * SCALE * ch)

    model.Minimize(sum(terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    status = solver.Solve(model)

    alloc = {res: {z: int(solver.Value(x[res, z])) for z in C.ZONES}
             for res in C.RESOURCES}
    return alloc, solver.StatusName(status)


if __name__ == "__main__":
    # démo : situation calme puis urgence
    calm = {"MainStage": .3, "SecondStage": .3, "FoodCourt": .4,
            "Camping": .2, "Entrance": .5}
    a1, s1 = solve_allocation(calm)
    print("Allocation calme :", s1)
    for r, d in a1.items():
        print(f"  {r:9s} {d}")

    surge = dict(calm, MainStage=.95)
    a2, s2 = solve_allocation(surge, {"MainStage": ["fallen_person"]}, a1)
    print("\nAllocation urgence MainStage :", s2)
    for r, d in a2.items():
        print(f"  {r:9s} {d}")
