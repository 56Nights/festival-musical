"""
CNN multi-tâches : un backbone partagé, trois têtes.

  frame -> backbone convolutionnel
             ├── tête 1 : densité de foule   (régression, 0..1)
             ├── tête 2 : personne au sol    (classification binaire)
             └── tête 3 : objet suspect      (classification binaire, POC)

Justification (Compétence 3) :
- backbone partagé = une seule passe d'inférence par frame
- taux d'échantillonnage découplés par tête (10 fps chute, 1 fps objet)
- la tête "objet suspect" (ex. seringue) est un proof of concept entraîné
  sur données synthétiques — limites explicitées dans le rapport.
"""
import torch
import torch.nn as nn


def _block(cin, cout):
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1), nn.BatchNorm2d(cout), nn.ReLU(),
        nn.Conv2d(cout, cout, 3, padding=1), nn.BatchNorm2d(cout), nn.ReLU(),
        nn.MaxPool2d(2))


class MultiTaskCrowdCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = nn.Sequential(
            _block(3, 16), _block(16, 32), _block(32, 64))
        # avg pool = signal global (densité) ; max pool = petits objets saillants
        self.avg = nn.AdaptiveAvgPool2d(1)
        self.max = nn.AdaptiveMaxPool2d(1)
        self.density_head = nn.Sequential(
            nn.Linear(128, 32), nn.ReLU(), nn.Linear(32, 1), nn.Sigmoid())
        self.fallen_head = nn.Sequential(
            nn.Linear(128, 32), nn.ReLU(), nn.Linear(32, 1))
        self.object_head = nn.Sequential(
            nn.Linear(128, 32), nn.ReLU(), nn.Linear(32, 1))

    def forward(self, x):
        f = self.backbone(x)
        z = torch.cat([self.avg(f).flatten(1), self.max(f).flatten(1)], dim=1)
        return {
            "density": self.density_head(z).squeeze(-1),
            "fallen": self.fallen_head(z).squeeze(-1),   # logits
            "object": self.object_head(z).squeeze(-1),   # logits
        }
