#!/usr/bin/env bash
# くつしたの「写し」を、元データ（data/socks/）から作り直す。
#   data/socks/original/*.png  →  front/public/socks/*.webp      （表示用の画像）
#   data/socks/socks.json      →  back/src/resources/socks.json  （バックエンド用）
#   上の 2 つ                  →  front/public/share/, front/public/s/（シェア用。scripts/build-share.py）
# 使い方: scripts/build-socks.sh（リポジトリのどこから実行してもよい）
# 説明: docs/socks.md
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
json="$root/data/socks/socks.json"
png_dir="$root/data/socks/original"
webp_dir="$root/front/public/socks"
json_copy="$root/back/src/resources/socks.json"

if ! command -v cwebp >/dev/null; then
  echo "cwebp が見つかりません。'brew install webp' で入れてから、もう一度実行してください。" >&2
  exit 1
fi

# 1. PNG を WebP に変換する（毎回すべて作り直す。4 枚ずつ並べて 1 分ほど）
mkdir -p "$webp_dir"
echo "WebP に変換しています…"
find "$png_dir" -maxdepth 1 -name '*.png' -print0 |
  xargs -0 -P 4 -I{} sh -c \
    'cwebp -quiet -q 85 -alpha_q 100 -m 6 "$1" -o "$2/$(basename "$1" .png).webp"' _ {} "$webp_dir"

# 2. 照合する: socks.json の ID と PNG、image と WebP が過不足なくそろっているか
python3 -I - "$json" "$png_dir" "$webp_dir" <<'PY'
import json, os, sys

json_path, png_dir, webp_dir = sys.argv[1:4]
items = json.load(open(json_path, encoding="utf-8"))["items"]


def compare(label, expected, folder, ext):
    actual = {f for f in os.listdir(folder) if f.endswith(ext)}
    lines = [f"  {label} が足りない: {name}" for name in sorted(expected - actual)]
    lines += [f"  {label} が余っている（socks.json にない）: {name}" for name in sorted(actual - expected)]
    return lines


problems = compare("PNG", {item["id"].lower() + ".png" for item in items}, png_dir, ".png")
problems += compare("WebP", {os.path.basename(item["image"]) for item in items}, webp_dir, ".webp")
if problems:
    sys.exit("照合に失敗しました。\n" + "\n".join(problems))
print(f"照合 OK: socks.json {len(items)} 件、PNG と WebP がそろっています。")
PY

# 3. socks.json をバックエンド用にコピーする
mkdir -p "$(dirname "$json_copy")"
cp "$json" "$json_copy"

echo "作り直しました: front/public/socks/（WebP）、back/src/resources/socks.json"

# 4. シェア用のカード画像とページを作り直す（Pillow が必要）
python3 "$root/scripts/build-share.py"
