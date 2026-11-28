"""印象の分類モデル。ImageNet などで学習済みのモデル（backbone）＋ 小さな分類の部分（head）。

入力は preprocess.normalize で整えた画像そのもの（N×1×256×256、0〜1、白地に黒）。
大きさの変更・3 チャネルへの複製・明るさの正規化はモデルの中で行う。こうすると、本番は
「normalize して 0〜1 にして渡すだけ」になり、学習と本番で処理がずれない（ONNX にもそのまま入る）。

候補（BACKBONES）。どれも timm で読める。本番は CPU（Cloudflare の basic、vCPU 1/4）なので、
大きさと速さも比べて選ぶ（tools/train.py export で CPU の時間を測る）。
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn.functional as F
from torch import nn


@dataclass(frozen=True)
class Backbone:
    timm_name: str
    input_size: int
    note: str
    # timm.create_model に渡す追加の引数
    kwargs: tuple = ()


BACKBONES = {
    "resnet18": Backbone("resnet18.tv_in1k", 224, "ImageNet。いちばん軽い。基準"),
    "convnext_tiny": Backbone("convnext_tiny.fb_in22k_ft_in1k", 224, "ImageNet-22k。今風の畳み込み"),
    "dinov2_s": Backbone("vit_small_patch14_dinov2.lvd142m", 224, "ラベルなしで学習。線画でも特徴が崩れにくい",
                         (("img_size", 224),)),
    "clip_b32": Backbone("vit_base_patch32_clip_224.openai", 224, "画像と言葉で学習。雰囲気の概念を持つ"),
}


def create_backbone(name: str, pretrained: bool = True) -> tuple[nn.Module, dict]:
    """(モデル, {"mean", "std", "input_size", "feature_dim"})"""
    import timm

    spec = BACKBONES[name]
    model = timm.create_model(spec.timm_name, pretrained=pretrained, num_classes=0, **dict(spec.kwargs))
    cfg = timm.data.resolve_data_config({}, model=model)
    return model, {"mean": list(cfg["mean"]), "std": list(cfg["std"]), "input_size": spec.input_size,
                   "feature_dim": model.num_features}


class Head(nn.Module):
    """特徴 → クラスの点数（logits）。特徴の平均と散らばりで割ってから、1 層で分類する。"""

    def __init__(self, feature_dim: int, n_classes: int, dropout: float = 0.2) -> None:
        super().__init__()
        self.register_buffer("mu", torch.zeros(feature_dim))
        self.register_buffer("sigma", torch.ones(feature_dim))
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(feature_dim, n_classes)

    def set_stats(self, features: torch.Tensor) -> None:
        self.mu.copy_(features.mean(0))
        self.sigma.copy_(features.std(0).clamp_min(1e-6))

    def forward(self, f: torch.Tensor) -> torch.Tensor:
        return self.fc(self.dropout((f - self.mu) / self.sigma))


class ImpressionNet(nn.Module):
    def __init__(self, backbone: nn.Module, info: dict, n_classes: int, dropout: float = 0.2) -> None:
        super().__init__()
        self.backbone = backbone
        self.input_size = info["input_size"]
        self.register_buffer("mean", torch.tensor(info["mean"]).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(info["std"]).view(1, 3, 1, 1))
        self.head = Head(info["feature_dim"], n_classes, dropout)

    def prepare(self, x: torch.Tensor) -> torch.Tensor:
        """N×1×256×256（0〜1）→ backbone の入力"""
        if x.shape[-1] != self.input_size:
            x = F.interpolate(x, size=(self.input_size, self.input_size), mode="bilinear", align_corners=False)
        return (x.expand(-1, 3, -1, -1) - self.mean) / self.std

    def features(self, x: torch.Tensor) -> torch.Tensor:
        return self.backbone(self.prepare(x))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x))


def freeze_backbone(model: ImpressionNet, unfreeze_groups: int = 0) -> list[str]:
    """backbone の重みを固定し、後ろから unfreeze_groups 個のまとまり（ResNet なら layer4 など）
    だけを学習できるようにする。学習するまとまりの名前を返す。"""
    from timm.models import group_parameters

    backbone = model.backbone
    for p in backbone.parameters():
        p.requires_grad = False
    if unfreeze_groups <= 0:
        return []
    # {まとまりの番号: [重みの名前]}。番号の大きいものほど後ろ（出力に近い）
    groups = group_parameters(backbone, backbone.group_matcher(coarse=True))
    names = dict(backbone.named_parameters())
    chosen = []
    for gid in sorted(groups, reverse=True):
        params = [n for n in groups[gid] if n in names]
        if not params:
            continue  # 分類の部分（num_classes=0 で空）など
        for n in params:
            names[n].requires_grad = True
        top = params[0].split(".")[0]
        if top in ("head", "norm", "fc_norm"):
            continue  # 最後の正規化の層だけのまとまりは、学習するが数に入れない（ConvNeXt など）
        chosen.append(f"{top} ({gid})")
        if len(chosen) >= unfreeze_groups:
            break
    return chosen


def set_train_mode(model: ImpressionNet) -> None:
    """学習のとき: 重みを固定した部分は評価のモード（BatchNorm の統計を変えない）にする"""
    model.train()
    for module in model.backbone.modules():
        params = list(module.parameters(recurse=False))
        if params and not any(p.requires_grad for p in params):
            module.eval()
