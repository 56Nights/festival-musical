"""
Pipeline intégré — le cœur du système intelligent.

Boucle de contrôle (par pas de 15 min) :

  1. TimesFM      -> prévision d'affluence à 2h par zone (zéro-shot)
  2. CNN          -> analyse frame : densité, chute, objet suspect
  3. Optical flow -> détection précoce de mouvement de masse (bousculade)
  4. Fusion       -> 2 signaux sur 3 actifs = alerte bousculade
  5. CSP dynamique-> ré-allocation si déclencheur périodique OU événement
  6. Journal complet -> dashboard + narration LLM

Ajout flux optique (Compétence 3) :
  Le CNN analyse des frames isolées — il détecte la bousculade APRÈS que des
  personnes sont tombées. Le flux optique détecte le mouvement de masse AVANT,
  dès que la foule commence à fuir dans une direction cohérente. Les deux
  signaux sont complémentaires : flux optique = alerte précoce,
  CNN fallen = confirmation.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import numpy as np
import pandas as pd
import torch
import cv2

import config as C
from forecasting.timesfm_forecaster import ZeroShotForecaster
from vision.model import MultiTaskCrowdCNN
from vision.synthetic_images import make_frame
from vision.optical_flow import StampedeDetector
from allocation.dynamic_csp import solve_allocation


def load_models():
    forecaster = ZeroShotForecaster()
    cnn = MultiTaskCrowdCNN(pretrained=True)
    cnn.load_state_dict(torch.load(C.VISION_MODEL, weights_only=True))
    cnn.eval()
    return forecaster, cnn


def _simulate_motion(frame_np: np.ndarray, density: float,
                     is_stampede: bool) -> np.ndarray:
    """
    Simule le mouvement inter-frames pour le flux optique.
    Bousculade  -> translation globale cohérente (fuite)
    Situation normale -> légère translation aléatoire (mouvement naturel)
    """
    if not is_stampede:
        shift_x = np.random.uniform(-0.5, 0.5)
        shift_y = np.random.uniform(-0.5, 0.5)
    else:
        shift_x = np.random.uniform(4, 7) * density
        shift_y = np.random.uniform(2, 4) * density

    h, w = C.IMG_SIZE, C.IMG_SIZE
    f_hwc = (frame_np.transpose(1, 2, 0) * 255).astype(np.uint8)
    M = np.float32([[1, 0, shift_x], [0, 1, shift_y]])
    moved = cv2.warpAffine(f_hwc, M, (w, h))
    return (moved.astype(np.float32) / 255).transpose(2, 0, 1)


def _alloc_moves(prev, new):
    """Nombre total de mouvements d'équipe entre deux allocations (somme des
    |Δ| par ressource/zone, /2 car un départ = une arrivée). Sert à l'hystérésis."""
    if prev is None or new is None:
        return 10 ** 9
    total = 0
    for res in new:
        for z in new[res]:
            total += abs(new[res][z] - prev.get(res, {}).get(z, 0))
    return total // 2


def _window(start_step, n_steps):
    if start_step is None:
        start_step = C.TOTAL_STEPS - C.STEPS_PER_DAY
    if n_steps is None:
        n_steps = C.STEPS_PER_DAY
    return start_step, n_steps


def run_reactive_loop(start_step: int = None, n_steps: int = None):
    """Scénario « SANS gestion prédictive » (baseline de comparaison).

    Aucun modèle, mais un ORGANISATEUR COMPÉTENT : les équipes suivent un
    PLANNING PRÉ-ÉTABLI par quart d'heure (`scheduled_allocation`), construit
    sur l'affluence observée les jours précédents à la même heure — il « sait »
    donc que MainStage sature à la tête d'affiche et le FoodCourt aux repas.
    Elles le suivent scrupuleusement ; un incident les dépêche (modélisé en aval
    par `kpis.py`) puis elles reviennent à leur poste. Pas de vision (détection
    HUMAINE) ni d'ajustement à la demande réelle du jour. On journalise la
    vérité terrain des incidents pour que l'évaluateur rejoue les MÊMES
    incidents que le scénario prédictif.
    """
    from allocation.dynamic_csp import scheduled_allocation
    events = pd.read_csv(C.EVENTS_CSV)
    start_step, n_steps = _window(start_step, n_steps)
    plans = scheduled_allocation()
    log = []
    for step in range(start_step, min(start_step + n_steps, C.TOTAL_STEPS)):
        truth = events[events["step"] == step]
        log.append({
            "step": step, "alerts": [], "resolved": False,
            "trigger": None, "forecast_peak": {},
            "truth_incidents": [{"zone": r.zone, "type": r.type}
                                for r in truth.itertuples()],
            "allocation": plans[step % C.STEPS_PER_DAY],
            "solver_status": "SCHEDULED",
        })
    with open(os.path.join(C.OUT, "control_log_reactive.json"), "w") as f:
        json.dump(log, f, indent=1)
    return log


def run_control_loop(start_step: int = None, n_steps: int = None,
                     mode: str = "predictive"):
    """Rejoue le dernier jour COMPLET du festival (10h -> minuit, 56 pas).

    mode="predictive" : pipeline complet (prévision + vision + CSP dynamique).
    mode="reactive"   : baseline sans gestion prédictive (cf. run_reactive_loop).

    L'historique des deux jours précédents (>> SEQ_LEN) reste disponible pour
    la prévision TimesFM.
    """
    if mode == "reactive":
        return run_reactive_loop(start_step, n_steps)
    df = pd.read_csv(C.DATA_CSV)
    events = pd.read_csv(C.EVENTS_CSV)
    forecaster, cnn = load_models()
    stampede_detector = StampedeDetector()

    series = {z: (df[df.zone == z].sort_values("step").attendance
                  / C.ZONE_CAPACITY[z]).to_numpy() for z in C.ZONES}

    if start_step is None:
        start_step = C.TOTAL_STEPS - C.STEPS_PER_DAY   # début du dernier jour
    if n_steps is None:
        n_steps = C.STEPS_PER_DAY                       # journée entière

    log = []
    prev_alloc = None
    n_fp_suppressed = [0]        # faux positifs fallen filtrés par le gate (mutable)

    for step in range(start_step, min(start_step + n_steps, C.TOTAL_STEPS)):
        entry = {"step": step, "alerts": [], "resolved": False}

        # ---- 1. prévision par zone (TimesFM zéro-shot) ----
        forecasts = {}
        for z in C.ZONES:
            pred = forecaster.forecast(series[z][:step], at_step=step)
            forecasts[z] = float(np.max(pred))
        entry["forecast_peak"] = {z: round(v, 3) for z, v in forecasts.items()}

        # ---- 2+3. CNN + flux optique par zone ----
        truth = events[events["step"] == step]
        # vérité terrain des incidents de ce pas (pour la vue simulation :
        # permet de distinguer visuellement détecté vs manqué)
        entry["truth_incidents"] = [
            {"zone": r.zone, "type": r.type} for r in truth.itertuples()]
        emergencies = {}

        with torch.no_grad():
            for z in C.ZONES:
                real_density = float(np.clip(series[z][step], 0, 1))
                inc = truth[truth["zone"] == z]["type"].tolist()
                is_stampede_gt = "crowd_surge" in inc

                # frame courante (synthétique)
                frame_np = make_frame(
                    density=real_density,
                    fallen="fallen_person" in inc or is_stampede_gt,
                    obj="suspicious_object" in inc)

                # frame de ce pas APRÈS mouvement (déplacement intra-pas simulé)
                moved_np = _simulate_motion(frame_np, real_density,
                                            is_stampede_gt)

                # --- CNN ---
                frame_t = torch.tensor(frame_np).unsqueeze(0)
                out = cnn(frame_t)
                cnn_density  = float(out["density"].item())
                cnn_fallen   = torch.sigmoid(out["fallen"]).item() > C.CNN_FALLEN_THRESHOLD
                cnn_object   = torch.sigmoid(out["object"]).item() > C.CNN_OBJECT_THRESHOLD

                # --- flux optique + fusion ---
                # on mesure le mouvement INTRA-pas (frame de base -> frame déplacée) :
                # calme = micro-jitter (pas d'alerte), bousculade = fuite cohérente.
                # Comparer des pas successifs (frames générées indépendamment)
                # produirait un flux parasite -> faux positifs.
                flow_result = stampede_detector.analyze(
                    z, moved_np, cnn_density, cnn_fallen, prev_frame=frame_np)

                # construction des kinds d'alerte
                kinds = []
                fallback_surge = False
                # GATE DE PLAUSIBILITÉ : une « personne au sol » dans une zone
                # quasi vide est physiquement improbable -> on la supprime (c'est
                # la principale source de faux positifs du CNN).
                if cnn_fallen and cnn_density >= C.FALLEN_MIN_DENSITY:
                    kinds.append("fallen_person")
                elif cnn_fallen:
                    n_fp_suppressed[0] += 1        # faux positif filtré (compteur)
                if cnn_object:
                    kinds.append("suspicious_object")
                if flow_result["stampede_alert"]:
                    kinds.append("crowd_surge")   # corroboré par la fusion 2/3
                elif cnn_density > C.DENSITY_ALERT_THRESHOLD:
                    kinds.append("crowd_surge")   # fallback densité seule
                    fallback_surge = True

                if kinds:
                    active = flow_result["active_signals"]
                    confirmed = active >= C.CORROBORATION_MIN_SIGNALS
                    # VEILLE DENSITÉ : un surge issu du seul seuil de densité, non
                    # corroboré et sans autre type, n'est PAS une affirmation
                    # d'incident (« il y a une bousculade ») mais une veille (« zone
                    # dense, pré-positionner »). Elle informe la couverture via la
                    # prévision mais ne déclenche pas le triage d'urgence CSP et
                    # n'entre pas dans la précision/rappel d'INCIDENTS.
                    is_watch = (fallback_surge and not confirmed
                                and kinds == ["crowd_surge"])
                    if not is_watch:
                        emergencies[z] = kinds
                    entry["alerts"].append({
                        "zone": z, "types": kinds,
                        "density": round(cnn_density, 2),
                        "confidence": "confirmé" if confirmed else "à vérifier",
                        "watch": is_watch,
                        "flow": {
                            "magnitude": flow_result["flow"]["mean_magnitude"]
                                         if flow_result["flow"] else None,
                            "coherence": flow_result["flow"]["coherence"]
                                         if flow_result["flow"] else None,
                            "active_signals": active,
                        }
                    })

        # ---- 4. CSP dynamique ----
        periodic = (step - start_step) % C.RESOLVE_EVERY_STEPS == 0
        forecast_spike = any(v > C.DENSITY_ALERT_THRESHOLD
                             for v in forecasts.values())
        if periodic or emergencies or forecast_spike:
            new_alloc, status = solve_allocation(forecasts, emergencies,
                                                 prev_alloc)
            if new_alloc is not None:
                # HYSTÉRÉSIS : hors urgence, on ignore les changements marginaux
                # (bruit de prévision) pour ne pas déplacer les équipes pour rien.
                moves = _alloc_moves(prev_alloc, new_alloc)
                if (emergencies or prev_alloc is None
                        or moves >= C.ALLOC_HYSTERESIS_MOVES):
                    prev_alloc = new_alloc
                # sinon : on conserve prev_alloc (changement jugé non significatif)
            else:
                print(f"[CSP] step {step} : {status}, "
                      f"allocation précédente conservée")
            entry["resolved"] = True
            entry["trigger"] = ("event"    if emergencies else
                                "forecast" if forecast_spike else "periodic")
            entry["allocation"]    = prev_alloc
            entry["solver_status"] = status
        else:
            entry["allocation"] = prev_alloc

        log.append(entry)

    metrics = alert_quality(log, n_fp_suppressed[0])
    with open(os.path.join(C.OUT, "control_log.json"), "w") as f:
        json.dump(log, f, indent=1)
    with open(os.path.join(C.OUT, "alert_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=1)
    return log


# types réellement détectables par la CAMÉRA (les bagarres sont vues par la
# sécurité, pas le CNN -> hors du calcul de précision/rappel caméra).
CAMERA_TYPES = {"fallen_person", "suspicious_object", "crowd_surge"}


def alert_quality(log, n_fp_suppressed=0, tol_steps=1):
    """Précision / rappel du détecteur caméra contre la vérité terrain.

    On distingue les AFFIRMATIONS D'INCIDENT (alertes non-veille) des VEILLES
    densité (pré-positionnement, pas un incident). La précision/rappel porte sur
    les affirmations d'incident ; les veilles sont comptées à part. On rapporte
    aussi les faux positifs déjà SUPPRIMÉS par le gate de plausibilité — métrique
    honnête, pas seulement l'exactitude in-distribution.
    """
    truth = set()
    for e in log:
        for t in e.get("truth_incidents", []):
            if t["type"] in CAMERA_TYPES:
                truth.add((e["step"], t["zone"], t["type"]))

    def matches(step, zone, typ):
        return any((step + d, zone, typ) in truth
                   for d in range(-tol_steps, tol_steps + 1))

    tp = fp = n_incident_alerts = n_watch = 0
    for e in log:
        for a in e["alerts"]:
            if a.get("watch"):
                n_watch += 1
                continue
            for typ in a["types"]:
                if typ not in CAMERA_TYPES:
                    continue
                n_incident_alerts += 1
                if matches(e["step"], a["zone"], typ):
                    tp += 1
                else:
                    fp += 1
    matched_truth = sum(1 for (st, z, ty) in truth
                        if any(any(ty in a["types"] and a["zone"] == z
                                   and not a.get("watch")
                                   for a in e["alerts"])
                               for e in log if abs(e["step"] - st) <= tol_steps))
    n_truth = len(truth)
    precision = tp / max(tp + fp, 1)
    recall = matched_truth / max(n_truth, 1)
    return {
        "n_incident_alerts": n_incident_alerts,
        "n_density_watches": n_watch,
        "n_truth_camera": n_truth,
        "true_positives": tp,
        "false_positives": fp,
        "fp_suppressed_by_gate": n_fp_suppressed,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "incident_alert_to_truth_ratio": round(n_incident_alerts / max(n_truth, 1), 2),
    }


if __name__ == "__main__":
    log = run_control_loop()
    n_alerts   = sum(len(e["alerts"]) for e in log)
    n_resolves = sum(e["resolved"] for e in log)
    m = alert_quality(log)
    print(f"{len(log)} pas simulés | {n_alerts} alertes | "
          f"{n_resolves} ré-allocations")
    print(f"Qualité caméra : précision {m['precision']:.0%}  rappel {m['recall']:.0%} "
          f"| {m['n_incident_alerts']} affirmations d'incident pour "
          f"{m['n_truth_camera']} réels (ratio {m['incident_alert_to_truth_ratio']}:1), "
          f"{m['false_positives']} faux positifs | "
          f"{m['n_density_watches']} veilles densité | "
          f"{m['fp_suppressed_by_gate']} FP supprimés par le gate")
    for e in log:
        if e["alerts"]:
            for a in e["alerts"]:
                flow = a.get("flow", {})
                print(f"  step {e['step']} {a['zone']:12s} "
                      f"[{a.get('confidence','?'):10s}] "
                      f"signals={flow.get('active_signals','?')}/3 "
                      f"-> {a['types']}")
