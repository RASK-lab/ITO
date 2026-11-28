import type { Drawing, PointerType } from "../components/WritingCanvas";

/**
 * 学習データ集めの API（back/src/collect.py、docs/collect.md）。
 * アプリ本体の「確定」（drawings.ts）とは別に記録する。
 */

/** 書いてもらう 1 回分。instruction は画面に出す指示の文（サーバーが決める）。 */
export type CollectTrial = {
  trial: number;
  /** 指示の種類（ラベル）。natural は「いつもどおり」 */
  condition: string;
  instruction: string;
};

export type CollectPlan = {
  /** 集め方の版。送るときにそのまま返す */
  protocol: string;
  trials: CollectTrial[];
};

/** 書いた人の申告。最初の画面で一度だけ聞き、ブラウザに覚えておく。 */
export type CollectProfile = {
  dominantHand: "right" | "left" | "both" | "unknown";
  calligraphy: "school" | "lessons" | "advanced" | "unknown";
  /** 学習に使ってよいか。true でないと記録しない */
  consentTrain: boolean;
  /** ほかの人に見せてよいか（あとで「良い」の比べ合いに使う） */
  consentShow: boolean;
};

/** 1 個の「と」に添える、書いたときの様子 */
export type CollectContext = {
  writerId: string;
  sessionId: string;
  /** 書く枠の、画面での一辺（CSS ピクセル） */
  displayPx: number;
  /** 「消去」と「1つ戻る」を押した回数 */
  redoCount: number;
};

/** 集めるときの点の上限（back/src/collect.py の MAX_COLLECT_POINTS と同じ値） */
export const MAX_COLLECT_POINTS = 20_000;

/** 書いた「と」（いまは「と」だけ。drawings.ts の TARGET と同じ） */
const TARGET = "と";

/** 集め方が更新されたとき（古いページを開いたまま）のエラー */
export class ProtocolChangedError extends Error {}

/** 画面の種類から、書くのに使いそうな入力を推測する（件数をそろえるため）。 */
export function guessPointerType(): PointerType {
  return window.matchMedia("(pointer: coarse)").matches ? "touch" : "mouse";
}

export async function fetchPlan(pointer: PointerType): Promise<CollectPlan> {
  const response = await fetch(`/api/collect/plan?pointer=${pointer}`, {
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export async function saveSample(
  plan: CollectPlan,
  trial: CollectTrial,
  drawing: Drawing,
  profile: CollectProfile,
  context: CollectContext,
): Promise<void> {
  const response = await fetch("/api/collect/samples", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal: AbortSignal.timeout(15_000),
    body: JSON.stringify({
      protocol: plan.protocol,
      writer_id: context.writerId,
      session_id: context.sessionId,
      trial: trial.trial,
      condition: trial.condition,
      dominant_hand: profile.dominantHand,
      calligraphy: profile.calligraphy,
      consent_train: profile.consentTrain,
      consent_show: profile.consentShow,
      display_px: Math.round(context.displayPx),
      device_pixel_ratio: window.devicePixelRatio || 1,
      redo_count: context.redoCount,
      target: TARGET,
      canvas: drawing.canvas,
      strokes: drawing.strokes,
      image: drawing.image,
      width: drawing.width,
      height: drawing.height,
    }),
  });
  if (response.status === 409) throw new ProtocolChangedError();
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
}

/**
 * 無作為な ID（英小文字・数字・ハイフン）。crypto.randomUUID は https か localhost でしか
 * 使えないので、使えないとき（スマホから PC の IP で開いたときなど）は自分で作る。
 */
export function randomId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

const WRITER_KEY = "ito.collect.writerId";
const PROFILE_KEY = "ito.collect.profile";

/**
 * 書いた人の匿名の ID。ブラウザに覚えさせ、同じ人が何回書いても同じ ID にする
 * （同じ人の字を、学習と評価に分けて入れないため）。名前などとは結び付けない。
 */
export function loadWriterId(): string {
  try {
    const stored = localStorage.getItem(WRITER_KEY);
    if (stored) return stored;
    const id = randomId();
    localStorage.setItem(WRITER_KEY, id);
    return id;
  } catch {
    // 覚えられないとき（プライベートウィンドウなど）は、毎回新しい ID になる
    return randomId();
  }
}

export function loadProfile(): CollectProfile | null {
  try {
    const stored = localStorage.getItem(PROFILE_KEY);
    return stored ? (JSON.parse(stored) as CollectProfile) : null;
  } catch {
    return null;
  }
}

export function saveProfile(profile: CollectProfile): void {
  try {
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  } catch {
    // 覚えられなくても続けられる（次回また聞くだけ）
  }
}
