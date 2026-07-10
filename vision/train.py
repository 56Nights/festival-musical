"""Entraînement du CNN multi-tâches sur frames synthétiques."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

import config as C
from vision.model import MultiTaskCrowdCNN
from vision.synthetic_images import make_dataset

torch.manual_seed(0)


def train():
    X, yd, yf, yo = make_dataset(800)
    cut = int(len(X) * 0.85)
    tr = DataLoader(TensorDataset(X[:cut], yd[:cut], yf[:cut], yo[:cut]),
                    batch_size=32, shuffle=True)
    vx, vd, vf, vo = X[cut:], yd[cut:], yf[cut:], yo[cut:]

    model = MultiTaskCrowdCNN()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    mse, bce = nn.MSELoss(), nn.BCEWithLogitsLoss()

    for epoch in range(C.EPOCHS_VISION):
        model.train()
        for xb, db, fb, ob in tr:
            opt.zero_grad()
            out = model(xb)
            # perte multi-tâches pondérée
            loss = (mse(out["density"], db)
                    + bce(out["fallen"], fb)
                    + 0.5 * bce(out["object"], ob))   # POC : poids réduit
            loss.backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            out = model(vx)
            d_mae = (out["density"] - vd).abs().mean().item()
            f_acc = (((out["fallen"] > 0).float()) == vf).float().mean().item()
            o_acc = (((out["object"] > 0).float()) == vo).float().mean().item()
        print(f"epoch {epoch+1}  density_MAE={d_mae:.3f}  "
              f"fallen_acc={f_acc:.2%}  object_acc={o_acc:.2%}")

    torch.save(model.state_dict(), C.VISION_MODEL)
    print(f"-> modèle sauvegardé : {C.VISION_MODEL}")
    return d_mae, f_acc, o_acc


if __name__ == "__main__":
    train()
