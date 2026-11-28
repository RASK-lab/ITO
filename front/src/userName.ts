/** ユーザーネームの決まり。バックエンド（back/src/drawings.py）と同じ値にする。 */
export const MAX_USER_NAME_LENGTH = 15;
/** 名前を入れずに進んだときの名前 */
export const DEFAULT_USER_NAME = "User";

const STORAGE_KEY = "ito.userName";

// ブラウザの保存場所が使えないとき（プライベートウィンドウなど）は、ページを開いている間だけ覚える
let fallback: string | null = null;

/** 前後の空白を取り、長さの上限で切る */
export function normalizeUserName(input: string): string {
  return Array.from(input.trim()).slice(0, MAX_USER_NAME_LENGTH).join("").trim();
}

/**
 * 入力されたユーザーネームを覚えておく（空のままでもよい）。
 * ブラウザを閉じても残る。
 */
export function saveUserName(input: string): void {
  const name = normalizeUserName(input);
  fallback = name;
  try {
    localStorage.setItem(STORAGE_KEY, name);
  } catch {
    // 保存できなくても、このページを開いている間は fallback で動く
  }
}

/**
 * 入力されたままのユーザーネーム（空のこともある）。
 * 最初の画面で「手紙を書く」をまだ押していなければ null。
 */
export function loadUserName(): string | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null) return normalizeUserName(stored);
  } catch {
    // 下の fallback を使う
  }
  return fallback;
}

/** 画面に出したり、サーバーに送ったりする名前。入力が空なら「User」。 */
export function displayUserName(): string {
  return loadUserName() || DEFAULT_USER_NAME;
}
