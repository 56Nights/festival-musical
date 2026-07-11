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


def _window(start_step, n_steps):
    if start_step is None:
        start_step = C.TOTAL_STEPS - C.STEPS_PER_DAY
    if n_steps is None:
        n_steps = C.STEPS_PER_DAY
    return start_step, n_steps


def run_reactive_loop(start_step: int = None, n_steps: int = None):
    """Scénario « SANS gestion prédictive » (baseline de comparaison).

    Aucun modèle : pas de prévision (donc aucun pré-positionnement), pas de
    vision (la détection sera HUMAINE, modélisée en aval par `kpis.py`). Le plan
    d'équipes est FIXE toute la journée (`static_allocation`). On journalise
    quand même la vérité terrain des incidents pour que l'évaluateur rejoue les
    MÊMES incidents que le scénario prédictif.
    """
    from allocation.dynamic_csp import static_allocation
    events = pd.read_csv(C.EVENTS_CSV)
    start_step, n_steps = _window(start_step, n_steps)
    alloc = static_allocation()
    log = []
    for step in range(start_step, min(start_step + n_steps, C.TOTAL_STEPS)):
        truth = events[events["step"] == step]
        log.append({
            "step": step, "alerts": [], "resolved": False,
            "trigger": None, "forecast_peak": {},
            "truth_incidents": [{"zone": r.zone, "type": r.type}
                                for r in truth.itertuples()],
            "allocation": alloc, "solver_status": "STATIC",
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

    for step in range(start_step, min(start_step + n_steps, C.TOTAL_STEPS)):
        entry = {"step": step, "alerts": [], "resolved": False}

        # ---- 1. prévision par zone (TimesFM zéro-shot) ----
        forecasts = {}
        for z in C.ZONES:
            pred = forecaster.forecast(series[z][:step])
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

                # frame précédente simulée avec mouvement
                moved_np = _simulate_motion(frame_np, real_density,
                                            is_stampede_gt)

                # --- CNN ---
                frame_t = torch.tensor(frame_np).unsqueeze(0)
                out = cnn(frame_t)
                cnn_density  = float(out["density"].item())
                cnn_fallen   = torch.sigmoid(out["fallen"]).item() > 0.5
                cnn_object   = torch.sigmoid(out["object"]).item() > 0.5

                # --- flux optique + fusion ---
                flow_result = stampede_detector.analyze(
                    z, moved_np, cnn_density, cnn_fallen)

                # construction des kinds d'alerte
                kinds = []
                if cnn_fallen:
                    kinds.append("fallen_person")
                if cnn_object:
                    kinds.append("suspicious_object")
                if flow_result["stampede_alert"]:
                    kinds.append("crowd_surge")
                elif cnn_density > C.DENSITY_ALERT_THRESHOLD:
                    kinds.append("crowd_surge")   # fallback density seule

                if kinds:
                    emergencies[z] = kinds
                    entry["alerts"].append({
                        "zone": z, "types": kinds,
                        "density": round(cnn_density, 2),
                        "flow": {
                            "magnitude": flow_result["flow"]["mean_magnitude"]
                                         if flow_result["flow"] else None,
                            "coherence": flow_result["flow"]["coherence"]
                                         if flow_result["flow"] else None,
                            "active_signals": flow_result["active_signals"],
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
                prev_alloc = new_alloc
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

    with open(os.path.join(C.OUT, "control_log.json"), "w") as f:
        json.dump(log, f, indent=1)
    return log


if __name__ == "__main__":
    log = run_control_loop()
    n_alerts   = sum(len(e["alerts"]) for e in log)
    n_resolves = sum(e["resolved"] for e in log)
    print(f"{len(log)} pas simulés | {n_alerts} alertes | "
          f"{n_resolves} ré-allocations")
    for e in log:
        if e["alerts"]:
            for a in e["alerts"]:
                flow = a.get("flow", {})
                print(f"  step {e['step']} {a['zone']:12s} "
                      f"signals={flow.get('active_signals','?')}/3 "
                      f"-> {a['types']}")
