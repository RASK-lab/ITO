import { useEffect, useRef, useState } from "react";
import {
  MAX_COLLECT_POINTS,
  ProtocolChangedError,
  fetchPlan,
  guessPointerType,
  loadWriterId,
  randomId,
  saveSample,
} from "../api/collect";
import type { CollectPlan, CollectProfile } from "../api/collect";
import { WritingCanvas } from "../components/WritingCanvas";
import type { WritingCanvasHandle } from "../components/WritingCanvas";

/**
 * 学習データ集めの画面（アドレスは #collect）。アプリ本体の画面からはつながず、
 * このアドレスを配って開いてもらう。集め方は docs/collect.md。
 *
 * 開くと、すぐにお題と書く枠が出る。「確定」で 1 個送り、次のお題に進む。
 * お題は 5 個で 1 組。5 個書き終えたら、お礼の画面を出す。「もう一回」で次の 5 個を書ける。
 * 説明と質問の画面、アプリ本体へ進むボタンは置かない。
 */

/** いま書いている 1 組（お題 5 個）と、その中の何個目か */
type Round = { plan: CollectPlan; index: number; sessionId: string };

/**
 * 書いた人の申告。質問の画面をなくしたので、利き手と習字の経験は「答えない」で送る。
 * 学習に使うことは、書く画面に書いて知らせている（下の collect-notice）。
 */
const PROFILE: CollectProfile = {
  dominantHand: "unknown",
  calligraphy: "unknown",
  consentTrain: true,
};

async function loadRound(): Promise<Round> {
  const plan = await fetchPlan(guessPointerType());
  return { plan, index: 0, sessionId: randomId() };
}

/**
 * サーバーが持つお題の文（例: 「雑に（急いで、なぐり書きで）」）を、
 * 大きく出す指示と、かっこの中の補足に分ける。
 */
function splitInstruction(instruction: string) {
  const match = /^(.+?)（(.+)）$/.exec(instruction);
  return match
    ? { text: match[1], hint: match[2] }
    : { text: instruction, hint: "" };
}

export function CollectPage() {
  const [round, setRound] = useState<Round | null>(null);
  /** お題を取れなかったとき true */
  const [failed, setFailed] = useState(false);
  /** この画面を開いてから送れた数 */
  const [sent, setSent] = useState(0);
  /** いまの 1 組で送れた数（飛ばした分は入らない） */
  const [roundSent, setRoundSent] = useState(0);
  /** 1 組を書き終えて、お礼の画面を出しているとき true */
  const [done, setDone] = useState(false);

  function start() {
    loadRound()
      .then(setRound)
      .catch((error) => {
        console.error(error);
        setFailed(true);
      });
  }

  // 開いたら、すぐに最初のお題を取る
  useEffect(start, []);

  /** 次のお題へ。5 個目のあとは、お礼の画面へ。 */
  function next() {
    if (!round) return;
    if (round.index + 1 < round.plan.trials.length) {
      setRound({ ...round, index: round.index + 1 });
    } else {
      setDone(true);
    }
  }

  /** お礼の画面の「もう一回」。次の 5 個を取りに行く。 */
  function again() {
    setDone(false);
    setRoundSent(0);
    setRound(null);
    start();
  }

  if (done) {
    return (
      <main className="collect collect-done">
        <div className="collect-seal" aria-hidden="true">
          と
        </div>
        <h1>ありがとうございました</h1>
        <p>
          {roundSent > 0
            ? `${roundSent} 個の「と」を受け取りました。`
            : "またいつでも書きに来てください。"}
        </p>
        <div className="actions">
          <button type="button" className="primary" onClick={again}>
            もう一回
          </button>
        </div>
      </main>
    );
  }

  if (!round) {
    return (
      <main className="collect">
        <div className="collect-prompt">
          <p className="collect-lead">「と」を書いてください</p>
          <h1>{failed ? "始められませんでした" : "お題を用意しています"}</h1>
          <p className="collect-hint">
            {failed ? "通信を確かめて、下のボタンを押してください。" : ""}
          </p>
        </div>
        {failed && (
          <div className="actions">
            <button
              type="button"
              className="primary"
              onClick={() => {
                setFailed(false);
                start();
              }}
            >
              もう一度
            </button>
          </div>
        )}
      </main>
    );
  }

  return (
    <CollectTrialView
      key={`${round.sessionId}-${round.index}`}
      round={round}
      sent={sent}
      onSent={() => {
        setSent((count) => count + 1);
        setRoundSent((count) => count + 1);
        next();
      }}
      onSkip={next}
    />
  );
}

type TrialProps = {
  round: Round;
  sent: number;
  onSent: () => void;
  onSkip: () => void;
};

/** 1 個分の書く画面。お題ごとに作り直す（key）ので、枠と数えた値は毎回空から始まる。 */
function CollectTrialView({ round, sent, onSent, onSkip }: TrialProps) {
  const canvasRef = useRef<WritingCanvasHandle>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [strokeCount, setStrokeCount] = useState(0);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState("");
  /** 「消去」と「1つ戻る」を押した回数（書き直しの多さとして記録する） */
  const redoRef = useRef(0);

  const trial = round.plan.trials[round.index];
  const total = round.plan.trials.length;
  const empty = strokeCount === 0;
  const { text, hint } = splitInstruction(trial.instruction);

  const status = sent === 0 ? "" : `これまでに ${sent} 個 書きました`;

  async function handleConfirm() {
    const drawing = canvasRef.current?.exportDrawing();
    if (!drawing) return;
    const points = drawing.strokes.reduce((n, s) => n + s.points.length, 0);
    if (points > MAX_COLLECT_POINTS) {
      setMessage("線が多すぎます。「消去」して書き直してください。");
      return;
    }
    // 書く枠の、画面での一辺（端末の大きさで書き方が変わるので記録する）
    const displayPx =
      wrapRef.current?.querySelector("canvas")?.getBoundingClientRect().width ??
      0;
    setSending(true);
    setMessage("");
    try {
      await saveSample(round.plan, trial, drawing, PROFILE, {
        writerId: loadWriterId(),
        sessionId: round.sessionId,
        displayPx: Math.max(50, displayPx),
        redoCount: redoRef.current,
      });
      onSent();
    } catch (error) {
      console.error(error);
      setMessage(
        error instanceof ProtocolChangedError
          ? "集め方が更新されました。ページを読み込み直してください。"
          : "送れませんでした。もう一度「確定」を押してください。",
      );
      setSending(false);
    }
  }

  return (
    <main className="collect">
      <div className="collect-prompt">
        <p className="collect-lead">
          「と」を書いてください（{round.index + 1} / {total}）
        </p>
        <h1>{text}</h1>
        <p className="collect-hint">{hint}</p>
      </div>

      <div className="collect-sheet" ref={wrapRef}>
        <WritingCanvas
          ref={canvasRef}
          disabled={sending}
          onChange={(count) => {
            setStrokeCount(count);
            setMessage("");
          }}
        />
      </div>

      <div className="actions">
        <button
          type="button"
          onClick={() => {
            redoRef.current += 1;
            canvasRef.current?.clear();
          }}
          disabled={empty || sending}
        >
          消去
        </button>
        <button
          type="button"
          onClick={() => {
            redoRef.current += 1;
            canvasRef.current?.undo();
          }}
          disabled={empty || sending}
        >
          1つ戻る
        </button>
        <button
          type="button"
          className="primary"
          onClick={handleConfirm}
          disabled={empty || sending}
        >
          確定
        </button>
      </div>

      <p className="collect-status" role="status">
        {message || status}
      </p>

      <p className="collect-notice">
        書いていただいた「と」は、AI が字の印象を学ぶためのお手本になります。
        {/* 書きにくいお題（利き手と反対の手など）は飛ばせる。飛ばした分は記録しない。 */}
        <button
          type="button"
          className="collect-skip"
          onClick={onSkip}
          disabled={sending}
        >
          このお題を飛ばす
        </button>
      </p>
    </main>
  );
}
