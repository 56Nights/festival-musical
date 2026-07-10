"""
Détection de mouvement de foule par flux optique (optical flow).

Justification (Compétence 3) :
- Le CNN analyse des frames ISOLÉES — il n'a aucune notion de mouvement.
- Le flux optique mesure le DÉPLACEMENT des pixels entre deux frames
  consécutives, capturant ainsi la signature temporelle d'une bousculade :
    * magnitude élevée  -> mouvement rapide (panique)
    * cohérence directionnelle -> tout le monde fuit dans la même direction
  Ces deux conditions simultanées = bousculade, détectable AVANT que des
  personnes tombent (signal précoce vs signal tardif du CNN fallen_person).

Algorithme : Farneback dense optical flow (OpenCV) — classique, robuste,
pas d'entraînement requis, 5 ms/frame sur CPU.

Les trois signaux sont ensuite fusionnés :
  optical_flow  -> alerte précoce (mouvement de masse)
  CNN density   -> confirmation (foule dense)
  CNN fallen    -> confirmation tardive (victimes au sol)
2 signaux sur 3 actifs -> alerte bousculade émise.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import cv2
import config as C

# seuils (calibrés sur frames synthétiques 64x64 — à ajuster sur données réelles)
MAGNITUDE_THRESHOLD   = 2.0    # pixels/frame — calibré sur frames synthétiques 64x64
COHERENCE_THRESHOLD   = 0.70   # part des vecteurs alignés avec direction dominante


def _to_gray_uint8(frame: np.ndarray) -> np.ndarray:
    """Convertit un frame (C,H,W) float32 [0,1] en (H,W) uint8."""
    if frame.ndim == 3 and frame.shape[0] in (1, 3):
        frame = frame.transpose(1, 2, 0)          # CHW -> HWC
    gray = cv2.cvtColor((frame * 255).astype(np.uint8),
                        cv2.COLOR_RGB2GRAY) if frame.ndim == 3 \
           else (frame * 255).astype(np.uint8)
    return gray


def compute_optical_flow(prev_frame: np.ndarray,
                         curr_frame: np.ndarray) -> dict:
    """
    Calcule le flux optique dense entre deux frames consécutives.

    Retourne un dict avec :
      mean_magnitude  : vitesse moyenne de déplacement (pixels/frame)
      coherence       : fraction de vecteurs alignés avec direction dominante
      dominant_angle  : direction dominante du mouvement (degrés)
      stampede        : bool — True si les deux seuils sont dépassés
    """
    prev_g = _to_gray_uint8(prev_frame)
    curr_g = _to_gray_uint8(curr_frame)

    flow = cv2.calcOpticalFlowFarneback(
        prev_g, curr_g, None,
        pyr_scale=0.5, levels=3, winsize=10,
        iterations=3, poly_n=5, poly_sigma=1.2, flags=0)

    magnitude, angle = cv2.cartToPolar(flow[..., 0], flow[..., 1],
                                       angleInDegrees=True)
    mean_mag = float(magnitude.mean())

    # cohérence : fraction des vecteurs dans un cone de ±45° autour du dominant
    dominant = float(np.median(angle[magnitude > 0.5])) if mean_mag > 0.3 else 0.0
    diff = np.abs(angle - dominant) % 360
    diff = np.minimum(diff, 360 - diff)
    coherence = float((diff < 45).mean())

    return {
        "mean_magnitude": round(mean_mag, 3),
        "coherence":      round(coherence, 3),
        "dominant_angle": round(dominant, 1),
        "stampede":       mean_mag > MAGNITUDE_THRESHOLD
                          and coherence > COHERENCE_THRESHOLD,
    }


class StampedeDetector:
    """
    Fusionne les trois signaux pour émettre une alerte bousculade :
      1. flux optique  (mouvement de masse rapide et cohérent)
      2. densité CNN   (foule déjà dense)
      3. fallen CNN    (personnes au sol)

    Règle de fusion : 2 signaux sur 3 actifs -> alerte.
    Cela évite les faux positifs (public qui danse = flux élevé mais pas dense)
    et les faux négatifs (caméra floue = flux faible malgré la panique).
    """

    def __init__(self, density_threshold: float = C.DENSITY_ALERT_THRESHOLD):
        self.density_threshold = density_threshold
        self._prev_frames: dict[str, np.ndarray | None] = {
            z: None for z in C.ZONES}

    def analyze(self, zone: str, frame: np.ndarray,
                cnn_density: float, cnn_fallen: bool) -> dict:
        """
        zone        : nom de la zone caméra
        frame       : frame courante (C,H,W) float32
        cnn_density : sortie tête densité du CNN (0..1)
        cnn_fallen  : sortie tête fallen_person du CNN (bool)

        Retourne un dict d'analyse complet pour cette zone / ce pas de temps.
        """
        result = {
            "zone": zone,
            "flow": None,
            "signals": {"flow": False, "density": False, "fallen": False},
            "active_signals": 0,
            "stampede_alert": False,
        }

        prev = self._prev_frames[zone]
        if prev is not None:
            flow = compute_optical_flow(prev, frame)
            result["flow"] = flow
            result["signals"]["flow"] = flow["stampede"]

        result["signals"]["density"] = cnn_density > self.density_threshold
        result["signals"]["fallen"]  = cnn_fallen

        active = sum(result["signals"].values())
        result["active_signals"]  = active
        result["stampede_alert"]  = active >= 2

        self._prev_frames[zone] = frame.copy()
        return result


if __name__ == "__main__":
    import torch
    from vision.synthetic_images import make_frame

    detector = StampedeDetector()
    print("=== test flux optique ===\n")

    # --- situation calme : personnes statiques ---
    f1 = make_frame(density=0.4, fallen=False, obj=False)
    f2 = make_frame(density=0.4, fallen=False, obj=False)   # peu de mouvement
    flow = compute_optical_flow(f1, f2)
    print(f"Situation calme   -> magnitude={flow['mean_magnitude']:.3f}  "
          f"cohérence={flow['coherence']:.3f}  stampede={flow['stampede']}")

    # --- bousculade simulée : ajout d'un décalage global ---
    h, w = C.IMG_SIZE, C.IMG_SIZE
    M = np.float32([[1, 0, 6], [0, 1, 4]])          # translation 6px droite, 4px bas
    f1_g = (f1.transpose(1,2,0) * 255).astype(np.uint8)
    f2_rush = cv2.warpAffine(f1_g, M, (w, h))
    f2_rush = (f2_rush.astype(np.float32) / 255).transpose(2,0,1)
    flow2 = compute_optical_flow(f1, f2_rush)
    print(f"Bousculade simulée-> magnitude={flow2['mean_magnitude']:.3f}  "
          f"cohérence={flow2['coherence']:.3f}  stampede={flow2['stampede']}")

    # --- fusion trois signaux ---
    print("\n=== test fusion ===")
    f_curr = torch.tensor(f2_rush).unsqueeze(0)
    res = detector.analyze("MainStage", f2_rush,
                           cnn_density=0.90, cnn_fallen=True)
    print(f"Signaux actifs : {res['active_signals']}/3  "
          f"-> alerte bousculade : {res['stampede_alert']}")
    print(f"Détail : {res['signals']}")
