#!/usr/bin/env bash
# 本番の R2 と D1 から、書かれた「と」のデータを消す。ラベル（labels/）は消さない。
#   bash infra/scripts/reset_data.sh            # 通常の確定（drawings、cards）だけ
#   bash infra/scripts/reset_data.sh --collect  # 学習データ集め（collect_samples）も消す
# 消す順番は R2 → D1（R2 のキーは D1 から読むため）。R2 は元に戻せない。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR/infra/cloudflare"

DB=ito-db
BUCKET=ito-drawing
WITH_COLLECT=false
[[ "${1:-}" == "--collect" ]] && WITH_COLLECT=true

d1() { npx wrangler d1 execute "$DB" --remote "$@"; }

delete_r2_keys() {
  # 標準入力のキーを 1 行ずつ R2 から消す
  local count=0
  while read -r key; do
    npx wrangler r2 object delete "$BUCKET/$key" --remote >/dev/null
    count=$((count + 1))
  done
  echo "R2 から ${count} 個消しました"
}

echo "=== 今の件数 ==="
d1 --command "select (select count(*) from drawings) as drawings, (select count(*) from collect_samples) as collect"

echo
echo "消すもの: drawings（drawings/、cards/）"
$WITH_COLLECT && echo "          collect_samples（collect/）"
echo "消さないもの: labels/（ラベル）"
read -r -p "本番のデータを消します。よろしければ yes と入力してください: " answer
[[ "$answer" == "yes" ]] || { echo "やめました"; exit 1; }

echo "=== drawings: R2 ==="
d1 --json --command "select image_1024_key, image_256_key, strokes_key, 'cards/' || id || '.jpg' as card_key from drawings" \
  | grep -o -E '"(drawings|cards)/[^"]*"' | tr -d '"' | delete_r2_keys
echo "=== drawings: D1 ==="
d1 --command "DELETE FROM drawings"

if $WITH_COLLECT; then
  echo "=== collect_samples: R2 ==="
  d1 --json --command "select image_1024_key, image_256_key from collect_samples" \
    | grep -o '"collect/[^"]*"' | tr -d '"' | delete_r2_keys
  echo "=== collect_samples: D1 ==="
  d1 --command "DELETE FROM collect_samples"
fi

echo "=== リセット後の件数 ==="
d1 --command "select (select count(*) from drawings) as drawings, (select count(*) from collect_samples) as collect"
echo "D1 に記録のないファイルは残ることがあります。ダッシュボードの R2 で確かめてください。"    