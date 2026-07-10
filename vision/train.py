"""
Entraînement du CNN ResNet18 multi-tâches.

Deux régimes selon la disponibilité des poids ImageNet :
- PRÉ-ENTRAÎNÉ (cas nominal) : backbone gelé, features pré-calculées en un
  seul forward, puis entraînement des 3 têtes seules -> quelques secondes CPU.
- REPLI (hors-ligne)         : backbone aléatoire entraîné de bout en bout
  (obligatoire : des features aléatoires figées ne séparent pas les classes).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

import config as C
from vision.model import MultiTaskCrowdCNN
from vision.synthetic_images import make_dataset

torch.manual_seed(0)


def _losses(out, db, fb, ob, mse, bce):
    return (mse(out["density"], db)
            + bce(out["fallen"], fb)
            + 0.5 * bce(out["object"], ob))       # POC : poids réduit


def _eval(out, vd, vf, vo):
    d_mae = (out["density"] - vd).abs().mean().item()
    f_acc = (((out["fallen"] > 0).float()) == vf).float().mean().item()
    o_acc = (((out["object"] > 0).float()) == vo).float().mean().item()
    return d_mae, f_acc, o_acc


def train():
    X, yd, yf, yo = make_dataset(800)
    model = MultiTaskCrowdCNN(pretrained=True)
    cut = int(len(X) * 0.85)
    mse, bce = nn.MSELoss(), nn.BCEWithLogitsLoss()

    if model.pretrained:
        # ---- transfert : features pré-calculées, têtes seules ----
        model.eval()
        feats = []
        with torch.no_grad():
            for i in range(0, len(X), 64):
                feats.append(model.backbone(X[i:i + 64]))
        Z = torch.cat(feats).detach()
        print(f"features pré-calculées : {tuple(Z.shape)} (backbone ImageNet gelé)")

        tr = DataLoader(TensorDataset(Z[:cut], yd[:cut], yf[:cut], yo[:cut]),
                        batch_size=64, shuffle=True)
        vz, vd, vf, vo = Z[cut:], yd[cut:], yf[cut:], yo[cut:]
        heads = [model.density_head, model.fallen_head, model.object_head]
        opt = torch.optim.AdamW(
            [p for h in heads for p in h.parameters()], lr=2e-3)

        for epoch in range(C.EPOCHS_VISION * 3):     # têtes seules = rapide
            for zb, db, fb, ob in tr:
                opt.zero_grad()
                _losses(model.heads(zb), db, fb, ob, mse, bce).backward()
                opt.step()
            with torch.no_grad():
                d_mae, f_acc, o_acc = _eval(model.heads(vz), vd, vf, vo)
            print(f"epoch {epoch+1}  density_MAE={d_mae:.3f}  "
                  f"fallen_acc={f_acc:.2%}  object_acc={o_acc:.2%}")
    else:
        # ---- repli : bout en bout ----
        print("mode repli : entraînement de bout en bout (backbone aléatoire)")
        tr = DataLoader(TensorDataset(X[:cut], yd[:cut], yf[:cut], yo[:cut]),
                        batch_size=32, shuffle=True)
        vx, vd, vf, vo = X[cut:], yd[cut:], yf[cut:], yo[cut:]
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3)

        for epoch in range(C.EPOCHS_VISION):
            model.train()
            for xb, db, fb, ob in tr:
                opt.zero_grad()
                _losses(model(xb), db, fb, ob, mse, bce).backward()
                opt.step()
            model.eval()
            with torch.no_grad():
                d_mae, f_acc, o_acc = _eval(model(vx), vd, vf, vo)
            print(f"epoch {epoch+1}  density_MAE={d_mae:.3f}  "
                  f"fallen_acc={f_acc:.2%}  object_acc={o_acc:.2%}")

    torch.save(model.state_dict(), C.VISION_MODEL)
    print(f"-> modèle sauvegardé : {C.VISION_MODEL}")
    return d_mae, f_acc, o_acc


if __name__ == "__main__":
    train()
