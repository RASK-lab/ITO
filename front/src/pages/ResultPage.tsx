import { useState } from "react";
import type { SavedDrawing } from "../api/drawings";
import { ShareDialog } from "../components/ShareDialog";

type Props = {
  /** 確定の応答。このうち、くつしたとメッセージを出す。 */
  result: SavedDrawing;
  /** 書いた「と」の画像（data URL）。シェアする画像に入れる。 */
  drawingImage: string;
  /** 「もう一度」が押されたとき */
  onAgain: () => void;
};

/**
 * 結果の画面（仮）。届いたくつしたの画像と、一行のメッセージを出す。
 * 「シェア」を押すと、シェアの画面（ShareDialog）を重ねて出す。
 */
export function ResultPage({ result, drawingImage, onAgain }: Props) {
  const [sharing, setSharing] = useState(false);

  return (
    <main className="result">
      {/* くつしたの画像は 512 × 512 の透明背景。読み込む前から場所を取っておく。 */}
      <img
        className="sock"
        src={result.sock.image}
        alt={result.sock.name}
        width={512}
        height={512}
      />
      <p>{result.message}</p>
      <div className="actions">
        <button type="button" onClick={onAgain}>
          もう一度
        </button>
        <button type="button" onClick={() => setSharing(true)}>
          シェア
        </button>
      </div>
      {sharing && (
        <ShareDialog
          sock={result.sock}
          drawingImage={drawingImage}
          onClose={() => setSharing(false)}
        />
      )}
    </main>
  );
}
