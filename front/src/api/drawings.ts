import type { Drawing } from "../components/WritingCanvas";

export type SavedDrawing = { id: string; created_at: string };

/**
 * 書いてもらう字。いまは「と」だけ。
 * バックエンドが受け取れる字（back/src/drawings.py の TARGETS）にあるものを送る。
 */
const TARGET = "と";

/**
 * 書いた「と」をバックエンドに記録する。
 * デプロイ先でも同じように動くよう、API は必ず相対パスで呼ぶ。
 * 仕様は docs/api.md を参照。
 */
export async function saveDrawing(drawing: Drawing): Promise<SavedDrawing> {
  const response = await fetch("/api/drawings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // 応答が返らないまま「記録中」で止まらないよう、待つ時間に上限を置く
    signal: AbortSignal.timeout(15_000),
    body: JSON.stringify({
      target: TARGET,
      canvas: drawing.canvas,
      strokes: drawing.strokes,
      image: drawing.image,
      width: drawing.width,
      height: drawing.height,
    }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
