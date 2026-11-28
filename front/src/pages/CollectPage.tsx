import { useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  MAX_COLLECT_POINTS,
  ProtocolChangedError,
  fetchPlan,
  guessPointerType,
  loadProfile,
  loadWriterId,
  randomId,
  saveProfile,
  saveSample,
} from "../api/collect";
import type { CollectPlan, CollectProfile } from "../api/collect";
import { WritingCanvas } from "../components/WritingCanvas";
import type { WritingCanvasHandle } from "../components/WritingCanvas";

/**
 * 学習データ集めの画面（アドレスは #collect）。アプリ本体の画面からはつながず、
 * このアドレスを配って開いてもらう。集め方は docs/collect.md。
 *
 * 流れ: 説明と同意・2 つの質問 → 「と」を 6 回書く（1 回ごとに送る）→ お礼
 * 途中でやめても、それまでに送った分は残る。
 */

type Step =
  | { kind: "intro" }
  | { kind: "write"; plan: CollectPlan; index: number; sessionId: string }
  | { kind: "done"; sent: number };

const EMPTY_PROFILE: CollectProfile = {
  dominantHand: "unknown",
  calligraphy: "unknown",
  consentTrain: false,
  consentShow: false,
};

export function CollectPage() {
  const [step, setStep] = useState<Step>({ kind: "intro" });
  const [profile, setProfile] = useState<CollectProfile>(
    () => loadProfile() ?? EMPTY_PROFILE,
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  /** この回で送れた数（お礼の画面に出す） */
  const sentRef = useRef(0);

  async function start() {
    setBusy(true);
    setMessage("");
    try {
      const plan = await fetchPlan(guessPointerType());
      sentRef.current = 0;
      setStep({ kind: "write", plan, index: 0, sessionId: randomId() });
    } catch (error) {
      console.error(error);
      setMessage("始められませんでした。通信を確かめて、もう一度押してください。");
    }
    setBusy(false);
  }

  function handleIntroSubmit(event: FormEvent) {
    event.preventDefault();
    if (!profile.consentTrain) return;
    saveProfile(profile);
    void start();
  }

  /** 次の指示へ。最後ならお礼の画面へ。 */
  function next() {
    if (step.kind !== "write") return;
    if (step.index + 1 < step.plan.trials.length) {
      setStep({ ...step, index: step.index + 1 });
    } else {
      setStep({ kind: "done", sent: sentRef.current });
    }
  }

  if (step.kind === "intro") {
    return (
      <main className="collect">
        <h1>「と」を集めています</h1>
        <p>
          AI の学習のために、ひらがなの「と」を 6 回書いてください（2〜3 分）。
          最初の 2 回はいつもどおりに、残りは「可愛く」などの指示に合わせて書きます。
        </p>
        <p className="collect-note">
          記録するのは、書いた線（位置と時間、筆圧）、画像、書く枠の大きさ、下の 2
          つの答えだけです。名前などは聞きません。同じ端末で書いた「と」は、無作為な番号でまとめます。
        </p>
        <form onSubmit={handleIntroSubmit}>
          <label>
            利き手
            <select
              value={profile.dominantHand}
              onChange={(e) =>
                setProfile({
                  ...profile,
                  dominantHand: e.target.value as CollectProfile["dominantHand"],
                })
              }
            >
              <option value="unknown">答えない</option>
              <option value="right">右</option>
              <option value="left">左</option>
              <option value="both">両方</option>
            </select>
          </label>
          <label>
            習字・書道の経験
            <select
              value={profile.calligraphy}
              onChange={(e) =>
                setProfile({
                  ...profile,
                  calligraphy: e.target.value as CollectProfile["calligraphy"],
                })
              }
            >
              <option value="unknown">答えない</option>
              <option value="school">学校の授業だけ</option>
              <option value="lessons">習っていた</option>
              <option value="advanced">段・師範など</option>
            </select>
          </label>
          <label className="collect-check">
            <input
              type="checkbox"
              checked={profile.consentTrain}
              onChange={(e) =>
                setProfile({ ...profile, consentTrain: e.target.checked })
              }
            />
            書いた「と」を、AI の学習に使うことに同意します（必須）
          </label>
          <label className="collect-check">
            <input
              type="checkbox"
              checked={profile.consentShow}
              onChange={(e) =>
                setProfile({ ...profile, consentShow: e.target.checked })
              }
            />
            書いた「と」を、名前なしでほかの人に見せてもかまいません（「良い」の比べ合いに使います。任意）
          </label>
          <button type="submit" disabled={!profile.consentTrain || busy}>
            始める
          </button>
        </form>
        <p className="message" role="status">
          {message}
        </p>
      </main>
    );
  }

  if (step.kind === "done") {
    return (
      <main className="collect">
        <h1>ありがとうございました</h1>
        <p>{step.sent} 個の「と」を受け取りました。</p>
        <div className="actions">
          <button type="button" onClick={() => void start()} disabled={busy}>
            もう 1 回書く
          </button>
          <button
            type="button"
            onClick={() => {
              window.location.hash = "";
            }}
          >
            アプリへ
          </button>
        </div>
        <p className="message" role="status">
          {message}
        </p>
      </main>
    );
  }

  return (
    <CollectTrialView
      key={`${step.sessionId}-${step.index}`}
      step={step}
      profile={profile}
      onSent={() => {
        sentRef.current += 1;
        next();
      }}
      onSkip={next}
    />
  );
}

type TrialProps = {
  step: Extract<Step, { kind: "write" }>;
  profile: CollectProfile;
  onSent: () => void;
  onSkip: () => void;
};

/** 1 回分の書く画面。回ごとに作り直す（key）ので、枠と数えた値は毎回空から始まる。 */
function CollectTrialView({ step, profile, onSent, onSkip }: TrialProps) {
  const canvasRef = useRef<WritingCanvasHandle>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [strokeCount, setStrokeCount] = useState(0);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState("");
  /** 「消去」と「1つ戻る」を押した回数（書き直しの多さとして記録する） */
  const redoRef = useRef(0);

  const trial = step.plan.trials[step.index];
  const total = step.plan.trials.length;
  const empty = strokeCount === 0;

  async function handleNext() {
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
      await saveSample(step.plan, trial, drawing, profile, {
        writerId: loadWriterId(),
        sessionId: step.sessionId,
        displayPx: Math.max(50, displayPx),
        redoCount: redoRef.current,
      });
      onSent();
    } catch (error) {
      console.error(error);
      setMessage(
        error instanceof ProtocolChangedError
          ? "集め方が更新されました。ページを読み込み直してください。"
          : "送れませんでした。もう一度「次へ」を押してください。",
      );
      setSending(false);
    }
  }

  return (
    <main className="collect">
      <p className="collect-progress">
        {step.index + 1} / {total}
      </p>
      <h1 className="collect-instruction">
        <strong>{trial.instruction}</strong>「と」を書いてください
      </h1>

      <div ref={wrapRef}>
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
        {/* 書きにくい指示（利き手と反対の手など）は飛ばせる。飛ばした回は記録しない。 */}
        <button type="button" onClick={onSkip} disabled={sending}>
          飛ばす
        </button>
        <button type="button" onClick={handleNext} disabled={empty || sending}>
          次へ
        </button>
      </div>

      <p className="message" role="status">
        {message}
      </p>
    </main>
  );
}
