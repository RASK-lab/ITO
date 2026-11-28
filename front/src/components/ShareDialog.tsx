import { useEffect, useRef, useState } from "react";
import type { Sock } from "../api/drawings";
import { uploadShareCard } from "../api/share";
import {
  CARD_HEIGHT,
  CARD_WIDTH,
  makeShareCard,
  makeXCard,
  sharePageUrl,
} from "../shareCard";

type Props = {
  /** 記録の ID（確定の応答の id）。結果ごとのシェア用のアドレスに使う。 */
  drawingId: string;
  sock: Sock;
  /** 書いた「と」の画像（data URL） */
  drawingImage: string;
  onClose: () => void;
};

/** 保存するときのファイル名 */
const FILE_NAME = "ito-sock.png";

/** スマホやタブレット（指で操作する端末）か。出すボタンと、LINE の開き方を変える。 */
const isTouch = window.matchMedia("(pointer: coarse)").matches;

/**
 * iPhone・iPad か。ダウンロードすると「ファイル」に入り「写真」に入らないので、
 * 画像の長押しで保存してもらう。iPad は Mac と名乗るので、指で触れるかどうかでも見る。
 */
const isIos =
  /iPhone|iPad|iPod/.test(navigator.userAgent) ||
  (navigator.userAgent.includes("Macintosh") && navigator.maxTouchPoints > 1);

/**
 * 端末の共有の画面に、画像を渡せるか（スマホとタブレットで、ブラウザが対応しているとき）。
 * 渡せるなら、Instagram のボタンで共有の画面を出す。アプリの中のブラウザなどでは渡せない。
 */
const canShareImage =
  isTouch &&
  typeof navigator.canShare === "function" &&
  navigator.canShare({
    files: [new File([], "ito-sock.png", { type: "image/png" })],
  });

const SAVE_BY_LONG_PRESS =
  "上の画像を長押しして、「写真に保存」を選んでください。";

/** Instagram のボタンで共有の画面を出したときの、次にすることの案内 */
const STORIES_GUIDE =
  "共有の画面で Instagram を選び、「ストーリーズ」を選んでください。";

/**
 * シェアの画面。シェアする画像と、行き先のボタンを出す。
 * 端末の共有の画面は、スマホの Instagram だけで使う（画像をアプリに渡すため）。
 * スマホでは下から、パソコンでは中央に出る（index.css）。
 */
export function ShareDialog({ drawingId, sock, drawingImage, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  /** シェアする画像。作り終わるまで null。 */
  const [card, setCard] = useState<{ blob: Blob; url: string } | null>(null);
  /**
   * この結果だけのシェア用のアドレス（例: https://…/api/share/0123…）。
   * X のカード用の画像をバックエンドに預け終わるまでと、預けられなかったときは null。
   */
  const [resultPageUrl, setResultPageUrl] = useState<string | null>(null);
  const [note, setNote] = useState("");
  /** Instagram を押したあとに出す、Instagram を開くリンク */
  const [showInstagramLink, setShowInstagramLink] = useState(false);

  // 開いたら showModal で出す。Esc と、外側を押したときも閉じる。
  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  useEffect(() => {
    let url = "";
    let cancelled = false;
    makeShareCard(sock, drawingImage)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setCard({ blob, url });
      })
      .catch((error) => {
        console.error(error);
        if (!cancelled) setNote("画像を作れませんでした。");
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [sock, drawingImage]);

  // X のカード用の横長の画像を作り、バックエンドに預ける。預け終わったら、X に入れる
  // アドレスを、この結果だけのものに替える。失敗しても、X へのシェアは
  // くつしたごとの固定のページでできるので、画面には何も出さない。
  useEffect(() => {
    let cancelled = false;
    uploadShareCard(drawingId, () => makeXCard(sock, drawingImage))
      .then((path) => {
        if (!cancelled) setResultPageUrl(`${window.location.origin}${path}`);
      })
      .catch((error) => console.error(error));
    return () => {
      cancelled = true;
    };
  }, [drawingId, sock, drawingImage]);

  const text = `「と」を書いたら、くつした「${sock.name}」が届きました。`;
  const pageUrl = sharePageUrl(sock);

  /** 画像を保存する。iPhone・iPad では、長押しの案内を出す。 */
  function save() {
    if (!card) return;
    if (isIos) {
      setNote(SAVE_BY_LONG_PRESS);
      return;
    }
    const a = document.createElement("a");
    a.href = card.url;
    a.download = FILE_NAME;
    a.click();
    setNote("画像を保存しました。");
  }

  function handleSave() {
    setShowInstagramLink(false);
    save();
  }

  /** 共有の画面を出せないとき。画像を保存してもらい、Instagram で選んでもらう。 */
  function saveForInstagram() {
    save();
    setNote(
      isIos
        ? `${SAVE_BY_LONG_PRESS}そのあと、Instagram で選んでください。`
        : "画像を保存しました。Instagram で選んでください。",
    );
    setShowInstagramLink(true);
  }

  /**
   * Instagram のストーリーズに追加してもらう。
   * Web から Instagram のストーリーズの作成画面に画像を直接渡す方法はない（Instagram が
   * 用意している口は、アプリ専用）。端末の共有の画面に画像を渡し、そこで Instagram →
   * 「ストーリーズ」を選んでもらうのが、いちばん近い道。
   * どのアプリが並ぶかは端末しだいで、こちらからは Instagram を指定できない。
   */
  async function handleInstagram() {
    if (!card) return;
    if (!canShareImage) {
      saveForInstagram();
      return;
    }
    setShowInstagramLink(false);
    setNote(STORIES_GUIDE);
    try {
      // 画像だけを渡す（文も一緒に渡すと、画像を受け取らないアプリがあるため）
      await navigator.share({
        files: [new File([card.blob], FILE_NAME, { type: "image/png" })],
      });
    } catch (error) {
      // 利用者が共有の画面を閉じただけなら、案内を出したままにする
      if (error instanceof DOMException && error.name === "AbortError") return;
      console.error(error);
      saveForInstagram();
    }
  }

  async function handleCopy() {
    if (!card) return;
    setShowInstagramLink(false);
    try {
      await navigator.clipboard.write([
        new ClipboardItem({ "image/png": card.blob }),
      ]);
      setNote("画像をコピーしました。投稿の画面に貼り付けられます。");
    } catch (error) {
      console.error(error);
      setNote("コピーできませんでした。「画像を保存」を使ってください。");
    }
  }

  /**
   * X の、文とアドレスを入れた投稿の画面。画像は、アドレスのカードとして出る。
   * アドレスは、この結果だけのページ（カードに、書いた「と」が入る）。まだ用意できて
   * いないときと、用意できなかったときは、くつしたごとの固定のページ（くつしただけ）。
   */
  const xUrl = `https://x.com/intent/post?${new URLSearchParams({ text, url: resultPageUrl ?? pageUrl })}`;

  /** スマホでは LINE のアプリ、パソコンではブラウザ用の共有のページを開く */
  function handleLine() {
    const url = isTouch
      ? `https://line.me/R/share?${new URLSearchParams({ text: `${text} ${pageUrl}` })}`
      : `https://social-plugins.line.me/lineit/share?${new URLSearchParams({ url: pageUrl, text })}`;
    window.open(url, "_blank", "noopener");
  }

  return (
    <dialog
      ref={dialogRef}
      className="share"
      onClose={onClose}
      onClick={(event) => {
        // 外側（暗いところ）を押したら閉じる
        if (event.target === event.currentTarget) event.currentTarget.close();
      }}
    >
      <div className="share-body">
        {/* 画像を作る前から場所を取っておく */}
        <img
          className="share-card"
          src={card?.url}
          alt="シェアする画像"
          width={CARD_WIDTH}
          height={CARD_HEIGHT}
        />
        <div className="share-buttons">
          <h2>シェア</h2>
          {isTouch ? (
            // 共有の画面を出せるときは、行き先が分かる名前にする。長いので、1 行を使う。
            <button
              type="button"
              className={canShareImage ? "share-wide" : undefined}
              onClick={handleInstagram}
              disabled={!card}
            >
              {canShareImage ? "Instagram ストーリーズ" : "Instagram"}
            </button>
          ) : (
            <button type="button" onClick={handleCopy} disabled={!card}>
              画像をコピー
            </button>
          )}
          <button type="button" onClick={handleSave} disabled={!card}>
            画像を保存
          </button>
          {/*
            X は、文とアドレスを入れた投稿の画面を直接開く（画像は、アドレスのカードとして出る）。
            X へのシェアは、このリンク 1 つだけ。
            ボタンではなくリンクにする。スマホでは、利用者が自分で押したリンクのときだけ、
            X のアプリが開く（window.open だと、アプリがあってもブラウザで開く）。
          */}
          <a
            className="share-link"
            href={xUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            X
          </a>
          <button type="button" onClick={handleLine}>
            LINE
          </button>
          {/* Instagram が 1 行を使うときは、LINE の隣に並べる（1 個だけ余らせない） */}
          <button
            type="button"
            className={isTouch && canShareImage ? undefined : "share-wide"}
            onClick={() => dialogRef.current?.close()}
          >
            とじる
          </button>
          <p className="share-note" role="status">
            {note}
            {showInstagramLink && (
              <>
                {" "}
                <a
                  href="https://www.instagram.com/"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Instagram を開く
                </a>
              </>
            )}
          </p>
        </div>
      </div>
    </dialog>
  );
}
