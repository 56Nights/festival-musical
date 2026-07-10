"""
Génération de frames synthétiques vues de dessus (64x64).

- La foule = points/ellipses verticales ("personnes debout").
- Personne au sol = ellipse horizontale allongée (signature distinctive).
- Objet suspect = petit segment fin très clair (proxy visuel de la seringue,
  clairement identifié comme POC synthétique dans le rapport).

Cela permet de démontrer le pipeline complet (données -> entraînement ->
inférence -> alerte) sans dataset réel, conformément au cadre simulé du sujet.
"""
import numpy as np
import torch

rng = np.random.default_rng(7)
IMG = 64


def _draw_ellipse(img, cx, cy, rx, ry, val):
    y, x = np.ogrid[:IMG, :IMG]
    mask = ((x - cx) / max(rx, 1e-6)) ** 2 + ((y - cy) / max(ry, 1e-6)) ** 2 <= 1
    img[mask] = np.clip(img[mask] + val, 0, 1)


def make_frame(density: float, fallen: bool, obj: bool):
    """density in [0,1] -> nombre de personnes dessinées."""
    img = np.zeros((IMG, IMG), dtype=np.float32)
    img += rng.normal(0.08, 0.02, img.shape).clip(0)      # sol / bruit

    n_people = int(3 + density * 90)
    for _ in range(n_people):
        cx, cy = rng.uniform(3, IMG - 3, 2)
        _draw_ellipse(img, cx, cy, rx=1.2, ry=2.6, val=rng.uniform(0.4, 0.7))

    if fallen:  # ellipse horizontale, plus grande
        cx, cy = rng.uniform(8, IMG - 8, 2)
        _draw_ellipse(img, cx, cy, rx=5.5, ry=1.8, val=0.95)

    if obj:     # petit motif clair en croix (proxy d'objet fin réfléchissant)
        cx, cy = int(rng.uniform(8, IMG - 8)), int(rng.uniform(8, IMG - 8))
        img[cy - 1: cy + 2, cx - 5: cx + 5] = 1.0
        img[cy - 4: cy + 4, cx - 1: cx + 2] = 1.0

    rgb = np.stack([img, img * rng.uniform(0.85, 1.0), img * 0.9])
    return rgb.astype(np.float32)


def make_dataset(n: int = 800):
    X, yd, yf, yo = [], [], [], []
    for _ in range(n):
        d = rng.uniform(0, 1)
        f = rng.random() < 0.3
        o = rng.random() < 0.25
        X.append(make_frame(d, f, o))
        yd.append(d); yf.append(float(f)); yo.append(float(o))
    return (torch.tensor(np.array(X)), torch.tensor(yd, dtype=torch.float32),
            torch.tensor(yf), torch.tensor(yo))
