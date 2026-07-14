"""
Flux optique par apprentissage profond (RAFT) pour vidéo réelle.

RAFT (Recurrent All-Pairs Field Transforms, ECCV 2020) est un modèle de flux
optique entraîné sur des données réelles. Contrairement à Farneback (méthode
classique), il gère :
  - les grands déplacements (mouvement rapide de foule)
  - les occlusions (personnes qui se croisent)
  - les changements d'éclairage (concerts, nuit)

Justification (Compétence 3) :
  Le flux optique classique (Farneback) est sensible aux paramètres caméra et
  peu robuste sur vidéo réelle. RAFT, pré-entraîné (Sintel/KITTI), fournit un
  champ de déplacement dense de bien meilleure qualité, sans entraînement de
  notre part. On conserve ensuite les MÊMES caractéristiques de haut niveau
  (compensation caméra, alignement, fraction mobile) calculées sur ce champ.

Repli : si RAFT ne peut être chargé (pas de réseau, machine trop faible),
le module retombe automatiquement sur Farneback (vision/stampede_flow.py).
"""
import numpy as np
import torch
import cv2

_RAFT = None
_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# seuils — RAFT donne des magnitudes différentes de Farneback, recalibrés
MAG_THRESHOLD         = 3.0
ALIGNMENT_THRESHOLD   = 0.6
MOVING_FRAC_THRESHOLD  = 0.25
PERSISTENCE_FRAMES    = 5
PROCESS_WIDTH         = 480     # RAFT exige des dimensions multiples de 8


def _load_raft():
    global _RAFT
    if _RAFT is not None:
        return _RAFT
    try:
        from torchvision.models.optical_flow import raft_small, Raft_Small_Weights
        model = raft_small(weights=Raft_Small_Weights.DEFAULT, progress=False)
        model = model.eval().to(_DEVICE)
        _RAFT = model
        print(f"[RAFT] modèle chargé sur {_DEVICE}")
    except Exception as exc:
        print(f"[RAFT] indisponible ({type(exc).__name__}) -> repli Farneback")
        _RAFT = False
    return _RAFT


def _prep(frame_bgr: np.ndarray, width: int) -> torch.Tensor:
    """BGR uint8 -> tensor RAFT (1,3,H,W) normalisé [-1,1], dims multiples de 8."""
    h, w = frame_bgr.shape[:2]
    nw = width
    nh = int(h * width / w)
    nh -= nh % 8
    nw -= nw % 8
    rgb = cv2.cvtColor(cv2.resize(frame_bgr, (nw, nh)), cv2.COLOR_BGR2RGB)
    t = torch.tensor(rgb).permute(2, 0, 1).float() / 255.0
    t = (t - 0.5) / 0.5                       # [-1, 1]
    return t.unsqueeze(0).to(_DEVICE)


def raft_flow(prev_bgr: np.ndarray, curr_bgr: np.ndarray,
              width: int = PROCESS_WIDTH) -> np.ndarray | None:
    """Champ de flux dense (H,W,2) via RAFT, ou None si indisponible."""
    model = _load_raft()
    if not model:
        return None
    with torch.no_grad():
        a = _prep(prev_bgr, width)
        b = _prep(curr_bgr, width)
        flow = model(a, b)[-1]                 # dernière itération récurrente
    return flow[0].permute(1, 2, 0).cpu().numpy()


def flow_features_from_field(flow: np.ndarray) -> dict:
    """Mêmes caractéristiques que le module classique, sur un champ RAFT."""
    camera = np.median(flow.reshape(-1, 2), axis=0)
    residual = flow - camera
    mag = np.linalg.norm(residual, axis=2)
    moving = mag > 1.0
    moving_frac = float(moving.mean())
    if moving.sum() > 100:
        vecs = residual[moving]
        mean_speed = float(np.linalg.norm(vecs, axis=1).mean())
        alignment = float(np.linalg.norm(vecs.mean(axis=0)) / (mean_speed + 1e-6))
        res_mag = float(mag[moving].mean())
    else:
        alignment, res_mag = 0.0, 0.0
    candidate = (res_mag > MAG_THRESHOLD
                 and alignment > ALIGNMENT_THRESHOLD
                 and moving_frac > MOVING_FRAC_THRESHOLD)
    return {"res_mag": round(res_mag, 2), "alignment": round(alignment, 2),
            "moving_frac": round(moving_frac, 2), "candidate": candidate}


class RaftStampedeDetector:
    """
    Détecteur de bousculade utilisant RAFT (repli Farneback automatique).
    Interface identique à RealVideoStampedeDetector : .update(frame_bgr).
    """

    def __init__(self, persistence: int = PERSISTENCE_FRAMES,
                 process_width: int = PROCESS_WIDTH):
        self.persistence = persistence
        self.process_width = process_width
        self._prev_bgr = None
        self._consecutive = 0
        self.backend = "raft" if _load_raft() else "farneback"
        if self.backend == "farneback":
            from vision.stampede_flow import compute_flow_features
            self._farneback_feats = compute_flow_features
            self._prev_gray = None

    def update(self, frame_bgr: np.ndarray) -> dict:
        feats = None
        if self.backend == "raft":
            if self._prev_bgr is not None:
                field = raft_flow(self._prev_bgr, frame_bgr, self.process_width)
                if field is not None:
                    feats = flow_features_from_field(field)
            self._prev_bgr = frame_bgr.copy()
        else:                                   # repli Farneback
            h, w = frame_bgr.shape[:2]
            if w > self.process_width:
                frame_bgr = cv2.resize(
                    frame_bgr,
                    (self.process_width, int(h * self.process_width / w)))
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            if self._prev_gray is not None:
                feats = self._farneback_feats(self._prev_gray, gray)
            self._prev_gray = gray

        self._consecutive = self._consecutive + 1 \
            if (feats and feats["candidate"]) else 0
        return {"flow": feats, "consecutive": self._consecutive,
                "backend": self.backend,
                "stampede_alert": self._consecutive >= self.persistence}

    def reset(self):
        self._prev_bgr = None
        self._consecutive = 0
        if self.backend == "farneback":
            self._prev_gray = None


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    print(f"Device : {_DEVICE}")
    det = RaftStampedeDetector()
    print(f"Backend actif : {det.backend}")
