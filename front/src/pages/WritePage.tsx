import { useRef, useState } from "react";
import { saveDrawing } from "../api/drawings";
import type { SavedDrawing } from "../api/drawings";
import { WritingCanvas } from "../components/WritingCanvas";
import type { WritingCanvasHandle } from "../components/WritingCanvas";
import { displayUserName } from "../userName";
import { ResultPage } from "./ResultPage";
import { WaitingPage } from "./WaitingPage";

/** 書ける量の上限に達している間、結果の表示がないときに出す案内 */
const FULL_MESSAGE =
  "これ以上は書けません。「1つ戻る」か「消去」で減らしてください。";

/**
 * 待機中の画面を出しておく、いちばん短い時間（ミリ秒）。
 * いまは保存が一瞬（0.1 秒前後）で終わるので、そのまま切り替えると、待機中の画面が
 * 一瞬だけ出て消え、ちらついて見える。あとで分析の待ち時間が入る場所なので、
 * その代わりとして、この時間は必ず出しておく。失敗したときも同じだけ待つ。
 */
const MIN_WAITING_MS = 1500;

function wait(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

/**
 * 「と」を書く画面。「確定」のあとの待機中の画面と結果の画面も、この中で切り替える
 * （アドレスは変えない）。
 */
export function WritePage() {
  const canvasRef = useRef<WritingCanvasHandle>(null);
  const [strokeCount, setStrokeCount] = useState(0);
  const [full, setFull] = useState(false);
  /** 「確定」を押してから、結果か失敗が決まるまで true。その間は待機中の画面を出す。 */
  const [sending, setSending] = useState(false);
  /** 届いた結果。あれば結果の画面を出す。 */
  const [result, setResult] = useState<SavedDrawing | null>(null);
  const [message, setMessage] = useState("");

  const empty = strokeCount === 0;

  function handleCanvasChange(count: number, isFull: boolean) {
    setStrokeCount(count);
    setFull(isFull);
    setMessage("");
  }

  async function handleConfirm() {
    const drawing = canvasRef.current?.exportDrawing();
    if (!drawing) return;
    setMessage("");
    setSending(true);
    // 保存が早く終わっても、失敗しても、MIN_WAITING_MS が過ぎるまでは待機中の画面のまま
    const [saved] = await Promise.allSettled([
      saveDrawing(drawing, displayUserName()),
      wait(MIN_WAITING_MS),
    ]);
    if (saved.status === "fulfilled") {
      setResult(saved.value);
    } else {
      // 書く画面に戻す。書いた線は残っている。
      console.error(saved.reason);
      setMessage("記録できませんでした。もう一度「確定」を押してください。");
    }
    setSending(false);
  }

  /** 結果の画面の「もう一度」。枠を空にして、書く画面に戻す。 */
  function handleAgain() {
    canvasRef.current?.clear();
    setResult(null);
  }

  return (
    <>
      {/*
        待機中の画面と結果の画面を出している間も、書く画面は外さずに隠すだけにする。
        外すと、枠が覚えている線が消え、失敗して戻ったときに書き直しになるため。
      */}
      <main hidden={sending || result !== null}>
        <h1>「と」を書いてください</h1>

        <WritingCanvas
          ref={canvasRef}
          disabled={sending}
          onChange={handleCanvasChange}
        />

        <div className="actions">
          <button
            type="button"
            onClick={() => canvasRef.current?.clear()}
            disabled={empty || sending}
          >
            消去
          </button>
          <button
            type="button"
            onClick={() => canvasRef.current?.undo()}
            disabled={empty || sending}
          >
            1つ戻る
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={empty || sending}
          >
            確定
          </button>
        </div>

        <p className="message" role="status">
          {message || (full ? FULL_MESSAGE : "")}
        </p>
      </main>

      {result !== null ? (
        <ResultPage result={result} onAgain={handleAgain} />
      ) : (
        sending && <WaitingPage />
      )}
    </>
  );
}
