import type { SavedDrawing } from "../api/drawings";

type Props = {
  /** 確定の応答。このうち、くつしたとメッセージを出す。 */
  result: SavedDrawing;
  /** 「もう一度」が押されたとき */
  onAgain: () => void;
};

/**
 * 結果の画面（仮）。届いたくつしたの画像と、一行のメッセージを出す。
 * シェア、画像の保存、メニューは、まだない。
 */
export function ResultPage({ result, onAgain }: Props) {
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
      </div>
    </main>
  );
}
