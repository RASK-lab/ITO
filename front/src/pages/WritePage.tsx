import { useRef, useState } from "react";
import { saveDrawing } from "../api/drawings";
import type { SavedDrawing } from "../api/drawings";
import { WritingCanvas } from "../components/WritingCanvas";
import type { WritingCanvasHandle } from "../components/WritingCanvas";
import { EnvelopeAnimation } from "../components/EnvelopeAnimation";
import { displayUserName } from "../userName";
import { ResultPage } from "./ResultPage";
import { WaitingPage } from "./WaitingPage";

type AnimPhase = "idle" | "glow" | "fold" | "envelope" | "fly" | "resolving";

const FULL_MESSAGE =
  "これ以上は書けません。「1つ戻る」か「消去」で減らしてください。";

function wait(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

export function WritePage() {
  const canvasRef = useRef<WritingCanvasHandle>(null);
  const [strokeCount, setStrokeCount] = useState(0);
  const [full, setFull] = useState(false);
  const [animPhase, setAnimPhase] = useState<AnimPhase>("idle");
  const [result, setResult] = useState<{
    saved: SavedDrawing;
    drawingImage: string;
  } | null>(null);
  const [message, setMessage] = useState("");

  const empty = strokeCount === 0;
  const isAnimating = animPhase !== "idle";

  function handleCanvasChange(count: number, isFull: boolean) {
    setStrokeCount(count);
    setFull(isFull);
    setMessage("");
  }

  async function handleSend() {
    const drawing = canvasRef.current?.exportDrawing();
    if (!drawing) return;
    setMessage("");

    // API 呼び出しをアニメーションと並列で開始
    const apiPromise = saveDrawing(drawing, displayUserName()).catch((e) => {
      console.error(e);
      return null;
    });

    // Phase 1: Glow（文字が金色に輝く・2 秒）
    setAnimPhase("glow");
    const glowMs = 2000;
    const glowStart = Date.now();
    let rafId: number;
    const animateInk = () => {
      if (Date.now() - glowStart < glowMs) {
        canvasRef.current?.redrawWithCurrentColor();
        rafId = requestAnimationFrame(animateInk);
      }
    };
    rafId = requestAnimationFrame(animateInk);
    await wait(glowMs);
    cancelAnimationFrame(rafId);

    setAnimPhase("fold");
    await wait(800);
    setAnimPhase("envelope");
    await wait(1000);
    setAnimPhase("fly");
    await wait(900);

    // アニメーション終了後、API 完了を待つ（通常はすでに終わっている）
    setAnimPhase("resolving");
    const saved = await apiPromise;
    setAnimPhase("idle");

    if (saved) {
      setResult({ saved, drawingImage: drawing.image });
    } else {
      setMessage("記録できませんでした。もう一度「送る」を押してください。");
    }
  }

  function handleAgain() {
    canvasRef.current?.clear();
    setResult(null);
  }

  const showLetter =
    (animPhase === "idle" || animPhase === "glow" || animPhase === "fold") &&
    result === null;
  const showEnvelope = animPhase === "envelope" || animPhase === "fly";
  const showWaiting = animPhase === "resolving";

  return (
    <>
      {/* 手紙ボード — DOM に残しておくことで canvas の線を保持 */}
      <div
        className="letter-scene"
        style={{ display: showLetter ? "flex" : "none" }}
        aria-hidden={!showLetter}
      >
        <div className="letter-with-seal">
          <div
            className={[
              "letter-board",
              animPhase === "glow" ? "phase-glow" : "",
              animPhase === "fold" ? "phase-fold" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <p className="letter-to">To: {displayUserName()}</p>

            <div
              className={`letter-canvas-area${animPhase === "glow" ? " glow" : ""}`}
            >
              <WritingCanvas
                ref={canvasRef}
                disabled={isAnimating}
                onChange={handleCanvasChange}
              />
            </div>

            <p className="letter-from">From: 糸</p>
          </div>

          <div className="wax-seal" aria-hidden="true">
            <span className="wax-seal__glyph">糸</span>
          </div>
        </div>

        <div className="letter-controls">
          <div className="letter-actions-sub">
            <button
              type="button"
              onClick={() => canvasRef.current?.clear()}
              disabled={empty || isAnimating}
              className="letter-btn-sub"
            >
              消去
            </button>
            <button
              type="button"
              onClick={() => canvasRef.current?.undo()}
              disabled={empty || isAnimating}
              className="letter-btn-sub"
            >
              1つ戻る
            </button>
          </div>

          <button
            type="button"
            onClick={handleSend}
            disabled={empty || isAnimating}
            className="letter-send-btn"
          >
            送る
          </button>
        </div>

        <p className="message" role="status">
          {message || (full ? FULL_MESSAGE : "")}
        </p>
      </div>

      {showEnvelope && (
        <EnvelopeAnimation phase={animPhase as "envelope" | "fly"} />
      )}

      {result !== null ? (
        <ResultPage
          result={result.saved}
          drawingImage={result.drawingImage}
          onAgain={handleAgain}
        />
      ) : (
        showWaiting && <WaitingPage />
      )}
    </>
  );
}
