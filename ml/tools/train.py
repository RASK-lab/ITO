"""印象の分類モデルを学習する（GPU のマシンで。CPU でも動くが遅い）。

準備: python -m pip install -r ml/requirements-train.txt（PyTorch は GPU 用のものを先に入れる）
データ: tools/export_dataset.py で書き出したフォルダ（--export。省略すると ml/data/export の最新）

使い方（リポジトリの直下で）:
  # 1. 速さと大きさを比べる（学習済みの重みは要らない。ラベルも要らない）
  python ml/tools/train.py bench
  # 2. モデルの候補を比べる（重みを固定して特徴を取り出し、分類の部分だけを学習。数分）
  python ml/tools/train.py compare
  # 3. 選んだモデルで本番用を学習し、ONNX に書き出す
  python ml/tools/train.py fit --backbone dinov2_s --unfreeze 1
  # 書き出したモデルで推論してみる
  python ml/tools/train.py predict ml/runs/<日時>-fit-dinov2_s/model.onnx 画像.png ...

結果は ml/runs/<日時>-<やったこと>/ に置く（Git には入れない）。
  report.md      成績の表（全体、出どころごと、クラスごとの再現率、取り違えの表）
  results.json   同じ内容の数字
  model.onnx     本番用のモデル（fit のとき）。model.json に、クラス・前処理の版・成績を書く

学習の決まり（ml/README.md の「モデル」も参照）:
- 評価: クラスの数の偏りがあるので macro-F1 で比べる。出どころ（フォント、くずし字、集めた
  手書き）ごとにも出す。本番に近いのはフォントと集めた手書き。
- compare は、train と val を group ごとに 5 つに分けて順番に検証する（交差検証）。val だけでは
  フォントが十数枚しかなく、結果がぶれるため。test は fit の最後にだけ使う。
- 偏りへの対策: --balance（sampler / loss / both / none）、--class-power、--source-power、
  --aug-boost（ito_ml/balance.py）。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

ML = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML))

import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402
from torch.utils.data import DataLoader, WeightedRandomSampler  # noqa: E402

from ito_ml import balance, metrics  # noqa: E402
from ito_ml.augment import Augment  # noqa: E402
from ito_ml.dataset import ImageSet, load_rows  # noqa: E402
from ito_ml.manifest import DATA_DIR  # noqa: E402
from ito_ml.model import BACKBONES, Head, ImpressionNet, create_backbone, freeze_backbone, set_train_mode  # noqa: E402
from ito_ml.preprocess import IMAGE_SIZE, PREPROCESS_VERSION  # noqa: E402

RUNS = ML / "runs"
FOLDS = 5


# ---------- 共通 ----------

def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def pick_device(name: str) -> torch.device:
    if name == "auto":
        name = "cuda" if torch.cuda.is_available() else "cpu"
    return torch.device(name)


def autocast(device: torch.device):
    # GPU では bfloat16 で計算して速くする（Blackwell / 5090 で使える）
    return torch.autocast("cuda", dtype=torch.bfloat16) if device.type == "cuda" else torch.autocast("cpu", enabled=False)


def latest_export() -> Path:
    exports = sorted((DATA_DIR / "export").glob("*/dataset.csv"))
    if not exports:
        raise SystemExit("書き出したデータがありません。先に python ml/tools/export_dataset.py --labels ... を実行してください")
    return exports[-1].parent


def new_run(kind: str) -> Path:
    out = RUNS / f"{datetime.now():%Y%m%d-%H%M%S}-{kind}"
    out.mkdir(parents=True)
    return out


def fold_of(group: str) -> int:
    return int(hashlib.sha1(f"fold\0{group}".encode()).hexdigest()[:8], 16) % FOLDS


def loader(rows, args, augment=None, strength=None, sampler=None, shuffle=False) -> DataLoader:
    return DataLoader(ImageSet(rows, augment, strength), batch_size=args.batch, sampler=sampler,
                      shuffle=shuffle and sampler is None, num_workers=args.workers,
                      persistent_workers=args.workers > 0, pin_memory=torch.cuda.is_available())


@torch.no_grad()
def run_model(fn, rows, args, device, augment=None, strength=None) -> torch.Tensor:
    """rows の全部に fn（特徴の取り出し、または logits）をかけて、順番どおりに並べて返す"""
    out = [None] * len(rows)
    for x, _, index in loader(rows, args, augment, strength):
        with autocast(device):
            y = fn(x.to(device, non_blocking=True)).float().cpu()
        for i, v in zip(index.tolist(), y):
            out[i] = v
    return torch.stack(out)


def train_head(head, feats, labels, sources, args, device, n_classes: int) -> None:
    """重みを固定した特徴だけで、分類の部分（head）を学習する。
    feats: V×N×D（V はひとつの画像から作った見え方の数。0 番は水増しなし）"""
    v, n, _ = feats.shape
    x = feats.reshape(v * n, -1).to(device)
    y = torch.tensor(list(labels) * v, device=device)
    head.to(device).set_stats(x)
    w_loss = None
    if args.balance in ("loss", "both"):
        w_loss = torch.tensor(balance.class_weights(labels, n_classes, args.class_power), dtype=torch.float32,
                              device=device)
    if args.balance in ("sampler", "both"):
        p = np.tile(balance.sample_weights(labels, sources, args.class_power, args.source_power), v) / v
    else:
        p = np.tile(balance.sample_weights(labels, sources, 0.0, args.source_power), v) / v
    opt = torch.optim.AdamW(head.parameters(), lr=args.head_lr, weight_decay=args.head_wd)
    steps = max(1, len(x) // 256)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, args.head_epochs * steps)
    rng = np.random.default_rng(args.seed)
    head.train()
    for _ in range(args.head_epochs):
        for _ in range(steps):
            idx = torch.from_numpy(rng.choice(len(x), 256, p=p)).to(device)
            loss = F.cross_entropy(head(x[idx]), y[idx], weight=w_loss, label_smoothing=args.label_smoothing)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
    head.eval()


def args_dict(args) -> dict:
    return {k: v for k, v in vars(args).items() if k != "func"}


def write_report(out: Path, title: str, sections: dict[str, str], results: dict) -> None:
    text = f"# {title}\n\n" + "\n\n".join(f"## {k}\n\n```\n{v}\n```" for k, v in sections.items()) + "\n"
    (out / "report.md").write_text(text, encoding="utf-8")
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def load_data(args):
    export = Path(args.export) if args.export else latest_export()
    rows, classes = load_rows(export)
    meta = json.loads((export / "meta.json").read_text(encoding="utf-8"))
    if not rows:
        raise SystemExit(f"学習に使える行がありません: {export}")
    print(f"データ: {export}（{len(rows)} 枚）")
    return export, rows, classes, meta


# ---------- compare ----------

def cmd_compare(args) -> None:
    device = pick_device(args.device)
    export, rows, classes, _ = load_data(args)
    pool = [r for r in rows if r["split"] in ("train", "val")]
    labels = [r["y"] for r in pool]
    sources = [r["source"] for r in pool]
    print("train + val の偏り:\n" + balance.describe(labels, sources, classes))
    strength = balance.augment_strength(labels, 1.0, args.aug_boost)
    folds = np.array([fold_of(r["group"]) for r in pool])
    out = new_run("compare")
    results, table = {}, []
    for name in args.backbones:
        seed_all(args.seed)
        t0 = time.time()
        backbone, info = create_backbone(name, pretrained=not args.no_pretrained)
        model = ImpressionNet(backbone, info, len(classes)).to(device).eval()
        cache = RUNS / "features" / export.name / f"{name}-v{args.views}-s{args.seed}-{int(args.no_pretrained)}.pt"
        if cache.exists():
            feats = torch.load(cache)
        else:
            views = [run_model(model.features, pool, args, device)]
            for _ in range(args.views):
                views.append(run_model(model.features, pool, args, device, Augment(), strength))
            feats = torch.stack(views)
            cache.parent.mkdir(parents=True, exist_ok=True)
            torch.save(feats, cache)
        t_feat = time.time() - t0
        pred = np.zeros(len(pool), dtype=np.int64)
        for k in range(FOLDS):
            tr, te = np.nonzero(folds != k)[0], np.nonzero(folds == k)[0]
            if len(te) == 0 or len(set(labels[i] for i in tr)) < 2:
                continue
            head = Head(info["feature_dim"], len(classes))
            train_head(head, feats[:, tr], [labels[i] for i in tr], [sources[i] for i in tr], args, device,
                       len(classes))
            with torch.no_grad():
                pred[te] = head(feats[0, te].to(device)).argmax(1).cpu().numpy()
        rep = metrics.report(labels, pred, sources, len(classes))
        results[name] = {"metrics": rep, "feature_seconds": round(t_feat, 1), "note": BACKBONES[name].note}
        print(f"\n[{name}]（特徴の取り出し {t_feat:.0f} 秒）\n" + metrics.format_report(rep, classes))
        table.append((name, rep))
        del model, backbone
        if device.type == "cuda":
            torch.cuda.empty_cache()
    sources_all = sorted({s for _, r in table for s in r if s != "all"})
    head_line = f"{'model':16s}{'all':>8s}" + "".join(f"{s[:12]:>14s}" for s in sources_all)
    lines = [head_line] + [
        f"{n:16s}{r['all']['macro_f1']:8.3f}" + "".join(f"{r[s]['macro_f1'] if s in r else float('nan'):14.3f}"
                                                         for s in sources_all)
        for n, r in sorted(table, key=lambda t: -t[1]["all"]["macro_f1"])]
    summary = "\n".join(lines)
    print("\nmacro-F1（交差検証）\n" + summary)
    write_report(out, "モデルの候補の比較（重みを固定、分類の部分だけ学習。5 分割の交差検証）",
                 {"macro-F1": summary, "偏り": balance.describe(labels, sources, classes),
                  **{n: metrics.format_report(r, classes) for n, r in table}},
                 {"export": str(export), "args": args_dict(args), "classes": classes, "results": results})
    print(f"→ {out}")


# ---------- fit ----------

def evaluate(model, rows, args, device, n_classes) -> dict:
    model.eval()
    logits = run_model(model, rows, args, device)
    return metrics.report([r["y"] for r in rows], logits.argmax(1).numpy(), [r["source"] for r in rows], n_classes)


def cmd_fit(args) -> None:
    device = pick_device(args.device)
    seed_all(args.seed)
    export, rows, classes, export_meta = load_data(args)
    train = [r for r in rows if r["split"] == "train"]
    val = [r for r in rows if r["split"] == "val"]
    test = [r for r in rows if r["split"] == "test"]
    if args.use_val_for_train:
        # 最後の本番用: val も学習に入れ、決めた回数だけ学習する（途中で止める判断はしない）
        train, val = train + val, []
    labels, sources = [r["y"] for r in train], [r["source"] for r in train]
    print(f"train {len(train)}、val {len(val)}、test {len(test)}")
    print("train の偏り:\n" + balance.describe(labels, sources, classes))
    out = new_run(f"fit-{args.backbone}")
    backbone, info = create_backbone(args.backbone, pretrained=not args.no_pretrained)
    model = ImpressionNet(backbone, info, len(classes), args.dropout).to(device)
    trainable = freeze_backbone(model, args.unfreeze)
    print(f"学習する backbone のまとまり: {trainable or 'なし（分類の部分だけ）'}")
    strength = balance.augment_strength(labels, 1.0, args.aug_boost)

    # 1. 分類の部分を、重みを固定した特徴で先に学習しておく（後の学習し直しが安定する）
    model.eval()
    feats = [run_model(model.features, train, args, device)]
    for _ in range(args.views):
        feats.append(run_model(model.features, train, args, device, Augment(), strength))
    train_head(model.head, torch.stack(feats), labels, sources, args, device, len(classes))
    history = []
    best = {"score": -1.0, "epoch": 0, "state": copy.deepcopy(model.state_dict())}
    if val:
        rep = evaluate(model, val, args, device, len(classes))
        best["score"] = rep["all"]["macro_f1"]
        history.append({"epoch": 0, "val_macro_f1": best["score"]})
        print(f"epoch 0（分類の部分だけ）: val macro-F1 {best['score']:.3f}")

    # 2. 水増ししながら、まとめて学習し直す（--epochs 0 なら 1 だけ）
    if args.epochs > 0:
        weights = balance.sample_weights(labels, sources,
                                         args.class_power if args.balance in ("sampler", "both") else 0.0,
                                         args.source_power)
        sampler = WeightedRandomSampler(torch.from_numpy(weights), num_samples=len(train), replacement=True)
        data = loader(train, args, Augment(), strength, sampler=sampler)
        w_loss = None
        if args.balance in ("loss", "both"):
            w_loss = torch.tensor(balance.class_weights(labels, len(classes), args.class_power),
                                  dtype=torch.float32, device=device)
        params = [{"params": [p for p in model.backbone.parameters() if p.requires_grad], "lr": args.lr_backbone},
                  {"params": model.head.parameters(), "lr": args.lr}]
        params = [g for g in params if list(g["params"])]
        opt = torch.optim.AdamW(params, weight_decay=args.wd)
        sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[g["lr"] for g in params],
                                                    total_steps=args.epochs * len(data), pct_start=0.1)
        bad = 0
        for epoch in range(1, args.epochs + 1):
            set_train_mode(model)
            t0, total = time.time(), 0.0
            for x, y, _ in data:
                x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
                with autocast(device):
                    loss = F.cross_entropy(model(x).float(), y, weight=w_loss, label_smoothing=args.label_smoothing)
                opt.zero_grad(set_to_none=True)
                loss.backward()
                opt.step()
                sched.step()
                total += loss.item() * len(x)
            entry = {"epoch": epoch, "loss": total / len(train), "seconds": round(time.time() - t0, 1)}
            if val:
                score = evaluate(model, val, args, device, len(classes))["all"]["macro_f1"]
                entry["val_macro_f1"] = score
                if score > best["score"]:
                    best, bad = {"score": score, "epoch": epoch, "state": copy.deepcopy(model.state_dict())}, 0
                else:
                    bad += 1
            else:
                best = {"score": float("nan"), "epoch": epoch, "state": copy.deepcopy(model.state_dict())}
            history.append(entry)
            print(f"epoch {epoch}: " + ", ".join(f"{k} {v:.3f}" if isinstance(v, float) else f"{k} {v}"
                                                 for k, v in entry.items() if k != "epoch"))
            if val and bad >= args.patience:
                print(f"val の成績が {args.patience} 回よくならなかったので止める")
                break
    model.load_state_dict(best["state"])
    print(f"いちばんよかった epoch {best['epoch']}（val macro-F1 {best['score']:.3f}）")

    reports = {name: evaluate(model, part, args, device, len(classes))
               for name, part in (("val", val), ("test", test)) if part}
    for name, rep in reports.items():
        print(f"\n[{name}]\n" + metrics.format_report(rep, classes))
    meta = {
        "classes": classes,
        "class_labels": {c["key"]: c["label"] for c in export_meta["classes"]},
        "label_set": export_meta["label_set"],
        "backbone": args.backbone, "timm_name": BACKBONES[args.backbone].timm_name,
        "input": f"N×1×{IMAGE_SIZE}×{IMAGE_SIZE} の float32（0〜1、白地に黒）。ito_ml.preprocess.normalize のあと",
        "preprocess": PREPROCESS_VERSION, "image_size": IMAGE_SIZE, "temperature": 1.0,
        "best_epoch": best["epoch"], "export": str(export), "created_at": datetime.now().isoformat(timespec="seconds"),
        "metrics": {name: {k: rep["all"][k] for k in ("macro_f1", "balanced_accuracy", "accuracy", "n")}
                    for name, rep in reports.items()},
        "args": args_dict(args),
    }
    torch.save({"state_dict": model.state_dict(), "meta": meta, "info": info}, out / "model.pt")
    export_onnx(model.cpu().eval(), meta, out, (val or test or train)[:64], args)
    write_report(out, f"学習の結果（{args.backbone}）",
                 {"偏り（train）": balance.describe(labels, sources, classes),
                  **{name: metrics.format_report(rep, classes) for name, rep in reports.items()},
                  "経過": "\n".join(json.dumps(h, ensure_ascii=False) for h in history)},
                 {"meta": meta, "reports": reports, "history": history})
    print(f"→ {out}")


# ---------- ONNX ----------

def to_onnx(model, x: torch.Tensor, path: Path, legacy: bool = True) -> None:
    """いまの PyTorch で確実に動く書き出し方（TorchScript 版）を使い、無くなっていたら新しい書き出し方にする"""
    if legacy:
        try:
            torch.onnx.export(model, (x,), str(path), input_names=["image"], output_names=["logits"],
                              dynamic_axes={"image": {0: "n"}, "logits": {0: "n"}}, opset_version=17, dynamo=False)
            return
        except TypeError:
            pass
    torch.onnx.export(model, (x,), str(path), input_names=["image"], output_names=["logits"],
                      dynamic_shapes={"x": {0: torch.export.Dim("n", min=1, max=64)}}, dynamo=True, external_data=False)


def export_onnx(model, meta: dict, out: Path, check_rows: list[dict], args) -> None:
    """ONNX に書き出し、PyTorch と同じ答えになるかと、CPU（1 スレッド）での時間を確かめる"""
    import onnxruntime as ort

    path = out / "model.onnx"
    x = torch.rand(1, 1, IMAGE_SIZE, IMAGE_SIZE)
    to_onnx(model, x, path)
    checks = {}
    batch = torch.stack([ImageSet(check_rows)[i][0] for i in range(len(check_rows))]) if check_rows else x
    with torch.no_grad():
        expected = model(batch).numpy()
    variants = [("model.onnx", path)]
    if args.int8:
        from onnxruntime.quantization import QuantType, quantize_dynamic

        q = out / "model.int8.onnx"
        # 全結合の層（ViT の大部分）だけ。畳み込みは、この方法では量子化できず、速くもならない
        quantize_dynamic(str(path), str(q), weight_type=QuantType.QInt8, op_types_to_quantize=["MatMul", "Gemm"])
        variants.append(("model.int8.onnx", q))
    for name, p in variants:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        session = ort.InferenceSession(str(p), options, providers=["CPUExecutionProvider"])
        got = session.run(None, {"image": batch.numpy()})[0]
        one = batch[:1].numpy()
        session.run(None, {"image": one})
        times = []
        for _ in range(20):
            t0 = time.perf_counter()
            session.run(None, {"image": one})
            times.append(time.perf_counter() - t0)
        checks[name] = {"max_abs_diff": float(np.abs(got - expected).max()),
                        "same_argmax": float((got.argmax(1) == expected.argmax(1)).mean()),
                        "cpu_1thread_ms": round(1000 * float(np.median(times)), 1),
                        "megabytes": round(p.stat().st_size / 1e6, 1)}
        (p.with_suffix(".json")).write_text(json.dumps(meta | {"check": checks[name]}, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
        print(f"{name}: {checks[name]}")
    meta["onnx_check"] = checks


def cmd_export(args) -> None:
    saved = torch.load(args.checkpoint, weights_only=False)
    meta, info = saved["meta"], saved["info"]
    backbone, _ = create_backbone(meta["backbone"], pretrained=False)
    model = ImpressionNet(backbone, info, len(meta["classes"]))
    model.load_state_dict(saved["state_dict"])
    export_onnx(model.eval(), meta, Path(args.checkpoint).parent, [], args)


def cmd_bench(args) -> None:
    """学習済みの重みなしで、候補ごとの ONNX の大きさと CPU（1 スレッド）の時間を測る"""
    out = new_run("bench")
    rows = []
    for name in args.backbones:
        backbone, info = create_backbone(name, pretrained=False)
        model = ImpressionNet(backbone, info, 4).eval()
        meta = {"classes": [str(i) for i in range(4)], "preprocess": PREPROCESS_VERSION, "backbone": name}
        sub = out / name
        sub.mkdir()
        export_onnx(model, meta, sub, [], args)
        rows.append((name, meta["onnx_check"]))
    lines = [f"{'model':16s}{'MB':>8s}{'ms(1thread)':>14s}" + ("  int8 MB  int8 ms" if args.int8 else "")]
    for name, c in rows:
        line = f"{name:16s}{c['model.onnx']['megabytes']:8.1f}{c['model.onnx']['cpu_1thread_ms']:14.1f}"
        if args.int8:
            line += f"{c['model.int8.onnx']['megabytes']:9.1f}{c['model.int8.onnx']['cpu_1thread_ms']:9.1f}"
        lines.append(line)
    print("\n" + "\n".join(lines))
    write_report(out, "候補ごとの大きさと CPU の時間（この PC、1 スレッド）", {"結果": "\n".join(lines)},
                 {name: c for name, c in rows})
    print(f"→ {out}")


def cmd_predict(args) -> None:
    from PIL import Image

    from ito_ml.infer import ImpressionModel

    model = ImpressionModel(args.model)
    for path in args.images:
        t0 = time.perf_counter()
        with Image.open(path) as image:
            result = model.predict(image)
        ms = 1000 * (time.perf_counter() - t0)
        print(f"{path}: {result['label']}  {result['probs']}  （{ms:.0f} ミリ秒）")


# ---------- 引数 ----------

def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(required=True)

    def common(p, training=True):
        p.add_argument("--device", default="auto")
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("--no-pretrained", action="store_true", help="学習済みの重みを使わない（動作の確認用）")
        p.add_argument("--int8", action="store_true", help="int8 に量子化したものも書き出す")
        if training:
            p.add_argument("--export", help="tools/export_dataset.py の書き出し先（省略すると最新）")
            p.add_argument("--batch", type=int, default=64)
            p.add_argument("--workers", type=int, default=4)
            p.add_argument("--views", type=int, default=4, help="分類の部分の学習に使う、水増しした見え方の数")
            p.add_argument("--balance", choices=["sampler", "loss", "both", "none"], default="sampler")
            p.add_argument("--class-power", type=float, default=1.0, help="1 で各クラスを同じ数ずつ（0 で偏りのまま）")
            p.add_argument("--source-power", type=float, default=0.5, help="出どころの偏りをならす強さ")
            p.add_argument("--aug-boost", type=float, default=1.0, help="少ないクラスほど水増しを強くする度合い")
            p.add_argument("--label-smoothing", type=float, default=0.1)
            p.add_argument("--head-lr", type=float, default=1e-3)
            p.add_argument("--head-wd", type=float, default=1e-2)
            p.add_argument("--head-epochs", type=int, default=30)

    p = sub.add_parser("compare", help="候補を比べる（重みを固定、交差検証）")
    common(p)
    p.add_argument("--backbones", nargs="+", default=list(BACKBONES), choices=list(BACKBONES))
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("fit", help="本番用を学習して ONNX に書き出す")
    common(p)
    p.add_argument("--backbone", default="dinov2_s", choices=list(BACKBONES))
    p.add_argument("--unfreeze", type=int, default=1, help="学習し直す backbone のまとまりの数（後ろから。0 で固定）")
    p.add_argument("--epochs", type=int, default=15)
    p.add_argument("--patience", type=int, default=5)
    p.add_argument("--lr", type=float, default=1e-3, help="分類の部分の学習率")
    p.add_argument("--lr-backbone", type=float, default=3e-5)
    p.add_argument("--wd", type=float, default=0.05)
    p.add_argument("--dropout", type=float, default=0.2)
    p.add_argument("--use-val-for-train", action="store_true", help="最後の本番用だけ: val も学習に使う")
    p.set_defaults(func=cmd_fit)

    p = sub.add_parser("export", help="model.pt から ONNX を書き出し直す")
    common(p, training=False)
    p.add_argument("checkpoint")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("bench", help="候補ごとの ONNX の大きさと CPU の時間")
    common(p, training=False)
    p.add_argument("--backbones", nargs="+", default=list(BACKBONES), choices=list(BACKBONES))
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("predict", help="ONNX のモデルで画像を分類する")
    p.add_argument("model")
    p.add_argument("images", nargs="+")
    p.set_defaults(func=cmd_predict)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
