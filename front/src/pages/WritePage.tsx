import { useRef, useState } from "react";
import { saveDrawing } from "../api/drawings";
import { WritingCanvas } from "../components/WritingCanvas";
import type { WritingCanvasHandle } from "../components/WritingCanvas";
import { displayUserName } from "../userName";

/** 書ける量の上限に達している間、結果の表示がないときに出す案内 */
const FULL_MESSAGE =
  "これ以上は書けません。「1つ戻る」か「消去」で減らしてください。";

/** 「と」を書く画面 */
export function WritePage() {
  const canvasRef = useRef<WritingCanvasHandle>(null);
  const [strokeCount, setStrokeCount] = useState(0);
  const [full, setFull] = useState(false);
  const [sending, setSending] = useState(false);
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
    try {
      const saved = await saveDrawing(drawing, displayUserName());
      // ID は長いので、画面には先頭だけ出す
      setMessage(`記録しました（ID: ${saved.id.slice(0, 8)}）`);
    } catch (error) {
      console.error(error);
      setMessage("記録できませんでした。もう一度「確定」を押してください。");
    } finally {
      setSending(false);
    }
  }

  return (
    <main>
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
        <button type="button" onClick={handleConfirm} disabled={empty || sending}>
          {sending ? "記録中" : "確定"}
        </button>
      </div>

      <p className="message" role="status">
        {message || (full ? FULL_MESSAGE : "")}
      </p>
    </main>
  );
}
