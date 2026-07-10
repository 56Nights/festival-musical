"""
CNN multi-tâches — backbone ResNet18 (transfert d'apprentissage).

  frame -> ResNet18 (pré-entraîné ImageNet, GELÉ)
             └─ features 512-d
                  ├── tête 1 : densité de foule   (régression, 0..1)
                  ├── tête 2 : personne au sol    (classification binaire)
                  └── tête 3 : objet suspect      (classification binaire, POC)

Justification (Compétence 3) :
- transfert d'apprentissage : les features visuelles génériques d'ImageNet
  (contours, textures, formes) sont réutilisées — seules les 3 petites têtes
  sont entraînées, ce qui rend l'entraînement quasi instantané même sur CPU
  (les features du dataset sont pré-calculées en un seul forward pass).
- si les poids ImageNet ne sont pas téléchargeables (hors-ligne), le backbone
  est initialisé aléatoirement et dégelé : le code reste fonctionnel.
"""
import torch
import torch.nn as nn
from torchvision.models import resnet18

try:
    from torchvision.models import ResNet18_Weights
    _WEIGHTS = ResNet18_Weights.IMAGENET1K_V1
except ImportError:                              # anciennes versions
    _WEIGHTS = None


def _head():
    return nn.Sequential(nn.Linear(512, 64), nn.ReLU(),
                         nn.Dropout(0.2), nn.Linear(64, 1))


class MultiTaskCrowdCNN(nn.Module):
    def __init__(self, pretrained: bool = True):
        super().__init__()
        self.pretrained = False
        net = None
        if pretrained:
            try:
                net = resnet18(weights=_WEIGHTS)
                self.pretrained = True
            except Exception as exc:             # pas de réseau
                print(f"[vision] poids ImageNet indisponibles "
                      f"({type(exc).__name__}) -> init aléatoire")
        if net is None:
            net = resnet18(weights=None)

        self.backbone = nn.Sequential(*list(net.children())[:-1],
                                      nn.Flatten())          # -> (B, 512)
        if self.pretrained:                       # transfert : backbone gelé
            for p in self.backbone.parameters():
                p.requires_grad = False

        self.density_head = nn.Sequential(_head(), nn.Sigmoid())
        self.fallen_head = _head()                # logits
        self.object_head = _head()                # logits

    def heads(self, z):
        return {
            "density": self.density_head(z).squeeze(-1),
            "fallen": self.fallen_head(z).squeeze(-1),
            "object": self.object_head(z).squeeze(-1),
        }

    def forward(self, x):
        return self.heads(self.backbone(x))
