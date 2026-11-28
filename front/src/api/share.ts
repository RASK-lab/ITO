/**
 * 記録の ID ごとの、カードを送る処理。送り終えると、シェア用のページのパスになる。
 * 同じ結果でシェアの画面を開き直したときに、作り直しと送り直しをしないために覚えておく。
 */
const uploads = new Map<string, Promise<string>>();

/**
 * 結果 1 件ぶんの、X のカード用の画像をバックエンドに預け、シェア用のページのパス
 * （例: /api/share/0123…）を受け取る。このページを X に投稿すると、預けた画像がカードとして出る。
 * デプロイ先でも同じように動くよう、API は必ず相対パスで呼ぶ。
 * 仕様は docs/api.md を参照。
 *
 * 同じ ID では、1 度しか作らず、1 度しか送らない。失敗したときは覚えないので、
 * 次に呼ばれたときにやり直す。
 *
 * @param drawingId 記録の ID（確定の応答の id）
 * @param makeCard カードの画像（1200 × 630 の JPEG）を作る関数
 */
export function uploadShareCard(
  drawingId: string,
  makeCard: () => Promise<Blob>,
): Promise<string> {
  let upload = uploads.get(drawingId);
  if (!upload) {
    upload = makeCard().then((card) => putCard(drawingId, card));
    uploads.set(drawingId, upload);
    upload.catch(() => uploads.delete(drawingId));
  }
  return upload;
}

async function putCard(drawingId: string, card: Blob): Promise<string> {
  const response = await fetch(`/api/drawings/${drawingId}/card`, {
    method: "PUT",
    headers: { "Content-Type": "image/jpeg" },
    signal: AbortSignal.timeout(15_000),
    body: card,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const { share_path }: { share_path: string } = await response.json();
  return share_path;
}
